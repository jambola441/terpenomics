# Enrichment model evals

A suite for comparing how different models perform the post-scrape enrichment in
[`scripts/enrich.py`](../../scripts/enrich.py) — so we can pick the best model and catch
regressions when prompts change.

## Eval types (one file per type in `cases/`)

| File | Type | What it checks |
| --- | --- | --- |
| `categorization.json` | `categorization` | Correct `category` + `subtype`, including overriding a wrong scraper `hint_category`. |
| `variant_fixes.json` | `variant_fix` | Fix variant-label errors: edible → total mg (pack math), flower fractions → grams, don't convert a drink's fl-oz to grams. |
| `common_errors.json` | `common_error` | Messy real listings with several mistakes at once (wrong category + ALLCAPS + flavor-as-strain + bad variant). |
| `identity_clusters.json` | `identity_cluster` | Groups of differently-worded listings of the **same product** must converge to one identity tuple — the cross-dispensary "same product → same key" test. |

Per-item cases have an `expect` dict (a case passes when every expected field matches).
Cluster cases have `members` + `expect_same` (passes when all members agree on those fields)
and an optional `canonical` tuple to also check the agreed value is *correct*.

## Run

```bash
# fast models
python evals/enrich/run_eval.py --models haiku,deepseek,gemini-flash,gpt-mini

# include MiMo (slow — ~110s/batch)
python evals/enrich/run_eval.py --models haiku,mimo

# one eval type only
python evals/enrich/run_eval.py --models haiku --cases cases/categorization.json
```

Models are the ids in `MODELS` in `scripts/enrich.py`. Needs `OPENROUTER_API_KEY` (OpenRouter
models) / `ANTHROPIC_API_KEY` (haiku) in `.env`.

## Outputs (`results/`)

- `comparison.md` — per case, every model's answer side by side (✓/✗ vs expected, or split-detail for clusters).
- `summary.md` — per model: time, tokens, cost, and pass rate per eval type.
- `<model>.json` — full scored detail for debugging.

Enrichment runs with `brand_examples={}` (model only, no DB nudge) and clears the eval cache
each run, so the **current** prompts are always exercised.

## Gold dispensary set

`cases/gold_the_plug.json` — 108 hand-labeled real listings from The Plug (Crown
Heights), stratified across categories. Includes the failure modes that matter in
production: a whole raw category the scraper's CATEGORY_MAP missed (vapes landing in
`other` — tests hint override at scale), edible pack math, typo strains that must be
kept verbatim ("Red Zprite", "Marakesh"), product lines (UP, Flyers, Noir, Quicks,
Releaf), flavor-as-strain beverages, and null-strain merch/topicals. Ambiguous fields
(infused-vs-pack prerolls, unknown pack counts) are omitted from `expect` so the pass
rate reflects real errors, not taxonomy judgment calls.

```bash
python evals/enrich/run_eval.py --models haiku --cases cases/gold_the_plug.json
```

## Results (haiku, gold_the_plug)

| run | cases | fields | cost |
| --- | --- | --- | --- |
| baseline | 90/108 (83.3%) | 382/400 (95.5%) | $0.0454 |
| v3 (deterministic layer) | 105/108 (97.2%) | 397/400 (99.2%) | $0.0461 |

category and product_line both reach 100%. The v3 run fixed 18 fields and broke 3;
all three regressions came from prompt edits, not from the deterministic layer, and
are addressed in v4 (beverage variant rule scoped so it stops pulling subtype toward
'beverage'; pack multiply-out scoped to mg doses so it stops overriding a correct
weight hint). Cost is flat — the accuracy came from curated data, not more tokens.

**A model that scores ~10% is almost always a broken config, not a bad model.** The
first deepseek run reported 11/108 having burned 0 tokens: the api_model slug was
never verified and no call was made, so the rule-based hints scored on their own.
run_eval now fails loudly on a zero-token run.

## Baseline detail (haiku, gold_the_plug)

| field | n | accuracy |
| --- | --- | --- |
| category | 108 | 99.1% |
| subtype | 94 | 97.9% |
| variant | 88 | 95.5% |
| strain | 99 | 92.9% |
| product_line | 11 | 63.6% |

83.3% of cases fully clean; 95.5% of individual fields. ~$0.00042/listing
(≈$0.46 for a 1,087-listing dispensary), so **cost is not the binding constraint —
accuracy is.** Note `cache_write`/`cache_read` came back 0: the system prompts sit
under the model's minimum cacheable length, so `cache_control` is currently a no-op.

The deterministic layer (`scripts/canonical.py`) was built from these failures and
fixes 6 of the 18 at zero marginal cost; three more were taxonomy rulings the model
had already answered correctly, taking the verified rate to **91.7%**. Seven more
depend on the v2 prompt/taxonomy changes and need a re-run to confirm (ceiling 98.1%).

A third vocabulary, `data/format_tokens.json`, settles the category for products
identifiable only by a brand's hardware name — "Select Briq V2" and "Florist Farms
Rechargeable OVL" are vapes with no vape word in them, so the model reads "1G
<something>" and answers concentrate. Of The Plug's 228 `other`-bucket rows, 24 carry
no generic vape token at all; the curated tokens settle 23 listings deterministically.
It is consulted *before* the model call, so the category it fixes also gives the model
the right subtype rails, and it overrules the model's answer afterwards.

Taxonomy rulings encoded in v2: beverages are dosed in mg, not volume; topical scent
names ARE strains; version suffixes ("2.0") stay in the strain; concentrate
`diamonds` is its own subtype. `_ENRICH_VERSION` in `scripts/enrich.py` stamps every
cache entry — bump it with any prompt/rail change and stale rows re-enrich themselves
rather than needing cache files deleted by hand.

## Audit sweep (full output, no labels)

`audit.py` complements the eval: it queries FULL enriched output — scrape CSVs or the
live listings table — and surfaces suspects (category/name token conflicts, near-
duplicate strain spellings within a brand, product lines leaking into strains, variant
unit anomalies, brand spelling splits, unenriched rows). Use it as the query layer of
an audit loop: run it, have an agent (or a human) adjudicate the JSON, then encode
confirmed fixes as `brand_aliases.json` entries, CATEGORY_MAP additions, or prompt
changes — deterministic fixes beat re-prompting.

```bash
python evals/enrich/audit.py --csv data/scrapes/the-plug-crown-heights_*.csv --json audit.json
python evals/enrich/audit.py --db     # active listings via DATABASE_URL
```

## Adding cases

Append to the relevant `cases/*.json`. Keep `expect`/`canonical` to fields with a single clear
right answer; leave subjective fields out so the pass-rate stays meaningful. New `*.json` files
in `cases/` are picked up automatically.
