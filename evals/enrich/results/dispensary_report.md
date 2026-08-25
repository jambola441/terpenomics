# Per-dispensary enrichment report — 24 stores, 18,264 listings

`suspects/100` counts audit findings per 100 listings. A finding is a row **worth reviewing**, not a row known to be wrong — there is no label behind it. Rank stores with it; do not read it as an error rate.

## Enriched — 24 stores, 18,264 listings

| store | listings | desc % | other % | strain fill | variant fill | suspects/100 |
|---|---:|---:|---:|---:|---:|---:|
| `garden-club-carroll-gardens` | 404 | 97.3 | 0.0 | 96.7 | 97.7 | **6.7** |
| `twisted-vibration-wburg` | 126 | 100.0 | 1.6 | 99.2 | 100.0 | **4.8** |
| `soulmate-fort-greene` | 254 | 100.0 | 0.0 | 99.2 | 100.0 | **4.7** |
| `kaya-bliss-brooklyn-heights` | 1,421 | 99.7 | 0.0 | 97.8 | 98.3 | **4.5** |
| `kaya-bliss-bay-ridge` | 1,933 | 100.0 | 0.0 | 99.2 | 99.4 | **3.8** |
| `bedford-club-bk` | 774 | 88.6 | 0.0 | 99.0 | 98.0 | **3.6** |
| `quality-control-brighton-beach` | 1,069 | 99.8 | 0.0 | 98.4 | 98.8 | **3.4** |
| `hold-up-roll-up` | 1,129 | 97.4 | 0.0 | 98.8 | 99.0 | **3.3** |
| `the-spot-bk` | 1,255 | 97.3 | 0.5 | 99.6 | 99.9 | **3.1** |
| `hii-nyc-bay-ridge` | 733 | 100.0 | 0.0 | 99.7 | 100.0 | **3.0** |
| `ignyte-red-hook` | 666 | 0.6 | 0.0 | 95.8 | 95.2 | **2.9** |
| `grow-together-bk` | 845 | 6.7 | 0.0 | 99.0 | 98.5 | **2.8** |
| `oc-dispensary-bk` | 1,950 | 98.2 | 0.0 | 99.3 | 99.4 | **2.8** |
| `hii-nyc-williamsburg` | 730 | 100.0 | 0.0 | 99.4 | 100.0 | **2.7** |
| `milligrams-greenpoint` | 535 | 100.0 | 0.0 | 99.4 | 100.0 | **2.6** |
| `rnr-dispensary-bk` | 693 | 98.0 | 0.0 | 98.5 | 98.0 | **2.5** |
| `dagmar-cannabis-wburg` | 263 | 82.9 | 0.0 | 99.0 | 100.0 | **2.3** |
| `stashmaster-nyc` | 1,591 | 100.0 | 0.0 | 99.2 | 98.6 | **2.3** |
| `greene-street-sheepshead-bay` | 319 | 100.0 | 0.0 | 100.0 | 100.0 | **2.2** |
| `herbology-bed-stuy` | 291 | 100.0 | 0.0 | 100.0 | 100.0 | **1.4** |
| `emerald-dispensary-carroll-gardens` | 200 | 100.0 | 0.0 | 100.0 | 100.0 | **1.0** |
| `by-any-other-name-bk` | 226 | 87.2 | 0.0 | 99.5 | 99.0 | **0.9** |
| `fireleaf-canarsie` | 423 | 100.0 | 0.0 | 99.8 | 100.0 | **0.9** |
| `emerald-dispensary-bk` | 434 | 100.0 | 0.0 | 100.0 | 100.0 | **0.2** |

## Suspects by check — enriched stores only

| store | category token conflict | unmapped category bucket | unmapped raw category | strain split | line leaked into strain | lineage as strain | variant anomaly | brand split | missing enrichment |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `garden-club-carroll-gardens` | 10 | 0 | 0 | 0 | 1 | 6 | 0 | 0 | 10 |
| `twisted-vibration-wburg` | 3 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 1 |
| `soulmate-fort-greene` | 0 | 0 | 0 | 1 | 0 | 9 | 0 | 0 | 2 |
| `kaya-bliss-brooklyn-heights` | 9 | 0 | 0 | 7 | 12 | 9 | 0 | 0 | 27 |
| `kaya-bliss-bay-ridge` | 15 | 0 | 0 | 8 | 24 | 13 | 0 | 0 | 13 |
| `bedford-club-bk` | 4 | 0 | 1 | 3 | 6 | 7 | 0 | 0 | 7 |
| `quality-control-brighton-beach` | 3 | 0 | 0 | 7 | 2 | 8 | 0 | 0 | 16 |
| `hold-up-roll-up` | 8 | 0 | 1 | 3 | 6 | 6 | 0 | 0 | 13 |
| `the-spot-bk` | 10 | 5 | 2 | 8 | 2 | 8 | 0 | 0 | 4 |
| `hii-nyc-bay-ridge` | 2 | 0 | 0 | 5 | 5 | 8 | 0 | 0 | 2 |
| `ignyte-red-hook` | 1 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 16 |
| `grow-together-bk` | 2 | 0 | 0 | 6 | 0 | 6 | 2 | 0 | 8 |
| `oc-dispensary-bk` | 2 | 0 | 0 | 21 | 11 | 5 | 1 | 0 | 14 |
| `hii-nyc-williamsburg` | 1 | 0 | 0 | 3 | 3 | 9 | 0 | 0 | 4 |
| `milligrams-greenpoint` | 0 | 0 | 0 | 1 | 0 | 10 | 0 | 0 | 3 |
| `rnr-dispensary-bk` | 5 | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 9 |
| `dagmar-cannabis-wburg` | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 2 |
| `stashmaster-nyc` | 6 | 0 | 0 | 5 | 7 | 9 | 0 | 0 | 10 |
| `greene-street-sheepshead-bay` | 1 | 0 | 0 | 0 | 0 | 6 | 0 | 0 | 0 |
| `herbology-bed-stuy` | 0 | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 |
| `emerald-dispensary-carroll-gardens` | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| `by-any-other-name-bk` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| `fireleaf-canarsie` | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 1 |
| `emerald-dispensary-bk` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Fleet totals — enriched stores only

| check | findings |
|---|---:|
| missing enrichment | 163 |
| lineage as strain | 125 |
| category token conflict | 85 |
| strain split | 85 |
| line leaked into strain | 85 |
| unmapped category bucket | 5 |
| unmapped raw category | 4 |
| variant anomaly | 3 |
| brand split | 0 |
