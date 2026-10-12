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
  * the store's description and its own category filing are in the state;
  * subtype and line narrow the options only on a confident answer (p >= NARROW_AT);
    an unsure one is left blank in the reading and the next question sees every value,
    so a wrong line cannot hide the right strain;
  * size is asked among the sizes of the product just picked, spelled out ("10pk
    100mg: 10 pieces, 100mg THC in the whole package"): a bare "100mg" then means the
    one package with that total, not every size the brand sells. An edible's mg is its
    total THC (or THCA) only, never CBD, CBN or other cannabinoids (owner, 2026-10-10):
    Ayrloom's "5mg THC : 5mg CBD" can is 5mg though stores size it "10mg".

The reading is the catalog's values, so the attribute join (catalog_match.CatalogIndex
.join) settles it without Jev; Jev no longer picks entries at matching. Each answer's
probability is kept on the reading (`p`), and the matcher trusts a join only when the
strain and size were read confidently (TRUST_AT) and the strain reads the same from the
name alone (trusted): a listing of a product the catalog
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
from functools import lru_cache
from pathlib import Path

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
# A size question with one package offered asks "this package or none": picking the
# package over none is enough (owner's reviews, 2026-10-11: 16 of 16 such picks under
# 0.9 were right, down to 0.55; the misses were weak "none" answers). Off until the owner
# picks the bar (spot checks: wrong picks ~7% at 0.5-0.6, ~2% at 0.6-0.7, <1% above): the
# default is the trust bar itself.
ONE_SIZE_AT = float(os.environ.get("CATALOG_READING_ONE_SIZE_AT", str(TRUST_AT)))

DESCRIPTION_CHARS = 1000
# A line option lists its strains when it has this many or fewer (line_strains).
LINE_STRAINS_SHOWN = int(os.environ.get("CATALOG_READING_LINE_STRAINS", "60"))

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
          "with that total or count. A package's mg is its total THC (or THCA) only, never CBD, "
          "CBN, CBG or other cannabinoids: a can of '5mg THC : 5mg CBD' is 5mg, even where the "
          "store's size field adds them up to 10mg. Choose none only if the listing states a total "
          "or count that none of these packages has.")

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

# Brand examples, from review decisions: {brand_slug: [{"listing", "size_field"?, "entry": selector}]},
# one store listing per catalog entry. A question shows a couple of them: from entries like the
# product being read whose answer is one of its options, nearest the listing's name first.
EXAMPLES_PATH = Path(__file__).resolve().parent.parent / "data" / "reading_examples.json"
EXAMPLES_SHOWN = 3
# The catalog field each question with examples answers. Subtype too (2026-10-12): a store
# that pastes its cart description under 'MFNY Skunk Live Resin Vape Pen | .5g' had the pen
# read as a cart at p 0.91 and trusted on the 0.5g cart; the brand's own 'Vape Pen' listings
# filed as all-in-one are what tells the two apart.
EXAMPLE_FIELDS = {"subtype": "subtype", "line": "product_line", "strain": "strain", "size": "variant"}
# Selector keys (catalog_fix's) -> catalog entry fields.
_SELECTOR = {"category": "category", "subtype": "subtype", "line": "product_line",
             "strain": "strain", "size": "variant"}


@lru_cache(maxsize=1)
def _examples() -> dict:
    try:
        data = json.loads(EXAMPLES_PATH.read_text())
    except FileNotFoundError:
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def brand_examples(slug: str | None, entries: list[dict]) -> list[tuple[dict, dict]]:
    """The brand's examples, each with the one active entry its selector names. An example
    naming no entry or several is left out, and so is a second listing for an entry."""
    out, seen = [], set()
    for ex in _examples().get(slug or "", []):
        sel = ex.get("entry") or {}
        hits = [e for e in entries
                if all((e.get(_SELECTOR[k]) or None) == (v or None) for k, v in sel.items())]
        if len(hits) != 1:
            print(f"  [warn] reading example {ex.get('listing')!r} names {len(hits)} entries; left out",
                  file=sys.stderr)
            continue
        key = hits[0].get("id") or id(hits[0])
        if key not in seen:
            seen.add(key)
            out.append((ex, hits[0]))
    return out


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:[.:/][a-z0-9]+)*", text.lower()))


def instructions_for(key: str, base: str, examples: list[tuple[dict, dict]], reading: dict,
                     values: list[str], name: str) -> str:
    """A question's instructions with up to EXAMPLES_SHOWN of the brand's examples (brand_examples):
    those whose entry is like the product read so far (its category, and its subtype and line
    where read) and whose answer is one of `values`, the listings sharing most words with `name`
    first."""
    field = EXAMPLE_FIELDS.get(key)
    if not field or not examples:
        return base
    offered, words = set(values), _words(name)
    near = []
    for ex, e in examples:
        if e.get(field) not in offered or e.get("category") != reading.get("category"):
            continue
        if any(reading.get(f) and e.get(f) != reading[f] for f in ("subtype", "product_line")):
            continue
        w = _words(ex["listing"])
        near.append((-len(w & words) / max(len(w | words), 1), len(near), ex, e))
    if not near:
        return base
    said = []
    for _, _, ex, e in sorted(near, key=lambda t: t[:2])[:EXAMPLES_SHOWN]:
        note = f" (size field {ex['size_field']})" if key == "size" and ex.get("size_field") else ""
        said.append(f"'{ex['listing']}'{note} is '{e[field]}'")
    return f"{base} Examples from this brand's listings: {'; '.join(said)}."


def spell_size(label: str, category: str | None, single: bool = False) -> str:
    """A catalog size with what it means: what a store's partial size is matched against.
    `single`: the product also comes in packs written "N × unit" (sizes.PACK_SIGN), so a
    size with no count is said to be one piece."""
    z = sizes.parse(label, category=category)
    if z.mg is not None and z.pack:
        return f"{label}: {z.pack} pieces, {z.mg:g}mg THC in the whole package (THC only)"
    if z.mg is not None:
        return f"{label}: {z.mg:g}mg THC in the whole package (THC only)"
    if z.grams is not None and z.pack:
        return f"{label}: {z.pack} pieces, {z.grams:g}g in total"
    if z.grams is not None and single:
        return f"{label}: one single piece of {z.grams:g}g"
    if z.grams is not None:
        return f"{label}: {z.grams:g}g in total"
    if z.ml is not None:
        # Volume-sized (MFNY's tinctures): the brand's mg is a per-batch lab total that
        # stores copy, so a listing's mg figure says nothing against this package.
        return (f"{label}: a {z.ml:g}mL bottle. Its THC in mg differs from batch to batch, so "
                f"a listing stating any mg figure, or no size at all, can be this package; only "
                f"a different volume rules it out")
    return label


def option_label(key: str, value: str, category: str | None, single: bool = False) -> str:
    if key == "category" and value in jev_classify.CATEGORY_CRITERIA:
        return f"{value}: {jev_classify.CATEGORY_CRITERIA[value]}"
    if key == "subtype":
        crit = jev_classify.SUBTYPE_CRITERIA.get(category or "", {})
        return f"{value}: {crit[value]}" if value in crit else value
    if key == "size":
        return spell_size(value, category, single)
    return value


def line_strains(line: str, pool: list[dict]) -> str:
    """A line option's strains, where it has at most LINE_STRAINS_SHOWN among the products
    still offered. The line is asked before the strain, and a brand's lines are often told
    apart only by which strains they carry (2026-10-12: MFNY's 'Classics Live Resin' is
    Chemdog, Sour Diesel, UK Cheese and Shishkaberry, sold as '... Live Resin Badder' like
    the 'Live Resin' line; STIIIZY's Liquid Diamonds pods beside its Original ones)."""
    strains = sorted({e["strain"] for e in pool if e.get("product_line") == line and e.get("strain")})
    if not strains or len(strains) > LINE_STRAINS_SHOWN:
        return ""
    return f" (its products: {', '.join(strains)})"


def base_state(brand: str, listing: dict) -> dict:
    state = {"brand": brand, "name": listing.get("name") or "",
             "store_size_field": listing.get("variant") or ""}
    if listing.get("store_category"):
        # The store's own filing: names often leave the format out ("Gelato | ROVE
        # Classics | 1g" is a cart, filed under Vaporizers).
        state["store_category"] = listing["store_category"]
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
        self.strain_values: list[str] = []

    def question(self, step: tuple, brand: str, examples: list = ()) -> tuple[dict, dict, list[str]] | None:
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
        single = key == "size" and any(sizes.pack_label(v) for v in values)
        for i, v in enumerate(values):
            options[f"o{i}"] = option_label(key, v, self.reading.get("category"), single)
            if key == "line":
                options[f"o{i}"] += line_strains(v, self.pool)
        return dict(base_state(brand, self.listing), **extra), \
            {key: jev.Choice(instructions_for(key, instructions, examples, self.reading, values,
                                              self.listing.get("name") or ""), options)}, values

    def answer(self, step: tuple, pick: str | None, p: float, values: list[str]) -> None:
        key, field, out, _ = step
        if key == "strain":
            self.strain_values = values
        if key == "size":
            self.reading["size_options"] = len(values)
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


def _check(self, pick: str | None, p: float) -> None:
    """Record the name-only strain answer (read, above)."""
    value = None if pick in (None, NONE) else self.strain_values[int(pick[1:])]
    self.reading["strain_from_name"] = value
    self.p["strain_from_name"] = round(p, 3)


_Walk.check = _check


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

    Listings are dicts with id, name, variant, description, store_category (the store's
    own filing, when known) and, for merch, category and subtype."""
    import catalog_match
    brand = catalog.get("brand_name") or ""
    entries = [e for e in catalog.get("entries") or [] if e.get("is_active", True)]
    examples = brand_examples(catalog.get("brand_slug"), entries)
    cache = cache or catalog_match.AnswerCache(f"reading.{catalog.get('brand_slug') or 'x'}")
    walks = [_Walk(l, entries) for l in listings
             if not merch_catalog.is_merch(l.get("category"), l.get("subtype"), l.get("name") or "", brand)]
    for step in STEPS:
        jobs, pending = [], []
        for w in walks:
            if w.done or w.failed:
                continue
            q = w.question(step, brand, examples)
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
    # The strain asked again from the name alone, among the same options. A store's
    # description is sometimes another product's, pasted (2026-10-10: MFNY's Superboof
    # badder carries the Gelato 41 description, and read as Gelato 41 at 0.96); when
    # the two answers differ, the reading is not trusted (trusted) and a person looks.
    jobs, pending = [], []
    for w in walks:
        if w.failed or not w.reading.get("strain") or not w.strain_values:
            continue
        state = {k: v for k, v in base_state(brand, w.listing).items() if k != "description"}
        state.update({k: w.reading[k] for k in ("category", "subtype", "product_line") if w.reading.get(k)})
        options = {NONE: "None of these", **{f"o{i}": v for i, v in enumerate(w.strain_values)}}
        question = {"strain": jev.Choice(instructions_for("strain", STRAIN_Q, examples, w.reading, w.strain_values,
                                                          w.listing.get("name") or ""), options)}
        key = _cache_key(state, question)
        hit = cache.get(key)
        if hit is not None:
            w.check(hit["pick"], hit["p"])
            continue
        jobs.append((state, question))
        pending.append((w, key))
    for (w, key), res in zip(pending, jev.ask_many(jobs, workers=workers, usage=usage) if jobs else []):
        if res is None:
            w.failed = True
            continue
        pick, p, _ = res.choice("strain")
        cache.put(key, {"pick": pick, "p": round(p, 4)})
        w.check(pick, p)
    cache.save()
    out = {}
    for w in walks:
        if w.failed:
            continue
        r = {f: w.reading.get(f) for f in ("category", "subtype", "strain", "product_line", "size")}
        for extra in ("strain_from_name", "size_options"):
            if extra in w.reading:
                r[extra] = w.reading[extra]
        if w.listing.get("store_category"):
            r["store_category"] = w.listing["store_category"]
        out[str(w.listing["id"])] = dict(r, p=w.p, by="catalog")
    return out


def trusted(reading: dict | None) -> bool:
    """Whether a catalog reading is sure enough for its join to be trusted: the strain
    and the size read at TRUST_AT or above, and the same strain read from the name
    alone (a store description is sometimes another product's). Anything less goes to
    review, where the fix is the catalog's (owner, 2026-10-10: keep it simple). A
    store's size field is no substitute: Ayrloom's 1:1 cans carry the THC + CBD total
    ("10mg" on a 5mg can).

    Category is not held to a bar: a wrong one already fails the join, since strain and
    size are offered within it. A reading not made against the catalog (enrichment's)
    has no probabilities and is not held to this."""
    if not reading or reading.get("by") != "catalog":
        return True
    p = reading.get("p") or {}
    if "strain_from_name" in reading and reading["strain_from_name"] != reading.get("strain"):
        return False
    return p.get("strain", 0.0) >= TRUST_AT and p.get("size", 0.0) >= size_bar(reading)


def size_bar(reading: dict) -> float:
    """The size's bar: ONE_SIZE_AT where the product offered one package and it was picked."""
    return ONE_SIZE_AT if reading.get("size_options") == 1 and reading.get("size") else TRUST_AT


def unsure_steps(reading: dict | None) -> list[str]:
    """The steps of a catalog reading answered below their bar, and "strain_from_name"
    when the name alone reads another strain (review queue detail)."""
    if not reading or reading.get("by") != "catalog":
        return []
    p = reading.get("p") or {}
    bar = {"size": size_bar(reading), **{k: NARROW_AT for k in SOFT}}
    out = [k for k, v in p.items() if k in ("strain", "size", *SOFT) and v < bar.get(k, TRUST_AT)]
    if "strain_from_name" in reading and reading["strain_from_name"] != reading.get("strain"):
        out.append("strain_from_name")
    return out


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
