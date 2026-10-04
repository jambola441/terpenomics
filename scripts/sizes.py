"""
sizes.py — Read a product's size out of its text as numbers, not as a label.

`variant` is a string, and the same size is written many ways across stores and
across a brand's own catalog: ".6g", "0.6G", "5 Pack | 0.6g each", "5pk x 0.6g - 3.0g",
"10mg / 10 pack", "100MG". Matching a listing to a catalog entry needs to know that
"5pk x 0.6g" and "3g" are the same package, which is arithmetic — and arithmetic is
the one thing the decision model is documented to be bad at (jev.py). So it lives
here, deterministic and tested, and the model only ever sees products that already
passed a size check.

A Size carries what the text states and nothing it does not:

  grams     total net weight of the package (flower, preroll, vape, concentrate)
  mg        total THC in the package (edible, tincture, topical)
  pack      units in the package (5 prerolls, 10 gummies)
  unit_g    weight of one unit, when a pack states it (0.6g each)
  unit_mg   dose of one unit, when a pack states it (10mg each)

Totals are derived when the parts are present (5 x 0.6g -> 3g, 10 x 10mg -> 100mg),
because that is how a store and a brand end up writing the same package differently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import taxonomy

DOSE_CATEGORIES = taxonomy.categories_measured_by("dose")
WEIGHT_CATEGORIES = taxonomy.categories_measured_by("weight")

_NUM = r"(\d+(?:\.\d+)?|\.\d+)"
_GRAMS = re.compile(rf"{_NUM}\s*(?:g|gr|gram|grams)\b", re.I)
_MG = re.compile(rf"{_NUM}\s*(?:mg|milligrams?)\b", re.I)
# "5pk", "5 pack", "5-pack", "5ct", "10 count", "2 pcs", "5 x" (when followed by a size)
_PACK = re.compile(r"\b(\d+)\s*[-\s]?(?:pk|pack|packs|ct|count|pcs|pieces|pc)\b", re.I)
_PACK_X = re.compile(rf"\b(\d+)\s*(?:pk\s*)?x\s*{_NUM}\s*(g|mg)\b", re.I)
_EACH = re.compile(rf"{_NUM}\s*(g|mg)\s*(?:each|ea\.?|per\s+\w+)\b", re.I)
_OZ_FRAC = re.compile(r"\b(\d+)\s*/\s*(\d+)\s*(?:oz|ounce)\b", re.I)
# Compounds first (longest-first below), so "Eighth Ounce" is 3.5g and not also an
# ounce; a bare "ounce" is 28g only when nothing longer claimed it.
_OZ_WORDS = {"eighth ounce": 3.5, "eighth oz": 3.5, "quarter ounce": 7.0,
             "quarter oz": 7.0, "half ounce": 14.0, "half oz": 14.0, "halfounce": 14.0,
             "eighth": 3.5, "quarter": 7.0, "ounce": 28.0}
_FL_OZ = re.compile(rf"{_NUM}\s*fl\.?\s*oz\b", re.I)
_RATIO = re.compile(r"\b\d+\s*:\s*\d+(?:\s*:\s*\d+)*\b")
_PERCENT = re.compile(rf"{_NUM}\s*%")

OZ_GRAMS = 28.0   # cannabis convention, same as scraper_common
EDIBLE_PACKAGE_CAP_MG = 100.0


@dataclass(frozen=True)
class Size:
    grams: float | None = None
    mg: float | None = None
    pack: int | None = None
    unit_g: float | None = None
    unit_mg: float | None = None

    def is_empty(self) -> bool:
        return self == Size()

    def label(self) -> str:
        """A compact, stable rendering — the form written into `variant`."""
        parts = []
        if self.pack and self.pack > 1:
            parts.append(f"{self.pack}pk")
        if self.grams is not None:
            parts.append(f"{self.grams:g}g")
        elif self.mg is not None:
            parts.append(f"{self.mg:g}mg")
        return " ".join(parts)


def _floats(pattern: re.Pattern, text: str) -> list[float]:
    out = []
    for m in pattern.finditer(text):
        try:
            out.append(float(m.group(1)))
        except (TypeError, ValueError):
            continue
    return out


def parse(*texts: str | None, category: str | None = None) -> Size:
    """The size stated across `texts` (variant first, then name, then anything else).

    Potency is stripped before parsing: "THC 37.45%" and a "1:1" ratio are not sizes,
    and "10mg THC : 5mg CBD" names a dose split rather than a package.
    """
    text = " | ".join(t for t in texts if t)
    text = _PERCENT.sub(" ", _RATIO.sub(" ", text))
    cat = (category or "").strip().lower()

    pack = None
    unit_g = unit_mg = None
    m = _PACK_X.search(text)
    if m:
        pack = int(m.group(1))
        val = float(m.group(2))
        if m.group(3).lower() == "g":
            unit_g = val
        else:
            unit_mg = val
    if pack is None:
        packs = [int(p) for p in _PACK.findall(text)]
        pack = max(packs) if packs else None
    for m in _EACH.finditer(text):
        val = float(m.group(1))
        if m.group(2).lower() == "g" and unit_g is None:
            unit_g = val
        elif m.group(2).lower() == "mg" and unit_mg is None:
            unit_mg = val

    grams = _floats(_GRAMS, text)
    for m in _OZ_FRAC.finditer(text):
        num, den = int(m.group(1)), int(m.group(2))
        if den:
            grams.append(num / den * OZ_GRAMS)
    # Longest word first, consuming what it matched, so "half ounce" is 14g and is
    # not also read as "ounce" (28g) — and a fraction already read ("1/8 Ounce") is
    # consumed before the words are, for the same reason.
    lowered = _OZ_FRAC.sub(" ", text).lower()
    for word, g in sorted(_OZ_WORDS.items(), key=lambda kv: -len(kv[0])):
        lowered, hits = re.subn(rf"\b{word}\b", " ", lowered)
        if hits:
            grams.append(g)
    mgs = _floats(_MG, text)

    total_g = _total(grams, pack, unit_g, unit_below=1.0)
    # New York caps an edible package at 100mg, so a lone dose next to a pack count
    # is per piece whenever multiplying stays within the cap ("10mg / 10 pack" is
    # 100mg) and is the package total when it would not ("100mg 10pk" is 100mg).
    total_mg = _total(mgs, pack, unit_mg, unit_below=None, cap=EDIBLE_PACKAGE_CAP_MG)

    # A dose category is measured in mg and a weight category in grams; keep only the
    # unit the category actually sells by, so a gummy's "3.5g" piece weight or a
    # preroll's "1000mg" of infused rosin does not become the package size.
    if cat in DOSE_CATEGORIES and total_mg is not None:
        total_g = None
    if cat in WEIGHT_CATEGORIES:
        if total_g is None and total_mg is not None and total_mg >= 100:
            total_g = total_mg / 1000   # "500mg" cart -> 0.5g
        total_mg = None
    if pack == 1:
        pack = None
    return Size(grams=_round(total_g), mg=_round(total_mg), pack=pack,
                unit_g=_round(unit_g), unit_mg=_round(unit_mg))


def mg_mentions(*texts: str | None) -> list[float]:
    """Every distinct mg amount the texts name, potency and ratios stripped as parse()
    strips them — so a caller can tell one dose ("10mg x 10pk") from several
    ("150MG THC : 450MG CBD"), which parse() would otherwise reduce to its largest."""
    text = " | ".join(t for t in texts if t)
    text = _PERCENT.sub(" ", _RATIO.sub(" ", text))
    return sorted({round(v, 3) for v in _floats(_MG, text) if v > 0})


def _total(values: list[float], pack: int | None, unit: float | None, *,
           unit_below: float | None, cap: float | None = None) -> float | None:
    """The package total implied by the mentions.

    With a pack and a stated per-unit size, the total is their product. With a pack
    and several mentions, a pair where small x pack == large is unit and total
    ("5 Pack | .6g | 3g"). A lone mention next to a pack is a unit size when it is
    small (`unit_below`: "5pk 0.6g" is 3g) or when multiplying stays within `cap`
    (doses). Without a pack, the largest mention is the package — a listing that
    restates its size twice is common, one naming a smaller size inside is rare.
    """
    values = [v for v in values if v > 0]
    if pack and pack > 1 and unit:
        return pack * unit
    if pack and pack > 1 and values:
        smallest, largest = min(values), max(values)
        if len(values) > 1 and abs(smallest * pack - largest) <= 0.05 * largest:
            return largest
        if len(values) == 1:
            if unit_below is not None and smallest < unit_below:
                return pack * smallest
            if cap is not None and smallest * pack <= cap:
                return pack * smallest
        return largest
    return max(values) if values else None


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 3)


def same_size(a: Size, b: Size) -> bool | None:
    """True / False when both sides state a comparable size, None when either is silent.

    None is not False: a store that omits the size is not selling a different product.
    """
    if a.grams is not None and b.grams is not None:
        return abs(a.grams - b.grams) <= max(0.02, 0.03 * max(a.grams, b.grams))
    if a.mg is not None and b.mg is not None:
        return abs(a.mg - b.mg) <= max(0.5, 0.01 * max(a.mg, b.mg))
    if a.pack is not None and b.pack is not None:
        return a.pack == b.pack
    return None
