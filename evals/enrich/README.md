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

## Adding cases

Append to the relevant `cases/*.json`. Keep `expect`/`canonical` to fields with a single clear
right answer; leave subjective fields out so the pass-rate stays meaningful. New `*.json` files
in `cases/` are picked up automatically.
