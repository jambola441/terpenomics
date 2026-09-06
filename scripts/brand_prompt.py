#!/usr/bin/env python3
"""
brand_prompt.py — One brand, one catalog, one batch: a brand-scoped enrichment prompt.

The generic pipeline sends a mixed-brand batch and injects a per-item shortlist of
catalog values into `known_strains`. Measured, that shape has two problems. The
shortlist lands in a slot the system prompt says to REUSE verbatim, which overrides
the source spelling and propagated a brand's self-censored title into `strain`. And
because only some items in a batch carry the extra keys, the payload is
heterogeneous — three Camino listings lost their product_line in both hinted eval
runs and neither unhinted one, for a brand with no catalog at all.

Batching by brand removes both. Every item in the batch is the same brand, so there
is no asymmetry between items. The catalog appears once, as reference material in
the system message — where it is cacheable and costs ~1k tokens per batch rather
than a shortlist repeated 50 times — instead of as a value pushed into a field.

The model is asked to identify which catalog product a listing IS, and to say so
explicitly (`catalog_match`), rather than being handed a spelling to copy. That
makes "none of them" a first-class answer: a listing for a discontinued or renamed
product should match nothing, and the extraction rules below still apply.

The per-category rules are the same ones the generic prompts carry — regrouped by
category rather than restated, so the two cannot drift into disagreeing.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# What each category means for the fields we extract. Sourced from the rules already
# in enrich.py's _CLASSIFY_BODY and _EXTRACT_PROMPT; kept per-category here so a
# brand batch only pays tokens for the categories that brand actually sells.
CATEGORY_RULES: dict[str, dict[str, str]] = {
    "flower":      {"variant": "weight (3.5g, 1g, 7g)", "strain": "cultivar"},
    "preroll":     {"variant": "weight (1g, 0.5g)", "strain": "cultivar"},
    "vaporizers":  {"variant": "weight (1g, 0.5g, 2g)", "strain": "cultivar or flavour"},
    "edible":      {"variant": "TOTAL package THC in mg — multiply a per-piece dose by "
                               "the pack count (5mg x 20pk = 100mg). For a drink this is "
                               "still the mg dose, never the liquid volume.",
                    "strain": "flavour"},
    "concentrate": {"variant": "weight (1g, 0.5g)", "strain": "cultivar"},
    "tinctures":   {"variant": "total mg (1000mg) — never converted to grams",
                    "strain": "flavour or blend name"},
    "topical":     {"variant": "total mg (1000mg)",
                    "strain": "scent or blend name — but a product line "
                              "(Revive/Restore/Rescue) is a line, not a strain"},
    "merch":       {"variant": "size and pack together (1 1/4 33ct)",
                    "strain": "null — accessories have no cultivar"},
    "other":       {"variant": "\"\" when there is no meaningful size", "strain": "flavour"},
}


def _catalog_lines(catalog: dict) -> list[str]:
    """One line per catalog product, with its variants folded in.

    Grouped by the source's own product id: a title can repeat across categories
    (Ayrloom sells 'honeycrisp' as a vape, a beverage and a canned drink), and
    collapsing those by name would hide exactly the distinction the model needs.
    """
    groups: dict[str, list[dict]] = {}
    for e in catalog.get("entries", []):
        groups.setdefault(e.get("product_external_id") or e["name"], []).append(e)

    lines = []
    for entries in groups.values():
        first = entries[0]
        bits = [f"{first['name']}"]
        cat = first.get("category")
        sub = first.get("subtype")
        bits.append(f"[{cat}/{sub}]" if cat and sub else f"[{cat or 'uncategorised'}]")
        if first.get("product_line"):
            bits.append(f"line={first['product_line']}")
        variants = [e["variant"] for e in entries if e.get("variant")]
        if variants:
            bits.append("sizes: " + " | ".join(dict.fromkeys(variants)))
        lines.append("  " + "  ".join(bits))
    return sorted(lines)


def _categories_for(catalog: dict, rows: list[dict] | None) -> list[str]:
    """Which category rails this batch needs: the catalog's UNION the batch's.

    Deriving from the catalog alone is wrong in both directions. It omits a rail the
    batch needs — a store carrying a discontinued or miscategorised product our
    scraper tagged `flower` would find no flower option in the prompt and have to
    pick something wrong. And it pays for a rail the batch will never use: one plush
    dog toy in Ayrloom's catalog pulled in the merch rail, the longest in the system
    at 22 subtypes, for a brand with zero merch listings.

    The batch is the authority on what needs answering; the catalog only adds
    categories the brand demonstrably sells.
    """
    from_catalog = {e.get("category") for e in catalog.get("entries", [])
                    if e.get("category")}
    from_rows = {(r.get("category") or "").strip().lower() for r in (rows or [])}
    # A catalog category with no listing in this batch is dead weight; keep it only
    # when the batch has nothing to say, so a prompt is never left with no rails.
    cats = (from_rows & from_catalog) | (from_rows - {""}) if from_rows else from_catalog
    return [c for c in sorted(cats) if c in CATEGORY_RULES] or list(CATEGORY_RULES)


def system_prompt(brand: str, catalog: dict, rows: list[dict] | None = None,
                  categories: list[str] | None = None) -> str:
    """The brand-scoped system message: task, taxonomy, then the brand's catalog.

    `rows` is the batch this prompt will be sent with — passing it scopes the
    taxonomy to the categories actually present. Omit it only when building a
    prompt with no batch in hand.
    """
    cats = categories or _categories_for(catalog, rows)

    import enrich  # local: avoids a cycle when enrich imports this module
    taxonomy = []
    for c in cats:
        rules = CATEGORY_RULES[c]
        subs = enrich.SUBTYPES.get(c, [])
        taxonomy.append(
            f"{c}\n"
            f"    subtype:  {', '.join(subs) if subs else '(none)'}\n"
            f"    variant:  {rules['variant']}\n"
            f"    strain:   {rules['strain']}"
        )

    entries = catalog.get("entries", [])
    products = len({e.get("product_external_id") or e["name"] for e in entries})

    return f"""\
You are enriching dispensary listings for a single brand: {brand}.

Every listing below is a {brand} product as one dispensary happens to have written it.
Different stores write the same product differently, so your job is to recognise WHICH
{brand} product each listing is, then report its attributes on our schema.

For each listing return: category, subtype, strain, product_line, variant, catalog_match.

CATEGORIES AND THEIR ATTRIBUTES
{chr(10).join(taxonomy)}

Shared rules:
  - strain is ONLY the strain/flavour. Never fold product_line into it
    ("Night Cap Elderberry Sage" -> strain "Elderberry Sage", product_line "Night Cap").
  - Strip the brand name, format words (Cart, Pre-Roll, Gummy, Disposable), sizes,
    and cannabinoid ratios ("1:2:3", "10MG THC : 5MG CBD") out of strain.
  - Title Case; crosses use " x ". Keep OG, AK, RSO, CBD, THC, NYC in caps.
  - product_line only when the listing's own name contains that line's text.

{brand.upper()} PRODUCT CATALOG — {products} products, {len(entries)} SKUs
This is what {brand} actually makes, taken from the brand's own storefront. Use it to
recognise the product behind an inconsistent store name, and to settle which part of
the name is the line and which is the strain.

{chr(10).join(_catalog_lines(catalog))}

Using the catalog:
  - catalog_match: the catalog product name this listing IS, or null.
  - Return null when nothing genuinely matches. Stores carry discontinued and
    renamed products, so "not in the catalog" is a normal, expected answer — do NOT
    stretch to the nearest entry. A wrong match is worse than none.
  - A catalog match tells you which product this is. It does NOT override the
    listing: report the size THIS listing sells (a single can is "10mg", even where
    the catalog lists a 12-pack), and keep our schema's spelling conventions rather
    than copying a marketing rendering verbatim.

Reply ONLY with a JSON array, no prose, no markdown fences:
[{{"id": "0", "category": "edible", "subtype": "beverage", "strain": "Honeycrisp",
  "product_line": "UP", "variant": "10mg", "catalog_match": "honeycrisp"}}, ...]"""


def user_message(rows: list[dict]) -> str:
    """The batch itself — every item the same brand, so the shape is uniform."""
    return json.dumps([
        {
            "id": str(i),
            "name": r.get("name", ""),
            "scraped_category": r.get("category", ""),
            "scraped_variant": r.get("variant", ""),
            "description": r.get("description", ""),
        }
        for i, r in enumerate(rows)
    ], ensure_ascii=False, indent=2)
