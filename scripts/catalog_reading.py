#!/usr/bin/env python3
"""
catalog_reading.py — Read a listing in its brand's catalog's own words.

Enrichment reads a listing from its name alone: the strain it writes is a phrase from
the name ("Wild Cherry Excite"), the line whatever the name spells out, and the matcher
then has to find which catalog product those words mean. For a brand with a catalog this
reads the listing *against* the catalog instead, one attribute at a time, each question
offering only the catalog's values that fit the answers before it (owner's design,
2026-10-10):

    category  ->  subtype  ->  product line  ->  strain  ->  size

  * category and subtype options carry the classifier's definitions
    (jev_classify.CATEGORY_CRITERIA / SUBTYPE_CRITERIA), so "chews" reads as a gummy;
  * the store's description is in the state;
  * subtype and line narrow the options only on a confident answer (p >= NARROW_AT);
    an unsure one is left blank in the reading and the next question sees every value,
    so a wrong line cannot hide the right strain;
  * size is asked among the sizes of the product just picked, spelled out ("10pk
    100mg: 10 pieces, 100mg THC in the whole package"): a bare "100mg" then means the
    one package with that total, not every size the brand sells.

The reading is the catalog's values, so the attribute join (catalog_match.CatalogIndex
.join) settles it without Jev; Jev no longer picks entries at matching. Each answer's
probability is kept on the reading (`p`), and the matcher trusts a join only when the
strain and size were read confidently (TRUST_AT): a listing of a product the catalog
lacks reads "none" or reads its nearest product unsurely (measured 2026-10-10: the
Excite listings, with Exhilarate removed, read the wrong strain at p 0.81-0.85 against
0.99 for true picks), and goes to the review queue, where the fix is the catalog.

Answers are cached per question (state and options), under data/enrich_cache/
catalog_match/reading.<brand>.json, so a re-import re-asks only a listing whose text or
catalog options changed. About five Jev calls a listing, $0.000025 each.

Usage
-----
  python scripts/catalog_reading.py --brand "Off Hours"            # read, print a sample
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_store  # noqa: E402
import jev  # noqa: E402
import jev_classify  # noqa: E402
import merch_catalog  # noqa: E402
import sizes  # noqa: E402

# Bump when a question or option text changes: cached answers to an older question are
# then asked again.
QUESTION_VERSION = 1

# Subtype and line narrow the next question's options only at or above this; below it
# the answer is left out of the reading.
NARROW_AT = float(os.environ.get("CATALOG_READING_NARROW_AT", "0.9"))
# The matcher trusts a join only when category, strain and size were read at least this
# surely (catalog_match.resolve); below it the listing goes to review.
TRUST_AT = float(os.environ.get("CATALOG_READING_TRUST_AT", "0.9"))

DESCRIPTION_CHARS = 1000

CATEGORY_Q = "Which category of cannabis product is this listing? Choose none if it is none of these."
SUBTYPE_Q = ("Which type of product is this listing within its category (a gummy, a gummy rope, a "
             "chocolate, a cartridge, an all-in-one vape, a pre-roll pack and so on)? Choose none if "
             "it is none of these.")
LINE_Q = ("Which of this brand's product lines is this listing in? A product line is a name the brand "
          "uses for a family of its products. Stores often leave the line out or write it "
          "differently, so pick the line this product belongs to, not only one spelled out in the "
          "name. Choose none if it belongs to none of these.")
STRAIN_Q = ("Which of these is this product's strain or flavor: the name that tells it apart from the "
            "brand's other products? A flavor counts as the strain for edibles, drinks, vapes and "
            "topicals. Stores often add, drop or reorder words, so pick the one that names the same "
            "product. It is never the brand, a format, a size or a potency. Choose none if the "
            "strain is not one of these.")
SIZE_Q = ("This listing is the product named in 'product'. Which of that product's packages is it? "
          "Stores often give only part of the size: just the package's total ('100mg') or just the "
          "count ('10pk'). A listing that states only the total or only the count is the package "
          "with that total or count. Choose none only if the listing states a total or count that "
          "none of these packages has.")

# (question key, catalog entry field, reading field, instructions)
STEPS = (("category", "category", "category", CATEGORY_Q),
         ("subtype", "subtype", "subtype", SUBTYPE_Q),
         ("line", "product_line", "product_line", LINE_Q),
         ("strain", "strain", "strain", STRAIN_Q),
         ("size", "variant", "size", SIZE_Q))
# Steps whose unsure answer is left blank rather than ending the reading.
SOFT = ("subtype", "line")
NONE = "none"
MAX_OPTIONS = 254          # Jev takes 255 options, one of them "none"


def spell_size(label: str, category: str | None) -> str:
    """A catalog size with what it means: what a store's partial size is matched against."""
    z = sizes.parse(label, category=category)
    if z.mg is not None and z.pack:
        return f"{label}: {z.pack} pieces, {z.mg:g}mg THC in the whole package"
    if z.mg is not None:
        return f"{label}: {z.mg:g}mg THC in the whole package"
    if z.grams is not None and z.pack:
        return f"{label}: {z.pack} pieces, {z.grams:g}g in total"
    if z.grams is not None:
        return f"{label}: {z.grams:g}g in total"
    return label


def option_label(key: str, value: str, category: str | None) -> str:
    if key == "category" and value in jev_classify.CATEGORY_CRITERIA:
        return f"{value}: {jev_classify.CATEGORY_CRITERIA[value]}"
    if key == "subtype":
        crit = jev_classify.SUBTYPE_CRITERIA.get(category or "", {})
        return f"{value}: {crit[value]}" if value in crit else value
    if key == "size":
        return spell_size(value, category)
    return value


def base_state(brand: str, listing: dict) -> dict:
    state = {"brand": brand, "name": listing.get("name") or "",
             "store_size_field": listing.get("variant") or ""}
    text = html.unescape(re.sub(r"<[^>]+>", " ", listing.get("description") or ""))
    text = " ".join(text.split())[:DESCRIPTION_CHARS]
    if text:
        state["description"] = text
    return state


class _Walk:
    """One listing's way down the steps."""

    def __init__(self, listing: dict, entries: list[dict]):
        self.listing = listing
        self.pool = entries
        self.reading: dict = {}
        self.p: dict[str, float] = {}
        self.done = False
        self.failed = False

    def question(self, step: tuple, brand: str) -> tuple[dict, dict, list[str]] | None:
        key, field, _, instructions = step
        values = sorted({e[field] for e in self.pool if e.get(field)}, key=str)
        if not values:
            return None                       # nothing to tell apart here (no lines): skip
        if len(values) > MAX_OPTIONS:
            self.failed = True                # more than Jev takes: the reading it has stands
            return None
        if key == "size":
            extra = {"product": self.reading.get("strain")}
        else:
            extra = {k: self.reading[k] for k in ("category", "subtype", "product_line")
                     if self.reading.get(k)}
        options = {NONE: "None of these"}
        for i, v in enumerate(values):
            options[f"o{i}"] = option_label(key, v, self.reading.get("category"))
        return dict(base_state(brand, self.listing), **extra), \
            {key: jev.Choice(instructions, options)}, values

    def answer(self, step: tuple, pick: str | None, p: float, values: list[str]) -> None:
        key, field, out, _ = step
        value = None if pick in (None, NONE) else values[int(pick[1:])]
        self.p[key] = round(p, 3)
        if key in SOFT and (value is None or p < NARROW_AT):
            return                            # unsure: blank, and the options stay whole
        self.reading[out] = value
        if value is None:
            if key in ("category", "strain"):
                self.done = True              # the catalog has no such product
            return
        self.pool = [e for e in self.pool if e.get(field) == value]


def _cache_key(state: dict, question: dict) -> str:
    q = {k: {"i": c.instructions, "o": c.criteria} for k, c in question.items()}
    blob = json.dumps([QUESTION_VERSION, state, q], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def read(catalog: dict, listings: list[dict], *, usage: jev.Usage | None = None,
         cache=None, workers: int = 8) -> dict[str, dict]:
    """Each listing's reading in the catalog's values, by listing id: category, subtype,
    product_line, strain and size (None where unread or unsure), with `p`, each step's
    probability, and `by` = "catalog". A listing Jev could not answer for is left out:
    the caller keeps the reading it has. Merch is left out too (merch_catalog reads it).

    Listings are dicts with id, name, variant, description and, for merch, category and
    subtype."""
    import catalog_match
    brand = catalog.get("brand_name") or ""
    entries = [e for e in catalog.get("entries") or [] if e.get("is_active", True)]
    cache = cache or catalog_match.AnswerCache(f"reading.{catalog.get('brand_slug') or 'x'}")
    walks = [_Walk(l, entries) for l in listings
             if not merch_catalog.is_merch(l.get("category"), l.get("subtype"), l.get("name") or "", brand)]
    for step in STEPS:
        jobs, pending = [], []
        for w in walks:
            if w.done or w.failed:
                continue
            q = w.question(step, brand)
            if q is None:
                continue
            state, question, values = q
            key = _cache_key(state, question)
            hit = cache.get(key)
            if hit is not None:
                w.answer(step, hit["pick"], hit["p"], values)
                continue
            jobs.append((state, question))
            pending.append((w, values, key))
        for (w, values, key), res in zip(pending, jev.ask_many(jobs, workers=workers, usage=usage)
                                         if jobs else []):
            if res is None:
                w.failed = True
                continue
            pick, p, _ = res.choice(step[0])
            cache.put(key, {"pick": pick, "p": round(p, 4)})
            w.answer(step, pick, p, values)
    cache.save()
    out = {}
    for w in walks:
        if w.failed:
            continue
        r = {f: w.reading.get(f) for f in ("category", "subtype", "strain", "product_line", "size")}
        out[str(w.listing["id"])] = dict(r, p=w.p, by="catalog")
    return out


def trusted(reading: dict | None) -> bool:
    """Whether a catalog reading is sure enough for its join to be trusted: category,
    strain and size each read at TRUST_AT or above. A reading not made against the
    catalog (enrichment's) has no probabilities and is not held to this."""
    if not reading or reading.get("by") != "catalog":
        return True
    p = reading.get("p") or {}
    return all(p.get(k, 0.0) >= TRUST_AT for k in ("category", "strain", "size"))


def unsure_steps(reading: dict | None) -> list[str]:
    """The steps of a catalog reading answered below its bar (review queue detail)."""
    if not reading or reading.get("by") != "catalog":
        return []
    p = reading.get("p") or {}
    return [k for k, v in p.items() if v < (NARROW_AT if k in SOFT else TRUST_AT)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    import catalog_match
    cat = catalog_store.for_brand(catalog_store.load_all("auto"), args.brand)
    if not cat:
        sys.exit(f"No catalog for {args.brand!r}")
    key = catalog_store.brand_key(args.brand)
    listings = [l for l in catalog_match.fetch_listings() if catalog_store.brand_key(l.get("brand")) == key]
    usage = jev.Usage()
    got = read(cat, listings[:args.limit], usage=usage)
    for l in listings[:args.limit]:
        print(f"  {l['name'][:60]:60} -> {got.get(str(l['id']))}")
    print(usage.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
