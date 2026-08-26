# Importing the 2026-08-25 fleet scrape

**Nothing from this session is in the database.** The sandbox this ran in cannot
reach Postgres — outbound 5432 times out (443 works, so it is the egress proxy, not
credentials). Every enriched listing exists only as a CSV in `data/scrapes/`, which
is gitignored and dies with the container.

So the import has to run from a machine that can reach the DB.

## What exists

| | |
| --- | --- |
| stores | 25 (24 scraped + The Plug after its Dutchie migration) |
| listings | 19,106, all enriched |
| enrich cache | 20,676 entries, every one stamped `"v": 5` |
| cost to produce | ~$11 of model calls |

Pre-flight over all 25 CSVs passed: every column `import_listings.py` reads is
present, every `dispensary_slug` resolves against `dispensaries.json`, and **0 rows
would be skipped** for a missing name.

## Re-scrape, then import

Scraping is free and takes ~2 minutes, so the simplest path is to redo it locally:

```bash
python prototypes/dutchie-scraper/scrape_graphql.py --all --no-enrich --parallel
python prototypes/tymber-scraper/scrape_blaze.py     --all --no-enrich --parallel
python prototypes/dutchie-scraper/scrape.py          --all --no-enrich --parallel

python evals/enrich/enrich_csvs.py --csv 'data/scrapes/*.csv' --model haiku-or

for f in data/scrapes/*.csv; do python scripts/import_listings.py --csv "$f"; done
```

### Reuse the cache or pay twice

`enrich.py` namespaces cache files per model — `<slug>.json` for the default
`haiku`, `<slug>.<model>.json` for anything else:

```python
slug = base_slug if model == DEFAULT_MODEL else f"{base_slug}.{model}"
```

This session ran `haiku-or`, so the files are `<slug>.haiku-or.json`. **Running
enrichment as plain `--model haiku` will not see them and will re-enrich all 19,106
listings from scratch (~$5.30).**

Either keep passing `--model haiku-or` (needs `OPENROUTER_API_KEY`), or, since
`haiku` and `haiku-or` are the same weights (`claude-haiku-4.5`) differing only in
transport, rename them onto the default namespace:

```bash
cd data/enrich_cache && for f in *.haiku-or.json; do mv "$f" "${f%.haiku-or.json}.json"; done
```

Only do that if you accept OpenRouter-served answers as equivalent to native ones.
They are the same model, but this session never verified the two transports agree
row-for-row.

## Before you run it

**Check `--stale-threshold`.** `import_listings.py` marks absent listings inactive,
guarded by a default `0.5` — a scrape carrying under half a dispensary's active
listings will not deactivate the rest. The DB has not been refreshed in a while, so
expect large deltas; run one store first and read the counts before looping.

**Two stores are no longer active.** Coney Island is marked `inactive`
(`shop.coneyislandcannabis.nyc` 404s at the domain root). The Plug moved to Dutchie
and its `dispensaries.json` entry is updated — importing its 842 rows under the same
slug will reconcile against the old Flowhub listings.

**10 rows collide on the listing key** — `(dispensary_id, sku, COALESCE(variant,''))`
— out of 19,106 (0.05%). Six are exact duplicates and collapse harmlessly. Four are
real:

```
hold-up-roll-up    HURU Gift Card    sku=HC00PRO1  variant=''   $10 / $25 / $50 / $100
hii-nyc-bay-ridge  Fernway Traveler Vape 1g                     $25.00 / $50.00
hii-nyc-wburg      Hash Burger Live Resin 510 Cart 0.5g         $38.00 / $58.00
```

The gift card is one SKU across four denominations with no variant to separate them,
so three of the four are dropped and which survives depends on row order. This is
the same class the variant-key migration fixed, but the variant column cannot reach
it because the platform leaves variant empty. Deciding whether price belongs in the
listing key is a migration-level call, so it is flagged rather than changed.

## Afterwards

`audit.py` works against the live table once the data is in, and is the cheapest way
to confirm the import landed:

```bash
python evals/enrich/audit.py --db
```

Expect roughly what the CSV-side report found: ~3 suspects per 100 listings, and
about 8 rows total in `other`.
