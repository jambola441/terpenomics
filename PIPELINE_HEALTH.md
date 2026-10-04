# Pipeline health — 2026-10-04

How the scrape → enrich → import pipeline stood this morning, measured against the
live database, live scraper runs and the code. How to operate it now is in
[PIPELINE.md](PIPELINE.md).

## Verdict

It could not have run on a schedule. No worker was ever deployed, so the data is 36
days old (last scrape 2026-08-29/30). And had one been deployed it would have failed
in ways nobody would have seen: 20 of 25 stores could not start, the run would still
have reported "ok", and the Dutchie stores that did run would have retired 48
listings each. All of that is fixed and tested in this change. Two things are yours
to decide (security, one store) and four are yours to run (below).

## Do these

1. **Security — decide today.** Row-level security is off on all 19 public tables, and
   the anon key ships in the frontend bundle. With nothing but that key, anyone can
   read `customers`, `phone_auth_challenges` and `orders` over the REST API (checked
   with a count-only request: 7, 5 and 0 rows). The frontend uses Supabase only for
   auth, and the API and pipeline connect as the table owner / service role, which
   bypass RLS — so enabling it with no policies closes the hole without breaking
   either. Review, then run:
   ```sql
   DO $$ DECLARE t text; BEGIN
     FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
       EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
     END LOOP;
   END $$;
   ```
   Not applied here: it changes production auth, and that is your call.
2. **Ignyte "Red Hook" is Ignyte Whitestone.** Its `blaze_id` belongs to the Queens
   store — all 653 products scraped today link to `shop.ignyteny.com/whitestone/`, and
   the storefront lists no other location. Its 672 active listings are another store's
   menu at a Brooklyn address. Unless you know where Red Hook's menu really lives, set
   its `status` to `inactive` in `dispensaries.json` (so `--all` stops scraping it) and
   retire what is already there:
   ```sql
   UPDATE listings SET is_active = false, in_stock = false
   WHERE dispensary_id = (SELECT id FROM dispensaries WHERE slug = 'ignyte-red-hook');
   ```
3. `python scripts/db_migrate.py --run` — three idempotent migrations; the first two are
   no-ops on production (they codify drift), the third adds catalog columns.
4. Push catalogs and deploy the worker — [PIPELINE.md → One-time setup](PIPELINE.md#one-time-setup).

## Measured state (live database, read-only)

| | |
| --- | --- |
| active listings | 18,806 across 27 stores (4 more stores have none) |
| last scrape | 2026-08-29 / 08-30 — **36 days stale** |
| brands | 719 (280 listings have no brand) |
| product rows (the `products` view) | 11,425 — 1.65 listings each |
| brands carried by 3+ stores | 266, holding **88%** of listings |
| catalogs | 1 (Ayrloom): 74 active entries in Postgres, 172 in the export file |
| listings matched to a catalog | 646 (3.4%) — none written since 2026-09-07 |
| verified listings | 1 (a test claim) |

## Findings — and what changed

### Would have stopped or silently broken a scheduled run

| finding | evidence | status |
| --- | --- | --- |
| **No schedule at all** | no worker service; `scripts/render.yaml` is reference only; SCRAPERS.md claimed a daily run | worker spec fixed — **deploy it** |
| **`curl_cffi` missing** from requirements.txt | `scrape_graphql.py` exits 1 without it → all 20 Dutchie stores (80% of active) fail in Docker | pinned `curl_cffi==0.16.3`; verified the `safari17_0` profile |
| **Dutchie pages are 0-indexed; the scraper started at 1** | live: 74 of 122 products collected (page 0 never fetched); every store loses its first 48 products and the import retires them | fixed — fetches page 0, and checks what arrived against `totalCount`; live: 122/122 |
| **Failures invisible** | `scrape.py` always exited 0; the worker ignored exit codes; no alerting | non-zero exit on any store failure, per-store `_last_run.json`, `ALERT_WEBHOOK_URL` |
| **A failed enrichment overwrote good data** | unanswered rows carried fallbacks with no marker; with no API key *every* row did, and the upsert wrote "other"/NULL over stored identity | `enrich_failed` CSV column; importer keeps the stored identity of those rows; no-key runs mark every row |
| **Partial scrapes retired real listings** | Flowhub (Grow Together) stalls at 812/861 after 50 passes (109 s, live); only a 50% guard stood between that and deactivation | scrapers record reported vs collected; a partial import refreshes what arrived and retires nothing, and the store is reported failed |
| No per-scraper timeout; the 90-min kill orphaned children | `subprocess.run(timeout=)` kills only the direct child | process-group kill, per scraper (20 min) and per import (15 min) |
| `--all` ran inactive and pending stores | registry `status` ignored | active only by default; `--include-pending` |
| Enrich cache: non-atomic writes, no corrupt-file handling | a deploy mid-write broke that store every day until hand-cleaned | atomic replace; an unreadable cache is set aside and the store re-enriches once |

### Data quality and identity

| finding | evidence | status |
| --- | --- | --- |
| **Matching read a stale file, not the catalog** | export file: 172 Ayrloom entries; Postgres: 74 active — the 98 online-only hemp D9 entries removed on 2026-09-06 were still match targets. The admin "export" writes to the web service's disk, which nothing else reads | matching reads Postgres (`catalog_store.py`); the file is an offline snapshot |
| **A catalog refresh would have undone curation** | `push` set `is_active = TRUE` on everything re-listed and overwrote edited fields | push is additive: new entries in, curated fields and deactivations kept, re-listed-but-removed entries reported |
| **Lexical catalog matching made confident wrong matches** | 7 "Island Time Pineapple Mango" *gummies* matched to the "Pineapple Mango" *beverage* | lexical tiers now only nominate; Jev decides (below); subtype/size veto |
| Catalog matches were never written at import | a manual per-brand `--write`; new listings stayed unmatched, renamed ones kept stale matches | every import resolves every row and writes the match columns; manual matches preserved |
| Product identity is model strings | Jetpacks FJ-Mini Afghani 0.6g at 7 stores: line "FJ-Mini" / "FJ Mini" / blank → 3+ product rows; 1,374 spurious rows from product_line alone (CATALOG.md) | catalog identity overlays trusted matches at import; bootstrap catalogs for every multi-store brand |
| Attribute meaning defined in 7 places, already disagreeing | topical was "dose" to one module, neither to another, so a 1000mg balm became "1g" | `taxonomy.py` is the single definition; prompts pinned byte-identical; topical is a dose |
| Stale-marking guard counted after the upsert | dry run ≠ real run; a full SKU change (platform migration) never retired the old menu; the stale UPDATE re-touched every inactive row daily | counted before writing; `AND is_active`; integration-tested |
| Rows without a SKU duplicated every run | plain INSERT, never marked stale | stable synthetic SKU from the name; upserted |
| Brand aliases skipped by 2 scrapers and the importer | Alleaves, Travel Agency | applied once, at import |
| Verified `variant` re-keyed the listing; verified `category` never protected | overlay rewrote the upsert key; `category` missing from the overlay map | variant no longer overlaid (it is the key); category protected |
| Travel Agency truncated prices | `int(19.99 * 100)` = 1998 | `round()` |

### Maintainability

| finding | evidence | status |
| --- | --- | --- |
| **Test suite red for four weeks** | 120 errors since 2026-09-06 (SQLite cannot compile JSONB/ARRAY); no CI; pytest not a dependency; bare `pytest` hit live APIs | type variants; `pytest.ini` (live tests opt-in); GitHub Actions with Postgres; **322 passing** |
| Schema defined nowhere | `products` view only in a destructive reset script, and drifted; `listings.attributes` had no DDL; models.py lacked 3 live columns; no record of what ran | `db/migrations` + `scripts/db_migrate.py` (recorded, checksummed); `db/schema/pipeline.sql` snapshot; models updated |
| Importer untestable | one 300-line `main()` over positional tuples | named records, overlays as functions; 19 integration tests against real Postgres 16 with the production schema |
| Two scripts that damage production if run | `scripts/migrate.py` dropped every table (orders included) and rebuilt from models.py; `scripts/import_listings_rest.py` was a drifted importer with no verification, attributes or failure protection | deleted |

## Not changed — worth doing next

- **Potency is thrown away.** Every scraper computes THC/CBD %, and the CSV schema drops
  it (85–95% populated before it was removed in May). No column holds it.
- **Dutchie's cross-store ids are never requested** (`brand.id`, enterprise product ids).
  For the three chains in the registry they would make matching exact. Needs a GraphQL
  introspection to confirm the field names.
- **Enrichment still runs inside each scraper process**, so a crash after scraping loses
  that store's day. It is now visible and retried tomorrow; decoupling (scrape → CSV,
  then enrich the CSV) is the cleaner end state.
- **The enriched variant is part of the listing key**, so a model changing a size
  re-keys a listing. Mitigated for failed rows only.
- **Flowhub never reaches its reported total** (94% after 50 passes). Imported safely
  now, but the scraper needs a better pagination strategy.
- **The portal re-implements product identity in five places** with different NULL
  handling, and none includes `attributes`, so merch colour variants merge there.
- **Dead code:** `services/matching.py` (no callers), `ui/my-app/src/ListingMatch.tsx`
  (calls endpoints that no longer exist) and the root `generate_*.py` scripts.
  Recommend deleting.
- Alleaves is wired to one store and its prices include tax, unlike every other scraper.
- Haiku's batch endpoint is half price and latency is free for a nightly run.

## Jev, measured

TypeSafe's decision model (`typesafe/jev-1.13`, OpenRouter) returns a choice with a
calibrated probability per option and cannot generate text — so it does catalog
matching, not extraction. Three identical calls: same answer, probabilities ±0.02,
350–720 ms, $0.00002 each.

Ayrloom, 655 active listings, against the curated catalog (47 products):

| | auto-matched | review | no match | known wrong |
| --- | ---: | ---: | ---: | ---: |
| lexical tiers (before) | 82.3% | — | 17.7% | 7 |
| Jev tier (p ≥ 0.85) | **92.1%** | 4.1% | 3.8% | 0 found |

- The 93 listings Jev matched that the lexical tiers could not were checked by hand:
  masked titles ("Alaskan Thunder Fuck" → `alaskan thunder fu*k`), the Mood line, the
  topical balms CATALOG.md had marked as needing a model tier.
- The "no match" answers are products missing from the curated catalog (Rose cider,
  Mood Rest/Focus) or genuinely different flavours — the right answer.
- **Holdout** (true product removed from the shortlist, so the right answer is "none"):
  wrong product picked at p ≥ 0.90: **0%**; p ≥ 0.85: 3.4%; p ≥ 0.80: 4.6% — all one
  near-miss, "Half & Half lemonade-and-tea" read as "Lemonade". Bootstrap catalogs, which
  can be missing products, use 0.90.
- Tried and rejected: a second yes/no "is this exactly that product" check. True and
  false pairs overlapped (0.10–0.88 vs 0.30–0.75); the competitive Choice is the better
  signal.
- Cost: $0.013 and 47 s for the whole brand (636 calls, 8 workers); cached afterwards.

## Catalogs for every brand, measured

`catalog_bootstrap.py` builds a catalog from the consensus of stores that carry a brand
(products at ≥ 2 stores):

| scope | proposed products | listings covered | product rows |
| --- | ---: | ---: | --- |
| Jetpacks | 71 | 232 / 304 | 210 → 141 |
| top 50 brands without a catalog | 1,922 | 7,294 / 9,692 (75%) | 4,796 → 3,916 |
| top 300 | 3,135 | 10,561 / 16,546 (64%) | 9,014 → 7,827 |

Before Jev absorbs the single-store variants and before any human review. Not pushed —
see [PIPELINE.md](PIPELINE.md#one-time-setup).
