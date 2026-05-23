"""
scraper_common.py — Shared utilities for all terpenomics listing scrapers.

Scrapers import this via:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../scripts'))
    from scraper_common import ...
"""

import csv
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
    "variant",
    "price_cents",
    "thc_percent",
    "cbd_percent",
    "classification",
    "in_stock",
    "product_url",
    "image_url",
    "scraped_at",
    "description",
    "subtype",
    "strain",
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
    # Dutchie GraphQL type strings (title-case singular/plural variants)
    "Edible":            "edible",
    "Pre-Rolls":         "preroll",
    "CBD":               "tinctures",
    "Oral":              "tinctures",
    # Tymber/BLAZE product_categories
    "Vape Pens":         "vaporizers",
    "Disposables":       "vaporizers",
    "Preroll":           "preroll",
    "Infused Preroll":   "preroll",
    "Infused Pre-Rolls": "preroll",
    "Infused Flower":    "flower",
    "Concentrates":      "concentrate",
    "Drinks":            "edible",
    "Merchandise":       "merch",
    "Gift Cards":        "other",
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
    # Dutchie GraphQL type strings
    "Edible":       "edible",
    "Pre-Rolls":    "preroll",
    "CBD":          "tinctures",
    "Oral":         "tinctures",
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

_MG_RE = re.compile(r'^(\d+(?:\.\d+)?)\s*mg$', re.I)

def normalize_variant(v: str) -> str:
    """Normalize variant strings for cross-source consistency.

    Converts ≥500mg to grams (e.g. 500mg → 0.5g) since vape carts/concentrates
    are measured in grams by some sources and mg by others.
    Keeps 100mg/200mg/etc. as-is (standard edible doses).
    """
    m = _MG_RE.match(v.strip())
    if m:
        mg = float(m.group(1))
        if mg >= 500:
            return f"{mg / 1000:g}g"
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
