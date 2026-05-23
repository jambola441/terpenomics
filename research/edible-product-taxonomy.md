# Edible Product Taxonomy for Dispensary Listings

**Sprint context:** Same analysis as vape taxonomy — establishing what edible subtypes exist, which ones differentiate products in the identity tuple, and what the actual DB looks like.

---

## The Five Subcategories (r012)

| Subtype | Canonical name | Examples | Market share |
|---|---|---|---|
| Soft candy | `gummy` | Gummies, chews, ropes, pearls | ~79% nationally |
| Chocolate | `chocolate` | Bars, mini bars, chocolate pieces | ~6% nationally |
| Drink | `beverage` | Infused drinks, sparkling water, tea | ~6% nationally |
| Pill/capsule | `tablet` | ProTabs, micro-pills, fast-acting tabs | ~5% nationally |
| Other | `other` | Lozenges, pastilles, dissolvable powder, honey | ~4% |

All five are genuinely different purchase decisions — different shelf section, different dosing method, different onset time.

---

## Live DB Distribution (r013)

213 edible listings in the live `listings` DB, classified by name-token inference:

| Inferred subtype | Count | % |
|---|---|---|
| **Unclassified** | 97 | 46% |
| Gummy | 71 | 33% |
| Beverage | 16 | 7% |
| Chocolate | 14 | 7% |
| Tablet/capsule | 12 | 6% |
| Baked/other | 3 | 1% |

**The unclassified rate (46%) is nearly double the vape rate (26%).** This is not random noise — it's structural.

---

## Why Edibles Underperform Vapes on Token Parsing (r014)

Major gummy brands publish listings with no format token. Their brand IS their format:

| Brand | Listings unlabeled | What they make |
|---|---|---|
| Camino | 12 | Always gummies |
| Wyld | 9 | Always gummies |
| Off Hours | 12 | Gummies + ropes (mixed) |
| Lost Farm | 6 | Always chews/gummies |
| Wana | 6 | Gummies + fast-acting tabs |
| Eaton Botanicals | 8 | Gummies |
| Heavy Hitters (edibles) | 4 | Gummies |
| Good Tide | 3 | Gummies |
| Rythm | 3 | Gummies |
| Papa & Barkley | 2 | Gummies |

For these brands, a brand-level lookup table classifies faster and more accurately than regex on the name.

Remaining ambiguous brands:
- **Beboe** (5) — pastilles/lozenges, not gummies
- **1906** (4) — micro-pills ("Go Tin", "Genius") without token
- **Incredibles** (9) — makes BOTH gummies and chocolates, can't infer from brand alone
- **Myhi** (3) — dissolvable powder
- **Select** (2) — fast-acting tablets/strips

---

## Live Rosin Is Quality, Not Type (r015)

Many listings contain "Live Rosin" or "Live Resin" in the name:

- `Off Hours | Cherry Diesel | Live Rosin Gummies`
- `MFNY | Blueberry x Blueberry Muffin | Live Rosin Gummies`
- `Lost Farm | Dragon Fruit X Frose | Live Resin`

This is an extract-quality signal (premium oil source), not a format-type signal. Both are gummies. Using it as a type differentiator would fragment the gummy category unnecessarily:

```
# WRONG — over-splitting type
(Camino, "live-rosin-gummy", "Chill", "10mg")
(Camino, "gummy", "Chill", "10mg")
→ treated as different product types

# RIGHT — extract quality is extra_info
(Camino, "gummy", "Chill", "10mg", extract="live-rosin")
(Camino, "gummy", "Chill", "10mg", extract="distillate")
→ variants of same type
```

---

## CATEGORY_MAP Status

The existing `scraper_common.py` already handles top-level edible strings correctly:

```python
"Gummies":   "edible"   # ✓ but loses subtype
"Chocolates": "edible"  # ✓ but loses subtype
"Beverage":  "edible"   # ✓ but loses subtype
```

These need to map to the finer subtypes once the enum is expanded.

---

## Recommendation (r016)

Four subtypes for the `ProductCategory` enum (edible section):

```python
gummy     = "gummy"      # all soft candy forms
chocolate = "chocolate"  # bars, confections
beverage  = "beverage"   # drinks, sparkling water, tea
tablet    = "tablet"     # pills, caps, sublingual tabs
other     = "other"      # pastilles, honey, powder, strips
```

Update `CATEGORY_MAP`:
- `'Gummies'` → `'gummy'`
- `'Chocolates'` → `'chocolate'`
- `'Beverage'`, `'Beverages'`, `'Beverage Enhancer'` → `'beverage'`
- `'Tablets'` → `'tablet'`
- Add brand defaults for unlabeled gummy brands (Camino, Wyld, Lost Farm etc.)

---

## Claims

- **r012** — Five edible subcategories: gummy, chocolate, beverage, tablet, other
- **r013** — Live DB: 33% gummy by token, 46% unclassified, 7% beverage, 7% chocolate, 6% tablet
- **r014** — High unclassified rate is structural: major gummy brands never include type tokens
- **r015** — Live rosin/resin = extract quality signal, not type — keep it in extra_info
- **r016** — Recommendation: four subtypes + other, update CATEGORY_MAP and add brand defaults
