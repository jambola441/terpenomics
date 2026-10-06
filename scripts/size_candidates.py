"""
size_candidates.py — Every size a listing's text could mean, with where each came from.

sizes.parse() reads one size out of a listing and settles ambiguous text with rules:
a lone weight beside a pack count is a unit's weight when it is under 1g, a dose is
per piece while the pack stays within New York's 100mg edible cap, and so on. The
rules are right most of the time and silently wrong the rest: "Sour Diesel - 32PK 1G
Prerolls" at $150 read as 1g put a 32-pack under the 1g product.

This module settles nothing. It lists the readings — the store's size field, the
name and the description each read as the pack total and as count x unit, a pack
count in one text times a size in another, and the sizes the matched product comes
in — so a caller can see when they disagree and have a model choose among them with
the text and the price in front of it. Nothing here changes what the pipeline stores.

A reading is the package total in the category's unit: grams for what sells by
weight, THC milligrams for what sells by dose (taxonomy.py). What a text states is
always a reading. What arithmetic adds — a lone figure beside a count read as the
pack's total, or as one unit's — is marked unlikely when the unit it implies does not
exist (a 0.03g pre-roll, a 0.2mg gummy, a 1000mg edible package). Unlikely readings
stay among the options; they only stop counting as a disagreement.

evals/sizes/ checks it against model readers who saw only the name and description of
1,000 listings: the size they believe is among the options for 597 of 598, and the code
settles on another size by itself for 2.

    from size_candidates import assess
    a = assess({"variant": "1g", "scraped_name": "Sour Diesel - 32PK 1G Prerolls",
                "scraped_category": "preroll"})
    a.status, a.values    # "conflict", [1.0, 32.0]

    python scripts/size_candidates.py report [--json out.json]   # active listings, read-only
"""

from __future__ import annotations

import argparse
import dataclasses
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import sizes  # noqa: E402

# A unit outside these does not exist: no pre-roll, pod or cart weighs under 0.2g or
# over 2g, no piece holds under 0.5mg of THC (Wyld's 20:1 gummies are that), no serving
# over 100mg.
MIN_UNIT_G, MAX_UNIT_G = 0.2, 2.0
MIN_UNIT_MG, MAX_UNIT_MG = 0.5, 100.0

_NUM = sizes._NUM
_UNITS = ("pre-roll", "preroll", "joint", "blunt", "cone", "dog", "mini", "gumm(?:y|ie)",
          "chew", "piece", "tablet", "tab", "pill", "capsule", "softgel", "drop", "mint", "bite",
          "chocolate", "square", "cookie", "brownie", "pearl", "lozenge", "can", "cup", "shot",
          "sachet", "packet", "pod", "cart", "cartridge", "stick", "serving", "dose")
# Not "unit": REMZzz's "100 mg/unit – 2.5mg THC Hash, 2.5mg THC/piece" is the package.
_UNIT_NOUN = "(?:" + "|".join(u.replace("-", r"[-\s]?") for u in _UNITS) + ")"     # "Pre Rolls" too
# A count takes the plural: "Gelato 33 Pre-Roll" is a strain, "5 Pre-Rolls" a pack.
_UNIT_NOUNS = "(?:" + "|".join(u.replace("-", r"[-\s]?").replace("gumm(?:y|ie)", "gummie") + "s"
                               for u in _UNITS) + ")"
_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "twenty": 20, "thirty": 30, "forty": 40}
_WORD = "(?:" + "|".join(_WORDS) + ")"
# Pack counts, more of them than sizes.parse reads: "2 - Pack", "10 gummies", "| 10 Bite
# size Cookies", "five 0.5g pre-rolls", "pack of 5".
_PACK = re.compile(r"\b(\d+)\s*-?\s*(?:pk|pack|packs|ct|count|pcs|pc)\b", re.I)
_COUNT_NOUN = re.compile(rf"\b(\d+)\s*-?\s*{_UNIT_NOUNS}\b", re.I)
_LEAD_COUNT = re.compile(rf"(?:^|[|(\[,]|\s-\s)\s*(\d+)\s+(?:[a-z][\w'-]*\s+){{1,2}}{_UNIT_NOUNS}\b", re.I)
_WORD_NOUN = re.compile(rf"\b({_WORD})\b[\s-]+(?:[\w.'-]+\s+){{0,3}}?{_UNIT_NOUNS}\b", re.I)
_PACK_OF = re.compile(rf"\bpack\s+of\s+(\d+|{_WORD})\b", re.I)
_WORD_PACK = re.compile(rf"\b({_WORD})[\s-]*(?:pack|pk|count|ct)\b", re.I)
# "0.5g x 5", the other order of sizes._PACK_X's "5 x 0.5g".
_X_PACK = re.compile(rf"{_NUM}\s*(g|gr|grams?|mg)\s*x\s*(\d+)\b(?!\s*(?:g|mg|%))", re.I)
# A figure given per unit ("0.5g each", "10mg per gummy", "5mgTHC/Serving"); "per package"
# is a total.
_PER_UNIT = re.compile(rf"{_NUM}\s*(g|gr|grams?|mg)\s*(?:thc\s*)?(?:each|ea\b\.?|"
                       rf"per\s+{_UNIT_NOUN}|/\s*{_UNIT_NOUN})", re.I)
# A count, a figure, the units: "five 0.5g pre-rolls", "Ten 10mg pearls" — each unit's figure.
_COUNT_SIZE_NOUN = re.compile(rf"\b(\d+|{_WORD})\s+{_NUM}\s*(g|gr|grams?|mg)\s+(?:[\w'-]+\s+){{0,2}}?{_UNIT_NOUNS}\b", re.I)
# A dose with no unit beside THC: "100THC:40CBG", Papa & Barkley's "THC1000".
_BARE_THC = re.compile(r"\b(\d+(?:\.\d+)?)\s*thc\b|\bthc\s*(\d+(?:\.\d+)?)\b(?!\s*(?:%|mg|g\b))", re.I)
# A dose missing its g: "Tiki Fruit Punch Rings - 100M Hash Rosin Nano Gummies".
_MG_TYPO = re.compile(r"\b(\d+(?:\.\d+)?)M\b")
# A bare standard weight as a whole segment ("X| Flamer | Hehe Haha | 3.5", "Runtz- 3.5- Flower").
_STANDARD_G = {0.5, 1.0, 2.0, 3.5, 7.0, 14.0, 28.0}
_SEGMENT = re.compile(r"\s*\|\s*|\s*[-–]\s+|\s+[-–]\s*")
# "1oz" (an ounce word or fraction is sizes.weight_mentions'), never a drink's "12 fl oz".
_OZ = re.compile(r"(?<![/\d.])(\d+(?:\.\d+)?|\.\d+)\s*oz\b", re.I)   # not the 8 of "1/8oz"
_GRAM_WORDS = {"one": 1, "two": 2, "three": 3, "seven": 7, "fourteen": 14}


@dataclass(frozen=True)
class Candidate:
    value: float          # the package total, in `unit`
    unit: str             # "g" or "mg"
    source: str           # "field", "name", "description", "catalog", or "name+field": a count in one, a size in the other
    reading: str          # how it was read: "as written", "as the pack total", "as 5 x 0.5g", ...
    likely: bool = True   # False: implies a unit that does not exist
    stated: bool = True   # False: arithmetic's reading, a count times a figure the text gives alone

    def label(self) -> str:
        return f"{self.value:g}{self.unit}"


@dataclass
class _Read:
    """What one text states: the readings it supports on its own, and the parts a
    reading across texts combines."""
    candidates: list[Candidate] = field(default_factory=list)
    packs: list[int] = field(default_factory=list)
    sizes: list[float] = field(default_factory=list)      # figures that may be a unit's, for another text's count
    per_unit: list[float] = field(default_factory=list)
    thc: bool = True                                      # False: the figures are another cannabinoid's


def unit_of(category: str | None) -> str | None:
    cat = (category or "").strip().lower()
    return "mg" if cat in sizes.DOSE_CATEGORIES else "g" if cat in sizes.WEIGHT_CATEGORIES else None


def same(a: float, b: float, unit: str) -> bool:
    """sizes.same_size's tolerance: a rounding apart is the same size."""
    if unit == "g":
        return abs(a - b) <= max(0.02, 0.03 * max(a, b))
    return abs(a - b) <= max(0.5, 0.01 * max(a, b))


# Pre-rolls, pods and carts are the units with a top weight; flower and concentrate
# come in jars of anything.
_UNIT_CAPPED = {"preroll", "vaporizers"}


def unit_exists(unit_size: float, unit: str, category: str | None = None) -> bool:
    if unit == "g":
        capped = (category or "").lower() in _UNIT_CAPPED if category else True
        return MIN_UNIT_G <= unit_size and (not capped or unit_size <= MAX_UNIT_G)
    return MIN_UNIT_MG <= unit_size <= MAX_UNIT_MG


def _times_likely(n: int, v: float, unit: str, category: str | None, thc: bool = True) -> bool:
    """Is "n units of v" a package that exists? The edible cap is on THC; a CBG
    capsule bottle can hold 1500mg."""
    if not unit_exists(v, unit, category):
        return False
    return not (thc and unit == "mg" and (category or "").lower() == "edible"
                and n * v > sizes.EDIBLE_PACKAGE_CAP_MG + 0.5)


def _clean(text: str | None) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    t = re.sub(r"(\d)\.\.(\d)", r"\1.\2", t)                                       # "92..4mg"
    t = re.sub(r"(\d|\.\d)\s*-\s*(grams?|gr|g|mg|milligrams?)\b", r"\1 \2", t, flags=re.I)  # "0.5-gram"
    t = re.sub(r"\b(" + "|".join(_GRAM_WORDS) + r")[\s-]+grams?\b",
               lambda m: f"{_GRAM_WORDS[m.group(1).lower()]} gram", t, flags=re.I)   # "one-gram"
    t = re.sub(r"\bhalf[\s-]*grams?\b", "0.5 gram", t, flags=re.I)                  # "half gram"
    t = re.sub(r"(\d),(\d{1,2})(?=\s*(?:g|gr|grams?|mg)\b)", r"\1.\2", t)      # "3,5g"
    t = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", t)                                # "1,000mg"
    t = re.sub(r"(\d)\s*(mg|g)(?=(?:thc|cbd|cbn|cbg|cbc|thcv)a?\b)", r"\1\2 ", t, flags=re.I)  # "10mgTHC"
    return sizes._PERCENT.sub(" ", sizes._RATIO.sub(" ", t))


def _in_unit(value: float, written: str, unit: str) -> float | None:
    """A figure written in g or mg, in the category's unit: a weight category reads
    "1000mg" as 1g (a cart's oil); a dose category has no use for grams (a gummy's
    piece weight)."""
    is_mg = written.lower().startswith("m")
    if unit == "mg":
        return value if is_mg else None
    return value / 1000 if is_mg else value


def _count(s: str) -> int:
    return int(s) if s.isdigit() else _WORDS[s.lower()]


def _distinct(values) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if v > 0 and not any(abs(v - o) <= max(1e-9, 0.005 * o) for o in out):
            out.append(round(v, 3))
    return out


def _totals(t: str, unit: str) -> tuple[list[float], bool]:
    """The figures a text states in the category's unit, potency and other cannabinoids
    aside, and whether they are THC (False when the text gives only a CBD or CBG amount)."""
    if unit == "g":
        no_drinks = sizes._FL_OZ.sub(" ", t)
        found = sizes.weight_mentions(t) + [v * sizes.OZ_GRAMS for v in sizes._floats(_OZ, no_drinks)]
        if not found:
            found = [v / 1000 for v in sizes._floats(sizes._MG, t) if v >= 100]
        if not found:
            segments = [s.strip() for s in _SEGMENT.split(t)]
            found = [float(s) for s in segments if re.fullmatch(r"\d+(?:\.\d+)?", s)
                     and float(s) in _STANDARD_G]
        return _distinct(found), True
    thc_only = sizes._NON_THC_MG.sub(" ", t)
    found = sizes._floats(sizes._MG, thc_only) or [
        float(a or b) for a, b in _BARE_THC.findall(thc_only)] or sizes._floats(_MG_TYPO, thc_only)
    if found:
        return _distinct(found), True
    return _distinct(sizes._floats(sizes._MG, t)), False


def _read(text: str | None, category: str | None, source: str) -> _Read:
    unit = unit_of(category)
    t = _clean(text)
    r = _Read()
    if not unit or not t.strip():
        return r

    def add(value, reading, likely=True, stated=True):
        r.candidates.append(Candidate(round(value, 3), unit, source, reading, likely, stated))

    settled = []
    for m in sizes._PACK_X.finditer(t):
        v = _in_unit(float(m.group(2)), m.group(3), unit)
        if v is not None:
            settled.append((int(m.group(1)), v))
    for m in _X_PACK.finditer(t):
        v = _in_unit(float(m.group(1)), m.group(2), unit)
        if v is not None:
            settled.append((int(m.group(3)), v))
    for m in _COUNT_SIZE_NOUN.finditer(t):
        v = _in_unit(float(m.group(2)), m.group(3), unit)
        if v is not None:
            settled.append((_count(m.group(1)), v))
    rest = _COUNT_SIZE_NOUN.sub(" ", _X_PACK.sub(" ", sizes._PACK_X.sub(" ", t)))
    r.per_unit = _distinct(v for m in _PER_UNIT.finditer(rest)
                           if (v := _in_unit(float(m.group(1)), m.group(2), unit)) is not None)
    rest = _PER_UNIT.sub(" ", rest)

    counts = [int(p) for rx in (_PACK, _COUNT_NOUN, _LEAD_COUNT) for p in rx.findall(t)]
    counts += [_count(p) for rx in (_WORD_NOUN, _PACK_OF, _WORD_PACK) for p in rx.findall(t)]
    r.packs = sorted({n for n in counts if n > 1} | {n for n, _ in settled if n > 1})
    totals, thc = _totals(rest, unit)
    r.thc = thc

    done = [(n * v, f"as {n} x {v:g}{unit}", v) for n, v in settled]
    done += [(n * v, f"as {n} x {v:g}{unit} each", v) for n in r.packs for v in r.per_unit]
    for value, reading, v in done:
        # Stated, but a typo can state a unit that does not exist: "5 x 05g" pre-rolls.
        add(value, reading, unit_exists(v, unit, category))
    # A total that restates a settled one is the same reading, and so is a unit's size
    # stated again without its "each" ("five 0.35g joints, 0.35g each"); one that is
    # neither is the text contradicting itself, and stays.
    units = [v for _, v in settled] + (r.per_unit if r.packs else [])
    totals = [v for v in totals if not any(same(v, d, unit) for d, _, _ in done)
              and not (done and any(same(v, u, unit) for u in units))]

    if r.packs and len(totals) > 1:
        # "5 Pack | .6g | 3g": the small figure is a unit of the large.
        for n in r.packs:
            for small in list(totals):
                if small not in totals:
                    continue
                big = next((b for b in totals if b > small and abs(small * n - b) <= 0.05 * b), None)
                if big is not None:
                    add(big, f"as {n} x {small:g}{unit}")
                    totals = [v for v in totals if v not in (small, big)]
                    r.sizes.append(small)
    # New York caps an edible package at 100mg of THC, so a stated figure above it is
    # not this package's (LEVEL's "98.1 mg | 2pk" with 196.2mg in the size field).
    capped = thc and unit == "mg" and (category or "").lower() == "edible"

    def under_cap(v):
        return not (capped and v > sizes.EDIBLE_PACKAGE_CAP_MG + 0.5)

    if r.packs and not done:
        for v in totals:
            add(v, "as the pack total", any(unit_exists(v / n, unit, category) for n in r.packs) and under_cap(v))
            for n in r.packs:
                add(n * v, f"as {n} x {v:g}{unit}", _times_likely(n, v, unit, category, thc), False)
    else:
        for v in totals:
            add(v, "as written", under_cap(v))
    r.sizes = _distinct(r.sizes + totals + r.per_unit + [v for _, v in settled])
    if not r.packs and not done:
        for v in r.per_unit:
            add(v, "per unit, count not stated", False, False)
    return r


def catalog_candidates(product_entries, category: str | None) -> list[Candidate]:
    """The sizes the matched product comes in, from its entries' variants."""
    unit = unit_of(category)
    out = []
    for e in product_entries or []:
        s = sizes.parse(e.get("variant"), category=e.get("category") or category)
        v = s.mg if unit == "mg" else s.grams
        if v is not None and not any(same(v, c.value, unit) for c in out):
            out.append(Candidate(v, unit, "catalog", f"a size this product comes in ({e.get('variant')})"))
    return out


def candidates(listing: dict, product_entries=None) -> list[Candidate]:
    """Every reading of the listing's size field, name and description, plus a count
    stated in one of them times a size stated in another ("1g" in the field, "- 2pk"
    in the name; "7 Pack" in the name, "0.5g pre-rolls" in the description), plus the
    matched product's sizes."""
    return _candidates(listing, product_entries)[0]


def _candidates(listing: dict, product_entries=None) -> tuple[list[Candidate], set[int]]:
    category = listing.get("scraped_category") or listing.get("category")
    texts = {"field": listing.get("variant"),
             "name": listing.get("scraped_name") or listing.get("name"),
             "description": listing.get("description")}
    reads = {src: _read(text, category, src) for src, text in texts.items()}
    unit = unit_of(category)
    sums = _cannabinoid_sums(texts["name"], texts["description"]) if unit == "mg" else []

    def summed(v):
        return any(same(v, total, unit) and not same(v, thc, unit) for thc, total in sums)

    # Nor is a figure the name or description states beside them: Ayrloom's "Pillow Talk"
    # drops say "1800mg per package/300mg THC per serving/1500mg CBN per serving".
    for r in reads.values():
        for c in list(r.candidates):
            if c.reading == "as written" and summed(c.value):
                r.candidates.remove(c)
                r.candidates.append(dataclasses.replace(
                    c, likely=False, reading="as written: THC and the other cannabinoids added together"))
    out = [c for r in reads.values() for c in r.candidates]
    for src, r in reads.items():
        for other, o in reads.items():
            if other == src:
                continue
            for n in o.packs:
                if n in r.packs:
                    continue
                for v in r.sizes:
                    out.append(Candidate(round(n * v, 3), unit, f"{other}+{src}",
                                         f"as {n} x {v:g}{unit} ({other}'s count, {src}'s size)",
                                         _times_likely(n, v, unit, category, r.thc)
                                         and not (src == "field" and summed(v)), False))
    counts = {n for r in reads.values() for n in r.packs}
    return out + catalog_candidates(product_entries, category), counts


_CANNABINOID = r"(thcv|thc|cbd|cbn|cbg|cbc)a?"
_AMOUNT_AFTER = re.compile(rf"{_NUM}\s*(?:mg|milligrams?)\s*(?:of\s+)?{_CANNABINOID}\b", re.I)     # "150MG THC"
_AMOUNT_BEFORE = re.compile(rf"\b{_CANNABINOID}\s*:?\s*{_NUM}\s*(?:mg|milligrams?)\b", re.I)    # "THC 100mg"


def _cannabinoid_sums(*texts) -> list[tuple[float, float]]:
    """(THC, THC + the other cannabinoids) for each text that names one THC amount beside
    others. A size field holding the sum is not the THC: Ayrloom's "150MG THC : 450MG CBD"
    drops are listed as 600mg, and its "5MG THC : 5MG CBN 10 Pack" as 10mg."""
    out = []
    for text in texts:
        t = _clean(text)
        amounts: dict[str, set[float]] = {}
        for m in _AMOUNT_AFTER.finditer(t):
            amounts.setdefault(m.group(2).lower(), set()).add(float(m.group(1)))
        for m in _AMOUNT_BEFORE.finditer(_AMOUNT_AFTER.sub(" ", t)):
            amounts.setdefault(m.group(1).lower(), set()).add(float(m.group(2)))
        thc = amounts.pop("thc", set())
        if len(thc) == 1 and amounts:
            (t_mg,) = thc
            out.append((t_mg, t_mg + sum(max(v) for v in amounts.values())))
    return out


def distinct_values(cands, unit: str | None = None) -> list[float]:
    """The different sizes among the candidates, a rounding apart counted once."""
    out: list[float] = []
    for c in sorted(cands, key=lambda c: c.value):
        if not any(same(c.value, o, unit or c.unit) for o in out):
            out.append(c.value)
    return out


@dataclass
class Assessment:
    candidates: list[Candidate]
    values: list[float]          # what the listing's own texts read as, distinct (likely readings)
    catalog: list[float]         # the matched product's sizes
    status: str                  # settled | conflict | off_catalog | silent

    def options(self) -> list[float]:
        """What a chooser would be offered: every reading and the product's sizes."""
        return distinct_values(self.candidates)


def assess(listing: dict, product_entries=None) -> Assessment:
    """settled: the listing's texts read one way, and the product comes in that size (or
    nothing is matched). conflict: they read two or more ways. off_catalog: one way, but
    not a size the matched product comes in. silent: the texts state no size.

    Readings implying a unit that does not exist count only when nothing else does: a
    "30 pk | 5MG THC" with no other figure is 5mg or 150mg, and both are asked about.
    Nor does a figure that, times a count the listing gives, is another figure its name
    or description states: Camino's "5mg THC per piece - 100mg THC per package" on a
    "[20pk]" names one package and its piece."""
    cands, counts = _candidates(listing, product_entries)
    own = [c for c in cands if c.source != "catalog"]
    cat = [c for c in cands if c.source == "catalog"]
    unit = cands[0].unit if cands else None
    likely = [c for c in own if c.likely]
    # The store's size field is not evidence here: stores fill it with count x the
    # name's figure, right or not ("20pc 20mg" micro-dose jellies listed as 400mg).
    stated = [c.value for c in likely if c.stated and c.source != "field"]
    pieces = {c.value for c in likely
              if any(same(c.value * n, b, unit) and not same(c.value, b, unit) for n in counts for b in stated)}
    values = distinct_values([c for c in likely if c.value not in pieces] or likely or own)
    catalog = distinct_values(cat)
    if not values:
        status = "silent"
    elif len(values) > 1:
        status = "conflict"
    elif catalog and not any(same(values[0], v, unit) for v in catalog):
        status = "off_catalog"
    else:
        status = "settled"
    return Assessment(cands, values, catalog, status)


# ---------------------------------------------------------------------------
# Report over the database (read-only)
# ---------------------------------------------------------------------------

def _product_entries(entries: list[dict]) -> dict[str, list[dict]]:
    """entry id -> the active entries of the product it belongs to."""
    by_product: dict[tuple, list[dict]] = {}
    for e in entries:
        if e.get("is_active"):
            by_product.setdefault((e["catalog_id"], e.get("product_key") or e["id"]), []).append(e)
    return {e["id"]: by_product.get((e["catalog_id"], e.get("product_key") or e["id"]), [e])
            for e in entries}


def report(json_out: str | None = None) -> None:
    import db_http
    cols = ("id,scraped_name,variant,description,scraped_category,scraped_brand,price_cents,"
            "catalog_entry_id")
    listings = db_http.select_all("listings", f"select={cols}&is_active=eq.true&order=id")
    entries = db_http.select_all("brand_catalog_entries",
                                 "select=id,catalog_id,product_key,variant,category,is_active&order=id")
    products = _product_entries(entries)
    statuses = ("settled", "conflict", "off_catalog", "silent")
    by_status, by_cat, rows = Counter(), Counter(), []
    for li in listings:
        if not unit_of(li.get("scraped_category")):
            continue
        a = assess(li, products.get(li.get("catalog_entry_id")))
        by_status[a.status] += 1
        by_cat[(li["scraped_category"], a.status)] += 1
        rows.append({"id": li["id"], "brand": li["scraped_brand"], "name": li["scraped_name"],
                     "variant": li["variant"], "price_cents": li["price_cents"], "status": a.status,
                     "values": [f"{v:g}" for v in a.values], "catalog": [f"{v:g}" for v in a.catalog],
                     "candidates": [{"size": c.label(), "source": c.source, "reading": c.reading,
                                     "likely": c.likely} for c in a.candidates]})
    total = sum(by_status.values())
    print(f"{total} sized active listings")
    for status, n in by_status.most_common():
        print(f"  {status:<12} {n:>6}  {n / total:6.1%}")
    print("\n  " + "category".ljust(12) + "".join(s.rjust(12) for s in statuses))
    for c in sorted({c for c, _ in by_cat}):
        print("  " + c.ljust(12) + "".join(str(by_cat[(c, s)]).rjust(12) for s in statuses))
    if json_out:
        Path(json_out).write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        print(f"\nwrote {len(rows)} rows to {json_out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report", help="status counts over active listings (read-only)")
    rp.add_argument("--json", help="write every listing's candidates here")
    args = ap.parse_args()
    if args.cmd == "report":
        report(args.json)


if __name__ == "__main__":
    main()
