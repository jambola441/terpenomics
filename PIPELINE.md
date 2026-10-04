# The listing pipeline — how it works and how to run it

Current as of 2026-10-04. What was wrong and what was measured is in
[PIPELINE_HEALTH.md](PIPELINE_HEALTH.md); this file is how to operate what is there now.

## The shape

```
dispensaries.json ──► scrape (per store) ──► enrich ──► CSV + .usage.json + .meta.json
                                                              │
                                    import_listings.py ◄──────┘   one transaction per store
                                      1. CSV values        (enrichment's answer)
                                      2. brand catalog     (trusted match overrides 1)
                                      3. human claim       (verified_fields overrides 2)
                                      + catalog_entry_id / _confidence / _method on every row
                                      + retire listings this scrape did not carry
                                        (never on a partial scrape)
```

`scripts/scrape.py --all` runs that for every store marked `active` in
`dispensaries.json`. `scripts/run_scrape_cron.py` wraps one sweep with a lock, a hard
timeout that kills the whole process tree, a heartbeat, and an optional alert.
`scripts/scrape_worker.py` runs that daily (09:00 ET by default).

## Where a listing's attributes come from

**Defined** in one place: [`scripts/taxonomy.py`](scripts/taxonomy.py). For each
category it declares the subtype rail, what `variant` measures, what `strain` means,
the rules the model is told, and which fields identify a product:

| category | variant measures | strain means | identity |
| --- | --- | --- | --- |
| flower, preroll, vaporizers, concentrate | weight (g, package total) | cultivar (vapes: or flavour) | subtype, line, strain, size |
| edible | dose (total mg; NY caps a package at 100mg) | flavour | subtype, line, strain, size |
| tinctures, topical | dose (total mg) | flavour / scent or blend | subtype, line, strain, size |
| merch | size + pack | — | subtype, attributes (colour/flavour), size |

Everything that used to declare these for itself — enrich's rails and prompts, the
brand prompt, the catalog importer, the merch enricher, both size normalisers — now
reads them from there. `scripts/test_taxonomy.py` pins the enrichment prompts byte
for byte, because a rail edit is a prompt edit and prompt edits moved the gold suite
every time one was made.

**Resolved**, strongest last:

| source | what it decides | written by |
| --- | --- | --- |
| scraper | name, brand, raw category, price, stock, raw size | `prototypes/*/scrape*.py` |
| enrichment | category, subtype, strain, product_line, variant | `scripts/enrich.py` (+ curated maps in `data/`) |
| **brand catalog** | subtype, strain, product_line — when the listing resolves to an entry by `exact`, `jev` (p ≥ threshold) or `manual` | `scripts/import_listings.py` via `catalog_match.resolve` |
| human claim | any verified field, bound to the scraped name | `scripts/verify_listing.py` |

A listing whose enrichment failed (`enrich_failed` in the CSV — a batch error, or no
API key) keeps its stored identity at import instead of having fallbacks written over
it. The size itself still comes from the model (`normalize_variant` standardises its
units); catalog matching and the bootstrap compare sizes as numbers parsed by
[`scripts/sizes.py`](scripts/sizes.py) (`5pk x 0.6g` = `3g`, `1/8 oz` = `3.5g`), so
two spellings of one size never split a product.

## Brand catalogs

A catalog is a brand's product list. A listing that resolves to an entry takes the
entry's identity, so every store carrying the product lands on one row of the
products view instead of three spellings of it.

**Where catalogs come from** — `brand_catalogs.source_method`:

| source | how | when to use |
| --- | --- | --- |
| `shopify_products_json` | `python scripts/brand_catalog.py fetch --brand X --domain x.com` then `push` | brand runs a Shopify store (Ayrloom, STIIIZY) |
| `listings_bootstrap` | `python scripts/catalog_bootstrap.py --brand X --write --push` | everyone else — built from the consensus of stores that carry the brand |
| `manual` | admin → Brand catalogs | fixes, additions |

The bootstrap groups a brand's listings across stores by (category, strain, line,
size), folds the product_line split (a line-less group joins the one lined group that
matches it on everything else), and keeps products at least two stores carry. On the
top 300 brands it proposes 3,135 products covering 64% of their listings. Each entry
records its `support` (how many stores) and the store names it was built from, so
those listings resolve exactly — no model call — on every later run.

**Pushing is additive.** `brand_catalog.py push` and `catalog_bootstrap.py --push`
insert new products and refresh metadata (store names, support, last seen), but never
overwrite a field you curated and never reactivate an entry you took out — a Shopify
re-fetch used to do both. Storefront products that vanish are deactivated; bootstrap
entries are not, since one quiet week at the stores is not a discontinuation.

**Postgres is the system of record.** Matching reads catalogs from the database
(`scripts/catalog_store.py`); the `data/catalogs/*.json` files are an offline
snapshot (`python scripts/catalog_store.py --snapshot`), not the read path. Edits in
the admin page apply on the next import — there is no export step to remember.

## Matching listings to catalogs — and where Jev fits

[`scripts/catalog_match.py`](scripts/catalog_match.py) resolves each listing:

1. **exact** — its normalised name is a catalog title or a recorded store name. Free.
2. **shortlist** — products ranked by token containment/overlap, filtered to the
   listing's category, softly to its subtype and size (a filter never empties the
   list on its own), with a hard veto when subtype *and* size both contradict.
3. **Jev** ([`scripts/jev.py`](scripts/jev.py)) picks which shortlisted product the
   listing is, or "none", with a probability for each:

   | probability | method | effect |
   | --- | --- | --- |
   | ≥ 0.85 (0.90 for bootstrap catalogs) | `jev` | identity taken from the entry |
   | 0.50 – threshold | `jev_review` | entry recorded, identity not taken — review it |
   | below | `none` | falls back to enrichment |

Jev is TypeSafe's decision model (`typesafe/jev-1.13`, pinned) on OpenRouter, using
the same `OPENROUTER_API_KEY`. It returns typed answers with calibrated probabilities
and cannot generate text — which is why it does matching (pick one of these, or none)
and not extraction (write the strain). It is weak at arithmetic, so sizes stay in
code; it leans toward the first option, so "none" is always offered first.

Measured on Ayrloom (655 listings): **92.1% auto-matched** vs 82.3% for the old
lexical tiers — which also turned out to have matched 7 gummies to a beverage. Run
twice, no listing changed product. With the true product deliberately removed
(the case that produces wrong matches), Jev picked a wrong product 0% of the time at
p ≥ 0.90 and 3.4% at p ≥ 0.85. A full pass over the brand cost $0.013 and took 47s;
answers are cached on the persistent disk keyed by the listing *and its candidates*,
so repeat runs are free and a catalog edit re-asks only the listings it affects.

If OpenRouter is down, five consecutive failures open a circuit breaker for ten
minutes and listings simply go unmatched (the safe outcome) instead of stalling the run.

Thresholds: `CATALOG_MATCH_AUTO`, `CATALOG_MATCH_AUTO_BOOTSTRAP`, `CATALOG_MATCH_REVIEW`.
Re-measure after changing the question or upgrading the model:
`python scripts/catalog_match.py --brand Ayrloom --eval --no-cache`.

## Running it regularly

### One-time setup

1. **Apply the schema migrations** (adds catalog `product_key`/`source`/`support`; the
   first two only codify what production already has):
   ```bash
   python scripts/db_migrate.py           # shows what would run
   python scripts/db_migrate.py --run
   ```
2. **Seed catalogs** for the biggest brands, then review them in the admin page:
   ```bash
   python scripts/catalog_bootstrap.py --top 50              # look first — prints the effect
   python scripts/catalog_bootstrap.py --top 50 --write --push
   python scripts/brand_catalog.py push --brand Ayrloom      # backfills product_key from the
                                                             # existing export; changes nothing else
   ```
3. **Deploy the worker** — Render → New → Background Worker → this repo, Docker, command
   `python scripts/scrape_worker.py`, a 1 GB disk at `/app/data/enrich_cache`, env
   vars from [`scripts/render.yaml`](scripts/render.yaml). Set `ALERT_WEBHOOK_URL` to
   hear about failed mornings. (Or move `scripts/render.yaml` to the repo root and
   create a Blueprint.)
4. **Rehearse once** from a shell with a real `DATABASE_URL`:
   ```bash
   python scripts/scrape.py --slug twisted-vibration-wburg     # smallest store, end to end
   python scripts/scrape.py --all --dry-run
   ```

### Daily (the worker does this)

`scripts/scrape.py --all --parallel --model haiku-or` — scrape, enrich, import and
match every active store. Results land in `data/enrich_cache/_last_run.json` (per
store) and `_cron_status.json` (the run). A store counts as **failed** when its
scraper errors or times out, it returns nothing, its import fails, enrichment
answered fewer than half its rows, or the scrape was partial (fewer products than the
platform reported). A partial scrape is still imported — prices and stock refresh —
but retires nothing.

### Weekly, or after editing catalogs

```bash
python scripts/catalog_match.py --all --jev --write     # re-match every listing to current catalogs
python scripts/catalog_bootstrap.py --top 50 --write --push   # refresh bootstrap catalogs
python evals/enrich/audit.py --db                         # suspects per store
```

### Commands

| task | command |
| --- | --- |
| one store, end to end | `python scripts/scrape.py --slug <slug>` |
| re-import the newest CSVs | `python scripts/scrape.py --all --import-only` |
| scrape without touching the DB | `python scripts/scrape.py --all --scrape-only` |
| include `pending` stores | `python scripts/scrape.py --all --include-pending` |
| catalog coverage for a brand | `python scripts/catalog_match.py --brand X --jev --misses` |
| propose a catalog | `python scripts/catalog_bootstrap.py --brand X --show 20` |
| list catalogs (DB) | `python scripts/catalog_store.py` |
| schema state | `python scripts/db_migrate.py --status` |
| tests | `pytest` (add `TEST_DATABASE_URL=...` for the importer integration tests) |

Knobs: `SCRAPER_TIMEOUT_SEC` (1200), `IMPORT_TIMEOUT_SEC` (900),
`IMPORT_STALE_THRESHOLD` (0.5), `SCRAPE_TIMEOUT_SEC` (5400, whole sweep),
`ENRICH_MAX_WORKERS` (8), `JEV_MODEL`, `JEV_TIMEOUT`.
