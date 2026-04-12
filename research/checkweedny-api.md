# CheckWeedNY COA API — Research

**Sprint question:** Can the CheckWeedNY API replace or augment Claude PDF parsing in the lab report flow?

---

## Overview

CheckWeedNY exposes a REST API (`https://api.checkweedny.com/v1`) that provides structured COA data for NY cannabis products, scraped and parsed from dispensary/processor sources. Auth via `X-API-Key` header.

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /v1/coas` | Search and filter COAs (paginated) |
| `GET /v1/coas/:id` | Single COA with full test data including terpene compounds |
| `GET /v1/labs` | Lab statistics and pass rates |
| `GET /v1/stats` | Dataset summary statistics |

## Dataset Scale (r018)

- **32,518 total COAs** as of 2026-04-12
- 671 unique clients, 532 unique brands, 26 unique labs
- Data spans 2008–April 2026

## /v1/coas List Schema (r020)

Key fields per record:
- `id` — string key, e.g. `buddega-23236`
- `brand_name`, `product_name`, `product_type`, `normalized_product_type`
- `batch_number`, `lab_name`, `test_date`
- `license_number`, `client_name`
- `pdf_url` — direct link to source PDF (r024)
- `parse_confidence` — 0.0–1.0 (r025)
- `total_terpenes_pct`, `dominant_terpene`, `terpene_count`
- Inline cannabinoids: `d9_thc_pct`, `thca_pct`, `total_thc_pct`, `cbd_pct`, `total_cbd_pct`, `cbg_pct`, `cbn_pct`, `cbc_pct`, `thcv_pct`, `d8_thc_pct`, `total_cannabinoids_pct`
- Pass/fail booleans: `metal_pass`, `microbial_pass`, `mycotoxin_pass`, `pesticide_pass`, `solvent_pass`

## /v1/coas/:id Detail Schema (r021)

Adds nested arrays not present in list:
- `terpenes: [{compound, value_pct}]` — individual compound percentages
- `pesticides: [{compound, result_ppm, loq_ppm, action_limit_ppm, pass}]`
- `solvents: [{compound, result_ppm, loq_ppm, action_limit_ppm, pass}]`
- `heavy_metals: {arsenic_ug_g, cadmium_ug_g, lead_ug_g, mercury_ug_g, ..., overall_pass}`
- `microbials: {total_aerobic_bacteria_cfu_g, total_yeast_mold_cfu_g, e_coli_detected, aspergillus_*_detected, overall_microbial_pass}`
- `mycotoxins: {aflatoxin_b1_ppm, ..., ochratoxin_a_ppm, overall_pass}`

### Terpene example (Berry Haze — 12 compounds)
```json
[
  {"compound": "Myrcene",      "value_pct": 0.8581},
  {"compound": "Caryophyllene","value_pct": 0.8010},
  {"compound": "Terpinolene",  "value_pct": 0.6484},
  {"compound": "Limonene",     "value_pct": 0.5411},
  ...
]
```

## Filter Parameters (r023)

| Parameter | Works? | Notes |
|---|---|---|
| `brand` | ✅ Yes | Most reliable, exact match |
| `limit` | ✅ Yes | Pagination |
| `offset` | ✅ Likely | Not tested |
| `product_name` | ❌ No | Returns full dataset |
| `license_number` | ❌ No | Returns full dataset |
| `product_type` | ❌ No | Returns full dataset |
| `batch_number` | ❌ No | Returns full dataset |

**Critical gap**: only `brand` filters work. Batch matching must be done client-side.

## Terpene Coverage (r022)

- **Flower / Concentrate**: terpene data present (Fernway/Tyson 2.0: 12–13 compounds, 3.95% total)
- **Ingestibles / Tinctures / Topicals / Beverages**: `terpene_count: null` in all tested samples
- Use `terpene_count` field in list response as a zero-cost null-check before fetching detail

## parse_confidence Field (r025)

| Value | Meaning | Action |
|---|---|---|
| ~1.0 | Excellent extraction | Use API data directly |
| 0.7 | Good | Use API data directly |
| 0.5 | Poor (garbled product name) | Fall back to Claude |
| null | Unknown | Fall back to Claude |

## Recommended Integration Strategy (r026)

```
1. LOOKUP:  GET /v1/coas?brand=<brand>&limit=200
            → paginate, match batch_number client-side

2. HIT with terpenes:
   - parse_confidence >= 0.7 AND terpene_count > 0
   → GET /v1/coas/:id for compound-level terpenes
   → map to COAExtraction model directly
   → skip Claude entirely ✅

3. HIT without terpenes:
   - terpene_count is null (common for non-flower)
   → fetch pdf_url → run through existing Claude parser
   → still saves user from uploading the PDF manually ✅

4. MISS (brand not in dataset, or brand mismatch):
   → existing upload+parse flow unchanged
```

## Risks

- **r027**: `brand` is the only filter. Brand name in our DB must exactly match CheckWeedNY's `brand_name`. No batch-level search endpoint.
- **r028**: Terpene data is null for most ingestibles/tinctures/topicals — the product categories where terpene lookup would matter most for terpenomics are the least covered.
