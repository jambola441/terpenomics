"""
scraper_common.py — Shared utilities for all terpenomics listing scrapers.

Scrapers import this via:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../scripts'))
    from scraper_common import ...
"""

import csv
import json
import os
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# CSV schema — single source of truth for all scrapers and import_listings.py
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "dispensary_slug",
    "sku",
    "batch_id",
    "name",
    "brand",
    "category",
    "raw_category",   # source string before map_category — makes CATEGORY_MAP gaps diagnosable
    "variant",
    "price_cents",
    "classification",
    "in_stock",
    "product_url",
    "image_url",
    "scraped_at",
    "description",
    "subtype",
    "strain",
    "product_line",
]

# ---------------------------------------------------------------------------
# Category map — merged superset of all known POS / website category strings
# ---------------------------------------------------------------------------

CATEGORY_MAP: dict[str, str] = {
    # Alleaves top-level categories (title-case)
    "Flower":                   "flower",
    "Pre-Roll":                 "preroll",
    "Vaporizers":               "vaporizers",
    "Concentrate":              "concentrate",
    "Edibles":                  "edible",
    "Tinctures":                "tinctures",
    "Topicals":                 "topical",
    "Accessories":              "merch",
    "Apparel":                  "merch",
    "Dog Treats":               "other",
    # Alleaves sub-category names (returned directly when no parent prefix)
    "Gummies":                  "edible",
    "Chocolate":                "edible",
    "Sublingual":               "tinctures",
    "Chocolates":               "edible",
    "Beverage":                 "edible",
    "Tablets":                  "edible",
    "Cartridges":               "vaporizers",
    "All-in-one Disposable":    "vaporizers",
    "Vaporizer Battery":        "vaporizers",
    "Single Pre-Rolls":         "preroll",
    "Pre-Roll Packs":           "preroll",
    "Infused Single Pre-Rolls": "preroll",
    "Infused Pre-Roll Packs":   "preroll",
    "Topical":                  "topical",
    "Shirts":                   "merch",
    "Uncategorized":            "other",
    # Dutchie GraphQL / Flowhub title-case strings
    "Edible":            "edible",
    "Pre-Rolls":         "preroll",
    "CBD":               "tinctures",
    "Oral":              "tinctures",
    "Live Rosin":        "concentrate",
    "Live Resin":        "concentrate",
    "Pills":             "edible",
    "Capsules":          "edible",
    # Dutchie Plus SCREAMING_SNAKE_CASE category strings
    "FLOWER":            "flower",
    "PRE_ROLLS":         "preroll",
    "VAPORIZERS":        "vaporizers",
    "EDIBLES":           "edible",
    "TINCTURES":         "tinctures",
    "TOPICALS":          "topical",
    "CONCENTRATES":      "concentrate",
    "ACCESSORIES":       "merch",
    "APPAREL":           "merch",
    # Tymber/BLAZE product_categories
    "Flowers":                 "flower",
    "Infused Flower":          "flower",
    "Vape Pens":               "vaporizers",
    "Vape AIOs":               "vaporizers",
    "Vape Carts":              "vaporizers",
    "Vape Carts (510 Thread)": "vaporizers",
    "Vape Disposables":        "vaporizers",
    "Vape Pods":               "vaporizers",
    "Disposables":             "vaporizers",
    "Pre Rolls":               "preroll",
    "Preroll":                 "preroll",
    "preroll":                 "preroll",
    "Infused Preroll":         "preroll",
    "Infused Pre-Roll":        "preroll",
    "Infused Pre-Rolls":       "preroll",
    "Concentrates":            "concentrate",
    "Drinks":                  "edible",
    "Merchandise":             "merch",
    "Gift Cards":              "other",
    # Travel Agency / Leaflogix (lowercase)
    "flower":       "flower",
    "vape":         "vaporizers",
    "vaporizer":    "vaporizers",
    "vaporizers":   "vaporizers",
    "vapes":        "vaporizers",
    "vape carts":   "vaporizers",
    "pre-roll":     "preroll",
    "pre-rolls":    "preroll",
    "pre-rolled flower": "preroll",
    "concentrate":  "concentrate",
    "concentrates": "concentrate",
    "edible":       "edible",
    "edibles":      "edible",
    "beverage":     "edible",
    "beverages":    "edible",
    "drinks":       "edible",
    "tincture":     "tinctures",
    "tinctures":    "tinctures",
    "topical":      "topical",
    "topicals":     "topical",
    "accessories":  "merch",
    "accessory":    "merch",
    "gear":         "merch",
    "cbd":          "tinctures",
}


def map_category(raw: str | None) -> str:
    """Map a raw source category string to the internal enum. Falls back to 'other'."""
    if not raw:
        return "other"
    top = raw.split(" > ")[0].strip()
    return CATEGORY_MAP.get(top, CATEGORY_MAP.get(top.lower(), "other"))


# ---------------------------------------------------------------------------
# Variant normalization
# ---------------------------------------------------------------------------

_MG_RE      = re.compile(r'^(\d+(?:\.\d+)?)\s*(?:mg|milligrams?)$', re.I)
_GRAM_RE    = re.compile(r'^(\d+(?:\.\d+)?)\s*grams?$', re.I)
_G_RE       = re.compile(r'^(\d*\.?\d+)\s*g$', re.I)
_OZ_FRAC_RE = re.compile(r'^(\d+)/(\d+)\s*oz\.?(?:\|.*)?$', re.I)
_OZ_WHOLE_RE = re.compile(r'^(\d+(?:\.\d+)?)\s*(?:oz\.?|ounces?)$', re.I)
_OZ_WORD_MAP = {
    "ounce":              28,
    "halfounce":          14,
    "quarterounceflower":  7,
}

_OZ_PER_G = 28  # cannabis convention: 1 oz = 28g


# Categories whose variant is a DOSE, not a physical weight. For these, mg is the
# canonical unit at every magnitude and ounces are package volume — so the
# weight-oriented conversions below must not run (they were turning a 1000mg
# tincture into "1g" and a 12oz beverage into "336g").
_DOSE_CATEGORIES = {"edible", "tinctures"}

# Categories whose variant is a physical WEIGHT. These stay in grams at every
# magnitude: a 0.4g pre-roll rendered as "400mg" sits inconsistently beside its
# own 0.5g and 0.6g siblings, and reads as a dose it is not.
_WEIGHT_CATEGORIES = {"flower", "preroll", "vaporizers", "concentrate"}


def normalize_variant(v: str, category: str | None = None) -> str:
    """Normalize variant strings for cross-source consistency.

    Canonical form: mg for <0.5g, grams (compact) for ≥0.5g.
      500mg       → 0.5g   (≥500mg converted to grams)
      100mg       → 100mg  (standard edible dose, kept as-is)
      1.5g        → 1.5g
      0.3g        → 300mg  (<0.5g converted to mg)
      1.5 grams   → 1.5g   (spelled-out collapsed)
      1/8oz       → 3.5g   (fractional ounces → grams)
      1oz         → 28g    (whole ounces → grams)
    Fluid ounces (fl oz) are left unchanged.

    `category` pins the unit to what the category actually measures:
      - dose categories (edible, tinctures): mg stays mg at any magnitude and oz
        stays oz, so "1000mg" and "12oz" survive instead of becoming "1g"/"336g".
      - weight categories (flower, preroll, vaporizers, concentrate): grams at
        any magnitude, so "0.4g" stays "0.4g" instead of becoming "400mg" and
        "350mg" becomes "0.35g".
    Callers that don't know the final category omit it and keep the legacy
    magnitude-based behavior.
    """
    v = v.strip()
    cat = (category or "").strip().lower()
    dose, weight = cat in _DOSE_CATEGORIES, cat in _WEIGHT_CATEGORIES
    if not dose:
        # Fractional ounces: "1/8oz", "1/4oz", "1/2oz", "1/2oz.|14g"
        m = _OZ_FRAC_RE.match(v)
        if m:
            grams = (int(m.group(1)) / int(m.group(2))) * _OZ_PER_G
            return f"{grams:g}g"
        # Whole/decimal ounces: "1oz", "3.0 ounces" — but not "fl oz"
        m = _OZ_WHOLE_RE.match(v)
        if m:
            grams = float(m.group(1)) * _OZ_PER_G
            return f"{grams:g}g"
        # Word forms: "ounce", "halfounce", "quarterounceflower"
        g = _OZ_WORD_MAP.get(v.lower().replace(" ", ""))
        if g is not None:
            return f"{g}g"
    # Gram forms
    m = _GRAM_RE.match(v) or _G_RE.match(v)
    if m:
        grams = float(m.group(1))
        if grams > 0 and grams < 0.5 and not weight:
            return f"{round(grams * 1000):g}mg"
        return f"{grams:g}g"
    m = _MG_RE.match(v)
    if m:
        mg = float(m.group(1))
        if weight or (mg >= 500 and not dose):
            return f"{mg / 1000:g}g"
        return f"{mg:g}mg"
    return v


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Brand normalization
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Lowercase and strip punctuation — used for loose brand matching."""
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def _cap_score(s: str) -> float:
    """Fraction of alphabetic chars that are uppercase."""
    alpha = [c for c in s if c.isalpha()]
    if not alpha:
        return 0.0
    return sum(1 for c in alpha if c.isupper()) / len(alpha)


def canonical_brands(raw_brands: set[str]) -> dict[str, str]:
    """Return {raw_brand: canonical_brand}.

    Brands that normalize to the same string (case/punct-insensitive) are
    collapsed to the variant with the highest uppercase fraction.
    Ties broken by longer string (preserves punctuation like apostrophes/periods).
    """
    groups: dict[str, list[str]] = {}
    for b in raw_brands:
        groups.setdefault(_norm(b), []).append(b)
    result: dict[str, str] = {}
    for variants in groups.values():
        best = max(variants, key=lambda v: (_cap_score(v), len(v)))
        for v in variants:
            result[v] = best
    return result


# ---------------------------------------------------------------------------
# Brand alias map (persistent, cross-scraper)
# ---------------------------------------------------------------------------

_ALIASES_CACHE: dict[str, str] | None = None
_ALIASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data/brand_aliases.json")


def _load_brand_aliases() -> dict[str, str]:
    global _ALIASES_CACHE
    if _ALIASES_CACHE is None:
        if os.path.isfile(_ALIASES_PATH):
            with open(_ALIASES_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            _ALIASES_CACHE = {k: v for k, v in raw.items() if not k.startswith("_")}
        else:
            _ALIASES_CACHE = {}
    return _ALIASES_CACHE


def apply_brand_aliases(rows: list[dict]) -> None:
    """Normalize brand names in-place using the persistent alias map."""
    aliases = _load_brand_aliases()
    if not aliases:
        return
    for row in rows:
        brand = row.get("brand") or ""
        if brand in aliases:
            row["brand"] = aliases[brand]


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """General-purpose slug: non-alphanumeric runs → hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def store_slug(text: str) -> str:
    """Storefront URL slug: apostrophes/backticks/slashes dropped (not hyphenated)."""
    text = re.sub(r"['`/]", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_stamp() -> str:
    """UTC timestamp suffix for output filenames — compact, filesystem-safe, and
    lexicographically chronological (so the newest file sorts last). e.g. 20260621T183000Z."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def stamped_path(path: str, stamp: str | None = None) -> str:
    """Insert a timestamp before the extension: foo/bar.csv -> foo/bar_20260621T183000Z.csv."""
    root, ext = os.path.splitext(path)
    return f"{root}_{stamp or run_stamp()}{ext}"


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], path: str) -> int:
    """Write rows to path using the canonical CSV schema. Returns row count."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
