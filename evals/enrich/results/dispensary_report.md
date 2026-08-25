# Per-dispensary enrichment report — 24 stores, 18,264 listings

`suspects/100` counts audit findings per 100 listings. A finding is a row **worth reviewing**, not a row known to be wrong — there is no label behind it. Rank stores with it; do not read it as an error rate.

## Enriched — 16 stores, 9,496 listings

| store | listings | desc % | other % | strain fill | variant fill | suspects/100 |
|---|---:|---:|---:|---:|---:|---:|
| `twisted-vibration-wburg` | 126 | 100.0 | 1.6 | 70.3 | 100.0 | **31.7** |
| `garden-club-carroll-gardens` | 404 | 97.3 | 0.0 | 96.7 | 97.7 | **6.7** |
| `kaya-bliss-bay-ridge` | 1,933 | 100.0 | 0.0 | 99.2 | 99.4 | **3.7** |
| `bedford-club-bk` | 774 | 88.6 | 0.0 | 99.0 | 98.0 | **3.6** |
| `ignyte-red-hook` | 666 | 0.6 | 0.0 | 95.8 | 95.2 | **2.9** |
| `grow-together-bk` | 845 | 6.7 | 0.0 | 99.0 | 98.5 | **2.8** |
| `hii-nyc-bay-ridge` | 733 | 100.0 | 0.0 | 99.7 | 100.0 | **2.7** |
| `hii-nyc-williamsburg` | 730 | 100.0 | 0.0 | 99.4 | 100.0 | **2.7** |
| `hold-up-roll-up` | 1,129 | 97.4 | 0.1 | 98.8 | 99.0 | **2.7** |
| `dagmar-cannabis-wburg` | 263 | 82.9 | 0.0 | 99.0 | 100.0 | **2.3** |
| `greene-street-sheepshead-bay` | 319 | 100.0 | 0.0 | 100.0 | 100.0 | **2.2** |
| `herbology-bed-stuy` | 291 | 100.0 | 0.0 | 100.0 | 100.0 | **1.4** |
| `emerald-dispensary-carroll-gardens` | 200 | 100.0 | 0.0 | 100.0 | 100.0 | **1.0** |
| `by-any-other-name-bk` | 226 | 87.2 | 0.0 | 99.5 | 99.0 | **0.9** |
| `fireleaf-canarsie` | 423 | 100.0 | 0.0 | 99.8 | 100.0 | **0.9** |
| `emerald-dispensary-bk` | 434 | 100.0 | 0.0 | 100.0 | 100.0 | **0.2** |

## Not enriched — 8 stores, 8,768 listings

Pass B never ran on these (the run was interrupted), so `strain` is empty and their suspect counts are almost entirely `missing_enrichment`. **These are not quality scores** — the stores are simply unprocessed. Re-run `enrich_csvs.py`; rows already answered are cached, so only the gaps cost.

| store | listings | desc % | other % | strain fill | variant fill | suspects/100 |
|---|---:|---:|---:|---:|---:|---:|
| `oc-dispensary-bk` | 1,950 | 98.2 | 0.0 | 0.0 | 98.8 | **100.8** |
| `milligrams-greenpoint` | 535 | 100.0 | 0.0 | 0.0 | 100.0 | **100.4** |
| `soulmate-fort-greene` | 254 | 100.0 | 0.0 | 0.0 | 99.2 | **96.1** |
| `quality-control-brighton-beach` | 1,069 | 99.8 | 0.0 | 0.0 | 100.0 | **95.8** |
| `the-spot-bk` | 1,255 | 97.3 | 2.3 | 0.0 | 90.8 | **93.1** |
| `kaya-bliss-brooklyn-heights` | 1,421 | 99.7 | 0.0 | 0.0 | 99.8 | **85.5** |
| `rnr-dispensary-bk` | 693 | 98.0 | 0.0 | 0.0 | 99.7 | **85.0** |
| `stashmaster-nyc` | 1,591 | 100.0 | 0.0 | 0.0 | 100.0 | **76.4** |

## Suspects by check — enriched stores only

| store | category token conflict | unmapped category bucket | unmapped raw category | strain split | line leaked into strain | lineage as strain | variant anomaly | brand split | missing enrichment |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `twisted-vibration-wburg` | 3 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 35 |
| `garden-club-carroll-gardens` | 10 | 0 | 0 | 0 | 1 | 6 | 0 | 0 | 10 |
| `kaya-bliss-bay-ridge` | 15 | 0 | 0 | 8 | 23 | 13 | 0 | 0 | 13 |
| `bedford-club-bk` | 4 | 0 | 1 | 3 | 6 | 7 | 0 | 0 | 7 |
| `ignyte-red-hook` | 1 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 16 |
| `grow-together-bk` | 2 | 0 | 0 | 6 | 0 | 6 | 2 | 0 | 8 |
| `hii-nyc-bay-ridge` | 2 | 0 | 0 | 5 | 3 | 8 | 0 | 0 | 2 |
| `hii-nyc-williamsburg` | 1 | 0 | 0 | 3 | 3 | 9 | 0 | 0 | 4 |
| `hold-up-roll-up` | 5 | 0 | 1 | 3 | 5 | 4 | 0 | 0 | 13 |
| `dagmar-cannabis-wburg` | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 2 |
| `greene-street-sheepshead-bay` | 1 | 0 | 0 | 0 | 0 | 6 | 0 | 0 | 0 |
| `herbology-bed-stuy` | 0 | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 |
| `emerald-dispensary-carroll-gardens` | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `by-any-other-name-bk` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| `fireleaf-canarsie` | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 1 |
| `emerald-dispensary-bk` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Fleet totals — enriched stores only

| check | findings |
|---|---:|
| missing enrichment | 112 |
| lineage as strain | 64 |
| category token conflict | 47 |
| line leaked into strain | 47 |
| strain split | 33 |
| unmapped raw category | 2 |
| variant anomaly | 2 |
| unmapped category bucket | 0 |
| brand split | 0 |
