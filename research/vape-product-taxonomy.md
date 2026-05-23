# Vape Product Taxonomy for Dispensary Listings

**Sprint question context:** Product identity tuple uses `type` as a differentiator. This research establishes what vape subtypes exist, which ones are meaningful for product matching, and what the actual data looks like.

---

## The Three Subcategories (r006)

| Subtype | Canonical name | Description | Battery |
|---|---|---|---|
| 510-thread cartridge | `cart` | Pre-filled oil tank, screws onto any 510 battery | Sold separately, universal |
| All-in-one / Disposable | `all-in-one` | Integrated battery + oil, discard whole unit | Built-in, non-replaceable |
| Pod system | `pod` | Brand-specific cartridge snaps into proprietary battery | Sold separately, brand-locked |

Cart and all-in-one are genuinely different purchase decisions: different price point, different accessories needed, different compatibility.

---

## Terminology Synonyms (r007)

"All-in-one", "disposable", "AIO", and "all-in-one disposable" are all the same product type:

| Term | Example source |
|---|---|
| `All-in-one` | Bloom, Ayrloom, Fernway, B Noble |
| `Disposable [flavor]` | Edie Parker |
| `AIO` | PAX |
| `All-in-one Disposable/Reusable` | Eureka |
| `All-inone` | Bloom (typo) |
| `Ail-in-one` | Heavy Hitters (typo) |

All should map to the same canonical value `all-in-one`.

---

## Actual Data Distribution (r008)

From the live `listings` DB, 238 rows in `scraped_category = 'vaporizers'`:

| Inferred subtype | Count | % |
|---|---|---|
| all-in-one / disposable | 112 | 47% |
| cart / 510 | 55 | 23% |
| unclassified | 61 | 26% |
| pod | 5 | 2% |
| battery / kit | 5 | 2% |

The unclassified 26% are mostly Bloom and Cannabals listings that publish no format token — just `Brand | Strain`. PAX uses `AIO`/`Cart` tokens that need extended matching patterns.

---

## Model vs Pipeline Gap (r009)

`ProductCategory` enum in `models.py` already has both `vaporizers` and `cart` as distinct values. But `scraper_common.py` maps everything to `vaporizers`:

```python
# Current — everything collapses
"Cartridges":            "vaporizers",
"All-in-one Disposable": "vaporizers",
"vape":                  "vaporizers",
```

The `cart` enum value is latent design intent that was never wired up.

---

## Risk: 26% Can't Be Parsed From Name Alone (r010)

Bloom and Cannabals publish listings like:
- `Bloom | Blue Cookies` (no format token)
- `Cannabals | Cereal Milk` (no format token)

For these, subcategorization requires either:
- A brand-level lookup table (`Bloom` → always cart? always AIO? mixed?)
- Manual tagging
- Accepting `unknown` as a valid subtype value

---

## Recommendation (r011)

Replace `vaporizers` enum value with three subtypes:

```python
class ProductCategory(str, Enum):
    flower     = "flower"
    cart       = "cart"        # 510-thread cartridge
    all_in_one = "all-in-one"  # disposable / AIO
    pod        = "pod"         # brand-specific pod
    edible     = "edible"
    concentrate = "concentrate"
    preroll    = "preroll"
    tinctures  = "tinctures"
    topical    = "topical"
    merch      = "merch"
    other      = "other"
```

Update `CATEGORY_MAP` to route:
- `'Cartridges'`, `'510'`, `'Reload Cartridge'`, `'Classic Preload'`, `'Reload'` → `'cart'`
- `'All-in-one Disposable'`, `'All-in-one'`, `'Disposable'`, `'AIO'` → `'all-in-one'`
- `'Pod'`, `'Live Rosin Pod'` → `'pod'`

---

## Claims

- **r006** — Three primary vape subcategories: cart, all-in-one, pod
- **r007** — All-in-one / disposable / AIO are synonymous
- **r008** — Live DB: 47% AIO, 23% cart, 26% unclassified, 2% pod, 2% battery
- **r009** — `cart` enum value already in models.py but pipeline never populates it
- **r010** — Risk: 26% of vape listings have no parseable format token
- **r011** — Recommendation: split vaporizers into cart / all-in-one / pod in enum + CATEGORY_MAP
