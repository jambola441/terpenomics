"""
taxonomy.py — What each category's attributes are, defined once.

A listing's attributes used to be defined in seven places that had to agree and
did not: enrich.py's rails, defaults and prompts, brand_prompt.py's per-category
rules, brand_catalog.py's idea of which titles are strains, enrichers.py's merch
rail, sizes.py's and scraper_common.py's ideas of which categories are dosed rather
than weighed. Topical alone had three answers to "is its size mg or grams" — the
README's five always-failing topical cases are that disagreement showing.

This is the one table. Everything that needs to know what a category's attributes
mean reads it from here; nothing else declares them.

Per category
------------
  subtypes        the rail — every answer is clamped to it (order is the prompt's)
  default_subtype what a row gets when no token or model settles it
  measure         what `variant` measures:
                    weight  grams of product (flower, preroll, vape, concentrate)
                    dose    total mg of THC in the package (edible, tincture, topical)
                    pack    size and pack count of an accessory (merch)
                    none    nothing meaningful (other)
  strain_means    what `strain` holds for this category, or None when it has none
  variant_rule /  how the model is told to write variant and strain — the text the
  strain_rule     brand-scoped prompt sends, so the two prompts cannot drift apart
  identity        the fields that make two listings the same product. A catalog
                  entry carries these; a listing resolved to one takes them. A
                  category whose identity has no subtype keeps none (keeps_subtype).
  title_is_strain a brand's catalog title names the strain/flavour (a vape called
                  "honeycrisp"); false where it names the product ("restore balm")
  catalogable     whether brand catalogs model this category (merch identity is
                  fully determined by name tokens; "other" is not a product)

Ordering is load-bearing in two places and both are preserved exactly:
CATEGORY_ORDER is the category list the classify prompt shows, and RAIL_ORDER is the
order its subtype rails are listed in. A rail edit is a prompt edit — README.md,
"a subtype rail is part of the prompt" — so scripts/test_taxonomy.py pins the prompts
byte for byte against what they were before this module existed.

A leaf module on purpose: it imports nothing from the repo, so every other module,
scrapers included, can import it without a cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CategorySpec:
    name: str
    subtypes: tuple[str, ...]
    default_subtype: str | None
    measure: str
    strain_means: str | None
    variant_rule: str
    strain_rule: str
    identity: tuple[str, ...]
    title_is_strain: bool
    catalogable: bool = True
    notes: str = ""


# Merch's rail is the longest and the only one owned by a deterministic enricher
# (scripts/enrichers.py, MerchEnricher), which reads it from here.
MERCH_SUBTYPES = ("gift-card", "filter-tip", "roller", "ashtray", "cone", "paper",
                  "wrap", "grinder", "tray", "bong", "pipe", "dab-tool", "bowl",
                  "downstem", "charger", "battery", "lighter", "storage", "apparel",
                  "cleaning", "scale", "merch")

_WEIGHT_RULE = "weight ({})"
_CULTIVAR_IDENTITY = ("subtype", "product_line", "strain", "size")

SPECS: dict[str, CategorySpec] = {s.name: s for s in (
    CategorySpec(
        "flower", ("flower", "smalls", "preground", "infused"), "flower", "weight",
        "cultivar", _WEIGHT_RULE.format("3.5g, 1g, 7g"), "cultivar",
        _CULTIVAR_IDENTITY, title_is_strain=True),
    CategorySpec(
        "preroll", ("single", "infused", "pack"), "single", "weight",
        "cultivar", _WEIGHT_RULE.format("1g, 0.5g"), "cultivar",
        ("product_line", "strain", "size"), title_is_strain=True,
        notes="A pack's size is the package total: 5 x 0.6g is 3g (sizes.py). No "
              "subtype is kept: single or pack is the size's pack count, and infused "
              "is the product line where the brand names one ('Live Resin Infused'). "
              "As a subtype, infused took the slot from pack on 834 listings, and 87 "
              "products sat under two subtypes (2026-10-05). The rail is still in the "
              "classify prompt, since a rail edit is a prompt edit; its answer is dropped."),
    CategorySpec(
        "vaporizers", ("cart", "all-in-one", "pod", "battery", "other"), None, "weight",
        "cultivar or flavour", _WEIGHT_RULE.format("1g, 0.5g, 2g"), "cultivar or flavour",
        _CULTIVAR_IDENTITY, title_is_strain=True),
    CategorySpec(
        "edible", ("gummy", "chocolate", "beverage", "tablet", "other"), None, "dose",
        "flavour",
        "TOTAL package THC in mg — multiply a per-piece dose by the pack count "
        "(5mg x 20pk = 100mg). For a drink this is still the mg dose, never the liquid volume.",
        "flavour",
        ("subtype", "product_line", "strain", "size"), title_is_strain=True,
        notes="New York caps an edible package at 100mg; sizes.py uses that to read "
              "a lone dose beside a pack count as per piece."),
    CategorySpec(
        "concentrate", ("diamonds", "rosin", "resin", "hash", "rso", "other"), None, "weight",
        "cultivar", _WEIGHT_RULE.format("1g, 0.5g"),
        "cultivar", _CULTIVAR_IDENTITY, title_is_strain=True),
    CategorySpec(
        "tinctures", ("tincture",), "tincture", "dose",
        "flavour or blend name", "total mg (1000mg) — never converted to grams",
        "flavour or blend name",
        ("subtype", "product_line", "strain", "size"), title_is_strain=True),
    CategorySpec(
        "topical", ("topical",), "topical", "dose",
        "scent or blend name", "total mg (1000mg)",
        "scent or blend name — but a product line (Revive/Restore/Rescue) is a line, not a strain",
        ("subtype", "product_line", "strain", "size"), title_is_strain=False,
        notes="Measured in mg like a tincture. scraper_common used to treat it as "
              "neither dose nor weight, so a 1000mg balm became '1g'."),
    CategorySpec(
        "merch", MERCH_SUBTYPES, "merch", "pack",
        None, "size and pack together (1 1/4 33ct)", "null — accessories have no cultivar",
        ("subtype", "attributes", "size"), title_is_strain=False, catalogable=False,
        notes="Answered entirely from the name by MerchEnricher; colour and flavour "
              "live in attributes (scripts/attributes.py)."),
    CategorySpec(
        "other", ("other",), "other", "none",
        "flavour", "\"\" when there is no meaningful size", "flavour",
        ("subtype", "strain"), title_is_strain=False, catalogable=False),
)}

# The category list the classify prompt shows, in its historical order.
CATEGORY_ORDER = ("flower", "preroll", "vaporizers", "edible", "concentrate",
                  "tinctures", "topical", "merch", "other")
# The order the classify prompt lists subtype rails in. Historical, and part of the
# prompt: reordering it changes what the model reads for every item.
RAIL_ORDER = ("vaporizers", "edible", "concentrate", "preroll", "flower",
              "tinctures", "topical", "merch", "other")
# brand_prompt.py's per-category rules, in the order it has always listed them.
RULES_ORDER = ("flower", "preroll", "vaporizers", "edible", "concentrate",
               "tinctures", "topical", "merch", "other")

assert set(CATEGORY_ORDER) == set(SPECS) == set(RAIL_ORDER) == set(RULES_ORDER)


# Format words that settle a subtype from the name alone — string facts about the
# listing ("Cart", "AIO", "Starter Kit"). Order matters: the first match wins.
# Enrichment sends the result to the model as its hint; the catalog paths let it beat
# a catalog entry's subtype (catalog_match.py). Pre-rolls keep no subtype
# (keeps_subtype), so theirs is only ever the classify prompt's hint.
SUBTYPE_TOKENS: dict[str, dict[str, re.Pattern]] = {
    "vaporizers": {
        "all-in-one": re.compile(r"\ball[\s-]*in[\s-]*one\b|\baio\b|\bdisposable\b", re.I),
        "cart": re.compile(r"\b(cart|510|cartridge|preload|reload)\b", re.I),
        "pod": re.compile(r"\bpod\b", re.I),
        "battery": re.compile(r"\b(battery|starter\s*kit)\b", re.I),
    },
    "edible": {
        "beverage": re.compile(r"\b(beverage|sparkling\s+water|tea\s+sachet|drink)\b", re.I),
        "gummy": re.compile(r"\bgumm|\bchews?\b|\brope\b|\bpearl\b", re.I),
        "chocolate": re.compile(r"\bchocolate\b|\bbar\b", re.I),
        "tablet": re.compile(r"\btablet\b|\bprotab\b|\bcapsule\b|\bpill\b|\bbean\b|\bdrop\b", re.I),
    },
    "preroll": {
        "infused": re.compile(r"\b(infused|kief|diamond|hash\s*hole|live\s*resin|live\s*rosin)\b", re.I),
        "pack": re.compile(r"\bpack\b|\bvariety\b|\b\d+\s*pk\b", re.I),
    },
    "flower": {
        "smalls": re.compile(r"\bsmalls?\b|\bsmall\s+bud", re.I),
        "preground": re.compile(r"\bpre-?ground\b|\bground\s+flower\b|\bready\s*-?\s*to\s*-?\s*roll\b", re.I),
        "infused": re.compile(r"\bdiamond\s+infused\b|\binfused\b", re.I),
    },
}


def token_subtype(category: str | None, name: str | None) -> str | None:
    """The subtype a format word in the name states, or None."""
    for subtype, pattern in SUBTYPE_TOKENS.get((category or "").strip().lower(), {}).items():
        if pattern.search(name or ""):
            return subtype
    return None


def spec(category: str | None) -> CategorySpec | None:
    return SPECS.get((category or "").strip().lower())


def keeps_subtype(category: str | None) -> bool:
    """Whether a listing or catalog entry of this category keeps a subtype: only where
    the subtype is part of the product's identity. A pre-roll's is not (its spec's
    notes say why). An unknown category keeps what it has."""
    s = spec(category)
    return s is None or "subtype" in s.identity


def rails() -> dict[str, list[str]]:
    """category -> its subtype rail, in prompt order."""
    return {c: list(SPECS[c].subtypes) for c in RAIL_ORDER}


def default_subtypes() -> dict[str, str | None]:
    return {c: SPECS[c].default_subtype for c in RAIL_ORDER}


def categories_measured_by(measure: str) -> frozenset[str]:
    return frozenset(c for c, s in SPECS.items() if s.measure == measure)


def prompt_rules() -> dict[str, dict[str, str]]:
    """What brand_prompt.py tells the model about variant and strain, per category."""
    return {c: {"variant": SPECS[c].variant_rule, "strain": SPECS[c].strain_rule}
            for c in RULES_ORDER}


def strain_bearing() -> frozenset[str]:
    """Categories whose catalog titles name a strain or flavour."""
    return frozenset(c for c, s in SPECS.items() if s.title_is_strain)


def catalogable() -> frozenset[str]:
    return frozenset(c for c, s in SPECS.items() if s.catalogable)
