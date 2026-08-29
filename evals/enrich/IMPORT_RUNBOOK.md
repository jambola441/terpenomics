# Importing the 2026-08-25 fleet scrape

**Nothing from this session is in the database.** The sandbox this ran in cannot
reach Postgres — outbound 5432 times out (443 works, so it is the egress proxy, not
credentials). Every enriched listing exists only as a CSV in `data/scrapes/`, which
is gitignored and dies with the container.

**Nothing else is updating it either.** `scripts/render.yaml` defines a
`terpenomics-scraper` background worker to run the pipeline daily at 09:00 ET, but
that blueprint lives in `scripts/` rather than the repo root, so Render never
auto-synced it and it says as much in its own header. The workspace currently runs
`terpenomics`, `terpenomics-ui` and unrelated projects — **there is no scraper
worker**. So listings are only as fresh as the last manual run.

## Use `scripts/scrape.py` — it already does all of this

It reads `dispensaries.json`, picks the right scraper per platform, enriches, and
imports:

```bash
python scripts/scrape.py --all                  # scrape + enrich + import, every store
python scripts/scrape.py --slug the-spot-bk     # one store
python scripts/scrape.py --all --dry-run        # print commands, run nothing
python scripts/scrape.py --all --import-only    # skip scraping, import CSVs already on disk
python scripts/scrape.py --all --scrape-only    # scrape to CSV, skip the DB
```

`scripts/run_scrape_cron.py` wraps `--all` with an overlap lock, a 90-minute
wall-clock ceiling, a heartbeat file and a non-zero exit on failure.
`scripts/scrape_worker.py` runs that on a daily schedule and is what the Render
worker is meant to execute.

## The sequence, as of _ENRICH_VERSION 6

The database was reset on 2026-08-26 (listings 0) and the variant-aware index is
in place, so this is a clean load with nothing to reconcile against.

```bash
git pull                                          # need >= f06e52c

# optional: keep 18,134 of 19,432 cached answers instead of re-enriching all
tar xzf enrich_cache_v5.tar.gz                    # if restoring from a handoff
cd data/enrich_cache && for f in *.haiku-or.json; do mv "$f" "${f%.haiku-or.json}.json"; done
cd ../.. && python scripts/migrate_enrich_cache_v6.py --run

python scripts/scrape.py --all --parallel         # scrape + enrich + import
```

`migrate_enrich_cache_v6.py` exists because the version stamp is per-entry but not
per-category, so bumping 5 -> 6 for a merch-only change invalidates everything.
The v5 -> v6 diff touches merch alone, so a non-merch v5 answer is still what v6
would produce: it restamps those and drops the 1,298 merch entries, which
re-enrich for about $0.40 instead of $5-6 for the whole fleet. That reasoning is
specific to this bump — a later one needs its own.

Skip the migration and `scrape.py` just re-enriches everything, which is equally
correct, only slower and dearer.

## Landing this session's data

The CSVs are already enriched, so importing them costs nothing and skips ~11 minutes
of scraping:

```bash
python scripts/scrape.py --all --import-only --dry-run   # look first
python scripts/scrape.py --all --import-only
```

`find_latest_csv()` discovers files matching `^{slug}_\d{8}T\d{6}Z\.csv$`. The
prototype scrapers write `{slug}_listings_{stamp}.csv`, which does **not** match —
these files have been renamed to the expected form, and all 25 resolve.

### What exists

| | |
| --- | --- |
| stores | 25 (24 scraped + The Plug after its Dutchie migration) |
| listings | 19,106, all enriched |
| enrich cache | 20,676 entries, every one stamped `"v": 5` |
| cost to produce | ~$11 of model calls |

Pre-flight over all 25 CSVs: every column `import_listings.py` reads is present,
every `dispensary_slug` resolves, and **0 rows would be skipped** for a missing name.

### Re-scraping instead

Scraping is free and takes ~11 minutes, so if the menus have moved on:

```bash
python scripts/scrape.py --all --parallel
```

## The cache namespace will cost you $5.30 if ignored

`enrich.py` keys cache files per model — `<slug>.json` for the default `haiku`,
`<slug>.<model>.json` for anything else:

```python
slug = base_slug if model == DEFAULT_MODEL else f"{base_slug}.{model}"
```

This session ran `haiku-or` (no `ANTHROPIC_API_KEY` was available), so the files are
`<slug>.haiku-or.json`. `scripts/scrape.py` defaults to `--model haiku`, which
**will not see them** and will re-enrich all 19,106 listings from scratch.

Either pass `--model haiku-or` (needs `OPENROUTER_API_KEY`), or, since `haiku` and
`haiku-or` are the same weights (`claude-haiku-4.5`) differing only in transport,
move them onto the default namespace:

```bash
cd data/enrich_cache && for f in *.haiku-or.json; do mv "$f" "${f%.haiku-or.json}.json"; done
```

Only do that if you accept OpenRouter-served answers as equivalent to native ones.
Same model, but this session never verified the two transports agree row-for-row.

## Before you run it

**Check `--stale-threshold`.** `import_listings.py` marks absent listings inactive,
guarded by a default `0.5` — a scrape carrying under half a dispensary's active
listings will not deactivate the rest. The DB has not been refreshed in a while, so
expect large deltas; run one store first and read the counts before the full sweep.

**Two stores changed state.** Coney Island is marked `inactive`
(`shop.coneyislandcannabis.nyc` 404s at the domain root). The Plug moved to Dutchie
and its `dispensaries.json` entry is updated — importing its 842 rows under the same
slug reconciles against the old Flowhub listings.

**10 rows collide on the listing key** — `(dispensary_id, sku, COALESCE(variant,''))`
— out of 19,106 (0.05%). Six are exact duplicates and collapse harmlessly. Four are
real:

```
hold-up-roll-up    HURU Gift Card    sku=HC00PRO1  variant=''   $10 / $25 / $50 / $100
hii-nyc-bay-ridge  Fernway Traveler Vape 1g                     $25.00 / $50.00
hii-nyc-wburg      Hash Burger Live Resin 510 Cart 0.5g         $38.00 / $58.00
```

The gift card is one SKU across four denominations with no variant to separate them,
so three of the four are dropped and which survives depends on row order. Same class
as the bug the variant-key migration fixed, but the variant column cannot reach it
because the platform leaves variant empty. Whether price belongs in the listing key
is a migration-level call, so it is flagged rather than changed.

## Afterwards

```bash
python evals/enrich/audit.py --db
```

Expect roughly what the CSV-side report found: ~3 suspects per 100 listings, and
about 8 rows total in `other`.

## Worth doing: deploy the worker

Nothing keeps the DB fresh right now. Either move `scripts/render.yaml` to the repo
root so Render auto-syncs the blueprint, or create the worker by hand from the
dashboard as its header describes. Note it declares `ANTHROPIC_API_KEY`, so the
worker would run native `haiku` and its persistent disk at
`/app/data/enrich_cache` would start cold unless the cache is seeded onto the
default namespace first.
