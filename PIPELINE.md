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
A Render cron job runs that daily. The enrich cache lives in Postgres
(`ENRICH_CACHE=db`), so the job needs no disk.

## Where a listing's attributes come from

**Defined** in one place: [`scripts/taxonomy.py`](scripts/taxonomy.py). For each
category it declares the subtype rail, what `variant` measures, what `strain` means,
the rules the model is told, and which fields identify a product:

| category | variant measures | strain means | identity |
| --- | --- | --- | --- |
| flower, vaporizers, concentrate | weight (g, package total) | cultivar (vapes: or flavour) | subtype, line, strain, size |
| preroll | weight (g, package total) | cultivar | line, strain, size — no subtype |
| edible | dose (total mg; NY caps a package at 100mg) | flavour | subtype, line, strain, size |
| tinctures, topical | dose (total mg) | flavour / scent or blend | subtype, line, strain, size |
| merch | size + pack | — | subtype, attributes (colour/flavour), size |

A pre-roll keeps no subtype. Single or pack is the size's pack count, and infused is
the product line where the brand names one ("Live Resin Infused"). As a subtype,
infused took the slot from pack on 834 listings, and 87 products sat under two
subtypes, splitting them in catalogs and price comparisons. The classify prompt still
asks for one (a rail edit is a prompt edit); the importer drops the answer.

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
it. Catalog matching and the bootstrap compare sizes as numbers parsed by
[`scripts/sizes.py`](scripts/sizes.py) (`5pk x 0.6g` = `3g`, `1/8 oz` = `3.5g`), so
two spellings of one size never split a product.

**A listing's size** has two columns. `variant` is the store's own size field, kept as
typed: it is part of the row's key, and orders, purchases and lab reports hang off the
row. `size` is what product pages and price comparisons group on
(`Listing.product_size`; NULL reads as `variant`). The importer sets it to the store's
size, or to the catalog's when a dose product (edible, tincture, topical) matched by
`exact`, `jev` or `manual` states a size it does not come in, and the listing backs the
catalog: its name or description states the catalog's total, or its figure is that
size's per-piece dose (`catalog_match.catalog_size`). Camino's 100mg 20-pack listed as
50mg ("100mg THC : 100mg CBD per package" in its description) and Ayrloom's 150mg drops
listed as 600mg ("150mg THC : 450mg CBD" in the name) go back on their products' pages:
68 listings on 2026-10-05, 31 of them a per-piece dose typed as the size. A weight that
disagrees stays on its own page, because a 14g bag matched to its strain's 3.5g is more
often a real size the catalog lacks. So does a listing that names another pack count (a
2-pack beside the catalog's 5-pack).

**Within enrichment**, each row is answered by the cheapest thing that can answer it
([`scripts/enrich.py`](scripts/enrich.py)):

| order | answered by | fields |
| --- | --- | --- |
| 1 | a human's verified claim | all |
| 2 | merch rules — the name's tokens | all |
| 3 | this store's cache of earlier answers | all |
| 4 | the brand catalog, when the listing's name *is* a recorded catalog product | all |
| 5 | **Jev** | category, subtype |
| 5 | code, when the store's figure is unambiguous (`stated_size`) | size |
| 5 | **Jev**, picking from the name's phrases (`jev_extract.py`) | strain, product line |
| 5 | Haiku, one call, for whatever is still open — with Jev's settled rows as context | strain, product line — and size where code refused |
| 6 | Haiku, two calls, for rows Jev is unsure of (p < 0.80) | all |

Steps 1–4 make no model call, and step 5 settles about half of what is left without
one. On the gold suites, steps 5–6 are more accurate than Haiku alone, change fewer
answers between runs, and cost 48% less (287.7 vs 278.7 of 302 cases; $0.086 vs $0.164
a run; [evals/enrich/README.md](evals/enrich/README.md#jev-picks-strain-and-line-too--and-haiku-needs-the-easy-rows-2026-10-04)).
Step 4 would have answered 21% of today's model-bound rows once the top-50 bootstrap
catalogs are pushed, more as catalogs grow. A listing qualifies when its name, with
or without the brand, is one a store has already used for that product — recorded in
the catalog when it was built. Its answers agreed with the stored category, subtype
and size on 99–100% of rows and strain on 98%. Strain differences are spellings
("Grand Daddy Purple" vs "Granddaddy Purple"); product line differences are line
splits. In both cases the catalog's consensus is the point. `ENRICH_CLASSIFIER=llm`
puts every model-bound row through step 6, as before; `ENRICH_CATALOG_FIRST=0`
skips step 4.

## Brand catalogs

A catalog is a brand's product list. A listing that resolves to an entry takes the
entry's identity, so every store carrying the product lands on one row of the
products view instead of three spellings of it.

**Where catalogs come from** — `brand_catalogs.source_method`:

| source | how | when to use |
| --- | --- | --- |
| `shopify_products_json`, `wc_store_api` | `python scripts/storefront.py push --brand X` with a recipe in `data/storefronts/` | the brand's site lists its products (Florist Farms) |
| `shopify_products_json` (legacy) | `python scripts/brand_catalog.py fetch --brand X --domain x.com` then `push` | Ayrloom, until it has a recipe |
| `listings_bootstrap` | `python scripts/catalog_bootstrap.py --brand X --write --push` | everyone else — built from the consensus of stores that carry the brand |
| `manual` | admin → Brand catalogs | fixes, additions |

**Storefront catalogs** take the brand's own word for what it sells. Each brand has a
recipe, `data/storefronts/<brand-slug>.json`: where the products are (a Shopify
store's `/products.json`, a WooCommerce Store API), what to skip (apparel), how the
site's fields map to our categories, and regexes that split the site's titles into
line, strain and size. A recipe is written once — by an agent pass that studies the
site, or by hand — and runs with no model from then on. Size and subtype come from
the shared readers (`sizes.py`, `taxonomy.py`), so storefront and bootstrap entries
are written the same way.

`storefront.py check --brand X` is the recipe's test: it lists every site item no
rule handled, and the products stores sell that the site does not. A push is the
site's entries plus the stores' consensus for those products only (Florist Farms'
site does not list the Gorilla Glue vapes four stores carry), with spelling allowed
for ("Mandarin Dog" at the stores is the site's "Mandarine Dog"). Store names that
resolve to a site product travel with it, so those listings stay `exact`. The push
retires everything else, the brand's old bootstrap entries included, and records the
site as the source, so `catalog_bootstrap.py --rebuild` leaves the brand alone. A
recipe that leaves more than 10% of the site unhandled is not pushed: the site has
changed shape, and the recipe needs another pass.

The bootstrap groups a brand's listings across stores by (category, subtype, strain,
line, size) — a strain's cart, pod and all-in-one are three products, and a format
word in the name ("Cart", "AIO") beats the model's subtype. It folds the product_line
split (a line-less group joins the one lined group that matches it on everything
else) and keeps products at least two stores carry. On the top 300 brands it proposes
3,122 products covering 61% of their listings. Each entry records its `support` (how
many stores) and the store names it was built from, so those listings resolve
exactly — no model call — on every later run, at enrichment and at import.

**Pushing is additive.** `brand_catalog.py push` and `catalog_bootstrap.py --push`
insert new products and refresh metadata (store names, support, last seen), but never
overwrite a field you curated and never reactivate an entry you took out — a Shopify
re-fetch used to do both. Storefront products that vanish are deactivated; bootstrap
entries are not, since one quiet week at the stores is not a discontinuation.

**Auditing a catalog's structure.** A catalog built right looks like a brand's range:
named lines, each in several strains or flavours. `python scripts/catalog_shape.py show
"<Brand>"` lays a catalog out that way and lists the places it does not (a line with one
strain, a big line-less group beside named lines, a strain or effect filed as a line, two
entries for one product); `triage` ranks every catalog by them. Which of those are real
takes evidence from store names and the brand's site, so the judgment is an agent skill,
`.claude/skills/catalog-audit/SKILL.md`: ask Claude Code to "spot check the X catalog".

**Postgres is the system of record.** Matching reads catalogs from the database
(`scripts/catalog_store.py`); the `data/catalogs/*.json` files are an offline
snapshot (`python scripts/catalog_store.py --snapshot`), not the read path. Edits in
the admin page apply on the next import — there is no export step to remember.

## Matching listings to catalogs — and where Jev fits

Jev does two jobs, both of them picks from a list: at enrichment it chooses a
listing's category and subtype (above), and at import it chooses which catalog
product a listing is.

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
answers are cached on local disk keyed by the listing *and its candidates*, so repeat
runs on one machine are free and a catalog edit re-asks only the listings it affects.
The cron job has no disk, so it re-asks each run; that costs cents.

**What Jev sees** is the listing's name, category, subtype and size, plus one thing
from its description: a curated product line it names when the name names none
(`catalog_match.described_line`, the rule enrichment uses — `data/product_lines.json`
lines that declare a category). Wider hints were measured on 2026-10-05 and did worse.
With the description's first 300 characters, across 21 brands, 74 matches became
trusted and 50 stopped being; with the true product held out, wrong picks rose from
75 to 92, because store copy is often pasted from another product (an MFNY "Turbo
Blueberry" pre-roll described as Honey Banana). Any line of the brand's catalog named
in the description did as badly: generic line names like "Infused" turn up in copy
about other products. Repeat runs with nothing changed moved 5 of 441 decisions, so
those differences are real.

A matched listing takes the entry's strain and product line; it takes the entry's
subtype unless a format word in its own name says otherwise ("Cart", "AIO", "Starter
Kit") — the name is a fact about the listing, the entry's subtype a claim about the
product (`catalog_match.matched_subtype`, shared with enrichment's step 4).

If OpenRouter is down, five consecutive failures open a circuit breaker for ten
minutes and listings simply go unmatched (the safe outcome) instead of stalling the run.
At enrichment the same breaker sends rows to Haiku's two calls instead.

Thresholds: `CATALOG_MATCH_AUTO`, `CATALOG_MATCH_AUTO_BOOTSTRAP`, `CATALOG_MATCH_REVIEW`.
Re-measure after changing the question or upgrading the model:
`python scripts/catalog_match.py --brand Ayrloom --eval --no-cache`.

## Running it regularly

### One-time setup

1. **Apply the schema migrations.** Done on production on 2026-10-04: all four are
   recorded in `schema_migrations`, so this now reports nothing pending. On a new
   database:
   ```bash
   python scripts/db_migrate.py           # shows what would run
   python scripts/db_migrate.py --run
   ```
2. **Seed catalogs** for the biggest brands, then review them in the admin page. Done
   for the top 50 on 2026-10-05 (48 catalogs; RAW and Blazy Susan propose nothing):
   ```bash
   python scripts/catalog_bootstrap.py --top 50              # look first — prints the effect
   python scripts/catalog_bootstrap.py --top 50 --write --push
   python scripts/brand_catalog.py push --brand Ayrloom      # backfills product_key from the
                                                             # existing export; changes nothing else
   ```
   Pushes write over `DATABASE_URL`. From a sandbox that cannot open a Postgres
   connection, add `--via-http` to either command: the same rules, over Supabase's REST
   API ([DB_ACCESS.md](DB_ACCESS.md)).
3. **Create the daily cron job.** Render → New → Cron Job → this repo, Docker runtime:
   - name `terpenomics-scraper`, region Oregon, plan Starter;
   - command `python scripts/run_scrape_cron.py`, schedule `0 13 * * *` (13:00 UTC:
     9am in New York in summer, 8am in winter);
   - secrets: `DATABASE_URL`, `OPENROUTER_API_KEY`, `ALLEAVES_USER`, `ALLEAVES_PASS`
     (the `terpenomics` service has the first; this repo's Claude Code cloud
     environment has all four);
   - settings: `SCRAPE_ARGS=--all --parallel --model haiku-or`, `ENRICH_CACHE=db`,
     `SCRAPE_TIMEOUT_SEC=9000`, `PYTHONUNBUFFERED=1`;
   - optional: `ALERT_WEBHOOK_URL`, to hear about failed mornings. Render also emails
     on a failed run.

   The same settings are in [`scripts/render.yaml`](scripts/render.yaml). There's no
   disk to attach. The first run enriches every listing (about an hour and a few
   dollars); after that, only new or changed listings go to a model.
4. **Rehearse once** from a shell with a real `DATABASE_URL`:
   ```bash
   python scripts/scrape.py --slug twisted-vibration-wburg     # smallest store, end to end
   python scripts/scrape.py --all --dry-run
   ```
   Or from a sandbox, over HTTPS (done for this store on 2026-10-05):
   ```bash
   ENRICH_CACHE=db python scripts/scrape.py --slug twisted-vibration-wburg --model haiku-or --via-http
   ```

### Daily (the cron job does this)

`scripts/scrape.py --all --parallel --model haiku-or` — scrape, enrich, import and
match every active store. Results land in `data/enrich_cache/_last_run.json` (per
store) and `_cron_status.json` (the run). On the cron job those files go with the
container, so read the run's log in Render instead. A store counts as **failed** when its
scraper errors or times out, it returns nothing, its import fails, or enrichment
answered fewer than half its rows; any failure makes the run exit non-zero. A
**partial** scrape (fewer products than the platform reported) is a warning: it is
still imported — prices and stock refresh — but retires nothing, and it does not fail
the run, so a chronic one (Grow Together's Flowhub menu stalls near 810 of 861) cannot
bury real failures.

**Pausing.** Set `PIPELINE_PAUSED=1` on the cron job (Render → Environment) and each
run logs, alerts and exits without scraping; set it to `0` to resume. Render's Suspend
button works too, but the switch alerts on every skipped run, so a pause that outlives
its reason gets noticed.

### Weekly, or after editing catalogs

```bash
python scripts/catalog_match.py --all --jev --write     # re-match every listing to current catalogs
python scripts/storefront.py push --all                   # refresh storefront catalogs
python scripts/catalog_bootstrap.py --rebuild --push       # refresh bootstrap catalogs (additive)
python scripts/catalog_bootstrap.py --top 50 --push        # propose catalogs for the next brands
python scripts/catalog_shape.py triage                     # which catalogs to spot check
python evals/enrich/audit.py --db                         # suspects per store
```

### Commands

| task | command |
| --- | --- |
| one store, end to end | `python scripts/scrape.py --slug <slug>` |
| re-import the newest CSVs | `python scripts/scrape.py --all --import-only` |
| scrape without touching the DB | `python scripts/scrape.py --all --scrape-only` |
| the whole pipeline from a sandbox | `ENRICH_CACHE=db python scripts/scrape.py --all --model haiku-or --via-http` |
| include `pending` stores | `python scripts/scrape.py --all --include-pending` |
| catalog coverage for a brand | `python scripts/catalog_match.py --brand X --jev --misses` |
| propose a catalog | `python scripts/catalog_bootstrap.py --brand X --show 20` |
| test a storefront recipe | `python scripts/storefront.py check --brand X` |
| a catalog's structure and leads | `python scripts/catalog_shape.py show "X"` (`triage` for all) |
| list catalogs (DB) | `python scripts/catalog_store.py` |
| schema state | `python scripts/db_migrate.py --status` |
| tests | `pytest` (add `TEST_DATABASE_URL=...` for the importer integration tests) |

Knobs: `SCRAPER_TIMEOUT_SEC` (1200), `IMPORT_TIMEOUT_SEC` (900),
`IMPORT_STALE_THRESHOLD` (0.5), `SCRAPE_TIMEOUT_SEC` (5400, whole sweep),
`ENRICH_MAX_WORKERS` (8), `ENRICH_CLASSIFIER` (`jev`; `llm` is the rollback),
`ENRICH_JEV_MIN_CONFIDENCE` (0.80), `ENRICH_JEV_TEXT` (1), `ENRICH_JEV_TEXT_MIN` (0.90),
`ENRICH_JEV_LINE_MIN` (0.80), `ENRICH_JEV_NO_LINE_MIN` (0.50), `ENRICH_CATALOG_FIRST` (1),
`JEV_MODEL`, `JEV_TIMEOUT`, `DB_VIA_HTTP` (off; `1` reaches the database over
Supabase's REST API instead of `DATABASE_URL`), `ENRICH_CACHE` (files; `db` keeps the
enrich cache in Postgres).
