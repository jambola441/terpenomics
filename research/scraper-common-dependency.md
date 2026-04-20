# Scraper Commonalities & Shared Dependency

**Research question:** What do the two scraping scripts share, and what should live in a common module?

## Scripts examined

| Script | Source |
|--------|--------|
| `prototypes/travel-agency-scraper/scrape.py` | Leaflogix/Remix turbo-stream site |
| `prototypes/alleaves-scraper/scrape.py` | Alleaves POS API (two-pass: items + inventory) |
| `scripts/import_listings.py` | Consumer of both scrapers' CSV output |

---

## Shared surface — verbatim or near-verbatim

### 1. CSV schema (exact match)
Both scrapers output the same 14 columns in the same order:
```
dispensary_slug, sku, product_uuid, name, brand, category, variant,
price_cents, thc_percent, cbd_percent, classification, in_stock, product_url, scraped_at
```
One calls it `CSV_HEADERS`, the other `CSV_COLUMNS` — same list.

### 2. `write_csv(rows, path)`
Functionally identical in both — `csv.DictWriter` with those headers, `newline=""`, `encoding="utf-8"`. The only difference: travel-agency passes `extrasaction="ignore"`, Alleaves doesn't need it.

### 3. `CATEGORY_MAP`
Both map raw source categories → the same internal enum (flower, preroll, cart, concentrate, edible, tincture, topical, merch, other). Keys differ (source-specific raw strings), values are identical. The combined map is a superset.

### 4. `scraped_at` generation
Both use `datetime.now(timezone.utc).isoformat()` — identical one-liner, no reason to diverge.

### 5. Pagination pattern (structural, not verbatim)
Both use: while True → fetch page → break on empty/partial → accumulate → sleep(). Structurally identical, but the fetch function signature and params differ enough that extracting a shared paginator would require a callback protocol — marginal value at 2 scrapers.

### 6. Deduplication by set
Both maintain a `seen_*: set[str]` and skip duplicates. Key differs (SKU slug vs `id_item`).

---

## What stays scraper-specific

| Concern | Why it can't be shared |
|---------|----------------------|
| Auth | Each source has a different auth scheme (none, cookie-based, JWT) |
| Fetch/parse logic | Turbo-stream decoding vs Kendo form-encoded API |
| `normalise()` | Source-specific field names and semantics |
| Dedup key | Slug, `id_item`, or whatever the next source uses |
| Rate limit delay | Source-appropriate (1.0s vs 0.3s) |

---

## Proposed: `scripts/scraper_common.py`

A minimal shared module. Deliberately thin — no abstraction of pagination or fetch:

```python
# scripts/scraper_common.py

import csv
import re
from datetime import datetime, timezone

CSV_COLUMNS = [
    "dispensary_slug", "sku", "product_uuid", "name", "brand", "category",
    "variant", "price_cents", "thc_percent", "cbd_percent", "classification",
    "in_stock", "product_url", "scraped_at",
]

CATEGORY_MAP = {
    # Alleaves keys
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
    # Travel Agency keys (lowercase)
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
    if not raw:
        return "other"
    top = raw.split(" > ")[0].strip()
    return CATEGORY_MAP.get(top, CATEGORY_MAP.get(top.lower(), "other"))


def slugify(text: str) -> str:
    """General-purpose slug: spaces/punctuation → hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def store_slug(text: str) -> str:
    """Storefront URL slug: apostrophes dropped rather than hyphenated."""
    text = re.sub(r"['`]", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_csv(rows: list[dict], path: str) -> int:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
```

Each scraper imports what it needs:
```python
from scraper_common import CSV_COLUMNS, map_category, store_slug, now_iso, write_csv
```

---

## Trade-offs

**For a shared module:**
- Eliminates ~40 lines of copy-pasted code (CSV_COLUMNS, write_csv, CATEGORY_MAP)
- Category map kept in one place — adding a new POS source adds keys to one file
- Scraper authors don't need to know the internal category enum

**Against / risks:**
- Adds a file-level import dependency between previously isolated scripts
- A bug in `scraper_common` breaks all scrapers simultaneously
- Solo project: the cost of divergence (copy-paste drift) is low vs a team codebase
- At 2 scrapers, the savings are real but modest (~40 lines)

**Verdict:** Worth doing — the CSV schema and category enum are clearly shared contracts, not incidental duplication. Keep the module minimal: no pagination abstractions, no base-class patterns.

---

## Claim IDs
- r001, r002, r003, r004, r005
