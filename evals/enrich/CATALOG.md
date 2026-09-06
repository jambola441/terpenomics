# Brand catalogs as source of truth — is it sound?

Measured 2026-08-30 against 18,806 active listings, 769 brands, 11,515 product
rows. The proposal: build a per-brand catalog of real products, then make
enrichment a **matching** problem — listing to catalog entry — rather than a
field-extraction problem.

## The short version

The instinct is right and the strongest argument for it is not the one you would
expect. It is not that enrichment is badly wrong; it is that **we currently have
no way to tell whether it is wrong.** The products view is derived from our own
model output, so it cannot validate itself. A catalog is the first independent
check this system would have.

The generation half needs correcting, though. Brand *marketing sites* are mostly
not catalogs. The thing that actually works is the storefront data endpoint
sitting behind them.

## 1. What is measurably broken today

Product rows that differ **only** in one field, where at least one member has it
blank — i.e. the same product split by an inconsistently extracted field:

| field | groups | product rows | listings affected | rows recovered if merged |
| --- | ---: | ---: | ---: | ---: |
| `product_line` | 1,002 | 2,376 | 4,415 | **1,374** |
| `strain` | 225 | 722 | 1,261 | 497 |
| `variant` | 158 | 651 | 1,088 | 493 |
| `subtype` | 0 | 0 | 0 | 0 |

1,374 spurious product rows is **12% of the products view**, from `product_line`
alone. Jetpacks is the clean example: `FJ-Mini / Blueberry Pancakes / 0.6g` and
`None / Blueberry Pancakes / 0.6g` are one product listed twice, because the line
was extracted on some stores and not others.

This is the failure a catalog fixes *by construction*. If the catalog says
Jetpacks makes "FJ-Mini Blueberry Pancakes 0.6g", every listing resolves to that
entry with the line attached, or does not resolve at all. There is no third state
where the line is silently absent.

`subtype` scoring 0 is the control: it is settled by curated tokens and rails, and
it does not split. That is the pattern working already, at a smaller scale.

## 2. Cardinality — the curation ladder is short

| | listings | share |
| --- | ---: | ---: |
| top 10 brands | 4,152 | 22.1% |
| top 50 brands | 10,300 | **54.8%** |
| top 100 brands | 13,278 | 70.6% |
| top 200 brands | 16,028 | 85.2% |

139 brands (18% of brands) have a single listing and account for 0.7% of the
fleet. So a catalog for **50 brands covers over half the data**, and the tail is
genuinely negligible. This is a vocabulary, not a long tail.

**Names do not repeat: 18,806 listings collapse to 17,239 distinct
(brand, normalised name) pairs — 1.09 listings per name.** Every store writes the
same product differently. That is the whole reason matching has to be fuzzy, and
the reason a catalog is worth more than a lookup table of names.

## 3. Where catalogs actually come from

Tested directly. **The brand marketing site is usually the wrong target.**

`https://www.pax.com/discover/new-york`, suggested as the example, has **zero
`Product` structured data** — only `BreadcrumbList` and `WebPage`. It renders 9
product *families* through Builder.io carousels marked "Loading…", with no SKUs,
strains, sizes or prices. It is a regional marketing hub. Page-scraping it yields
a category list, not a catalog.

What works is the storefront endpoint:

| brand | listings | site | catalog source | result |
| --- | ---: | --- | --- | --- |
| Ayrloom | 655 | Shopify | `/products.json` | **65 products, 174 SKUs** |
| STIIIZY | 515 | Shopify | `/products.json` | **153 products** |
| MFNY | 442 | — | 5 `Product` ld+json on the homepage | partial |
| Wyld | 219 | `/products/` | no schema on the homepage | needs a crawl |
| Jaunty, Ruby Farms | 940 | — | DNS/connection failure | unresolved |

Shopify's `/products.json` is free, unauthenticated, complete, and already
structured as product + variants. That is the acquisition strategy, tiered:

1. Shopify `/products.json` (and equivalents) — structured, no model needed
2. `Product` ld+json on the site — structured, no model needed
3. Rendered page + model extraction — for sites with neither
4. Hand-curated, seeded from our own listings — for brands with no usable site

## 4. Matching is tractable

Naive substring test on Ayrloom — no fuzzy matching, no aliases, no model:

**518 of 655 listings (79.1%) contain a catalog title verbatim.**

The 137 misses are informative and mostly cheap:

- `Rescue 1:1 Topical | 1000MG THC` vs catalog `rescue balm` — token overlap, not
  substring. **This is the topical product-line problem REFACTOR.md recorded as
  blocked**: Revive / Restore / Rescue / Releaf are Ayrloom product lines, and the
  catalog names them outright.
- `Alaskan Thunder Fuck` vs catalog `alaskan thunder fu*k` — the brand censors its
  own name. One alias.
- `Cranberry Apple`, `Beverage Enhancer` — not in the current 65, so either
  discontinued or renamed. This is the staleness problem, below.

The catalog also settles standing eval failures directly. `x-ayrloom-honeycrisp`
splits between 'Honeycrisp', 'Honeycrisp Cider' and 'Honeycrisp Apple Cider' on
every run; the catalog says **honeycrisp**. `holdup-044` wants
`strain: 'Pillow Talk'` and gets `'Pillow Talk Sleep'`; the catalog says
**pillow talk**.

## 5. What this does NOT establish

**We are not obviously over-splitting.** A first pass compared Ayrloom's 65
catalog products against our 194 product rows and read as 3× over-splitting. That
was wrong — their products nest variants. The fair comparison is **174 catalog
SKUs against our 194 rows, 1.1×.** Ayrloom is roughly right.

That weakens "enrichment is badly broken" and strengthens the real argument: we
could not have known it was roughly right. Every quality number in this repo is
computed from the same model output it is meant to judge. The catalog is the first
external referent.

## 6. Risks worth designing for, not around

- **Staleness.** Flower strains rotate seasonally; a catalog is a snapshot. It
  needs the same lapse model as verification — provenance (`source_url`,
  `fetched_at`, `method`) per entry, and a claim that expires rather than silently
  vouching for a menu that has moved on.
- **A new failure mode: confident wrong matches.** Today a bad answer is a wrong
  string. With a catalog, a bad answer is a *specific wrong SKU*, which reads as
  more authoritative and propagates further. "No match" must be a first-class
  outcome with a confidence threshold, not a fallback to the nearest entry.
- **Coverage is a layer, never a replacement.** 769 brands, and the tail will never
  have catalogs. The extraction path stays for everything that does not match.

## Proposed shape

`data/catalogs/<brand-slug>.json`, one file per brand, each entry carrying an id
and provenance. Then a `CatalogEnricher` that runs **before** the model in the
existing registry — the same position `MerchEnricher` occupies — returning
`(catalog_id, confidence, method)` and falling through to today's extraction when
confidence is below threshold. The verification layer already built then attaches
to catalog entries rather than to listings, which is where a human review is worth
far more: one sign-off covers every store carrying that product.

## Where to start

**Ayrloom.** 655 listings (the largest brand), a working Shopify endpoint, 79%
naive match before any tuning, and it is implicated in two standing eval failures
plus the topical product-line problem REFACTOR.md marked blocked. It exercises
acquisition, matching, staleness and verification in one brand, and if the pattern
does not pay there it will not pay anywhere.
