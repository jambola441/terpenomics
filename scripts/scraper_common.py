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
    "product_uuid",
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
    "scraped_at",
]

# ---------------------------------------------------------------------------
# Category map — merged superset of all known POS / website category strings
# ---------------------------------------------------------------------------

CATEGORY_MAP: dict[str, str] = {
    # Alleaves (title-case)
    "Flower":       "flower",
    "Pre-Roll":     "preroll",
    "Vaporizers":   "cart",
    "Concentrate":  "concentrate",
    "Edibles":      "edible",
    "Tinctures":    "tincture",
    "Topicals":     "topical",
    "Accessories":  "merch",
    "Apparel":      "merch",
    "Dog Treats":   "other",
    # Travel Agency / Leaflogix (lowercase)
    "flower":       "flower",
    "vape":         "cart",
    "vaporizer":    "cart",
    "pre-roll":     "preroll",
    "pre-rolls":    "preroll",
    "concentrate":  "concentrate",
    "concentrates": "concentrate",
    "edible":       "edible",
    "edibles":      "edible",
    "beverage":     "edible",
    "beverages":    "edible",
    "tincture":     "tincture",
    "tinctures":    "tincture",
    "topical":      "topical",
    "topicals":     "topical",
    "accessories":  "merch",
    "accessory":    "merch",
    "gear":         "merch",
    "cbd":          "tincture",
}


def map_category(raw: str | None) -> str:
    """Map a raw source category string to the internal enum. Falls back to 'other'."""
    if not raw:
        return "other"
    top = raw.split(" > ")[0].strip()
    return CATEGORY_MAP.get(top, CATEGORY_MAP.get(top.lower(), "other"))


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """General-purpose slug: non-alphanumeric runs → hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def store_slug(text: str) -> str:
    """Storefront URL slug: apostrophes/backticks dropped (not hyphenated)."""
    text = re.sub(r"['`]", "", text.lower())
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
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
