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

**No `ANTHROPIC_API_KEY`?** Use `--models haiku-or` — same model
(`anthropic/claude-haiku-4.5`) over OpenRouter. Accuracy is comparable; **cost is not**
(OpenRouter bills $1.00/$5.00 per M vs Anthropic's $0.80/$4.00, ~25% higher), so don't
compare its cost column against a native `haiku` run.

**Gotcha — `ANTHROPIC_BASE_URL`.** The Anthropic SDK reads that variable from the
environment, and some agent runtimes (Claude Code among them) set it to a local proxy.
`_make_client` passes only `api_key`, so in such a shell the native `haiku` path will
silently route to the proxy rather than the API even with a valid key. Unset it for the
eval, or use `haiku-or`.

## Outputs (`results/`)

- `comparison.md` — per case, every model's answer side by side (✓/✗ vs expected, or split-detail for clusters).
- `summary.md` — per model: time, tokens, cost, and pass rate per eval type.
- `<model>.json` — full scored detail for debugging.

Enrichment runs with `brand_examples={}` (model only, no DB nudge) and clears the eval cache
each run, so the **current** prompts are always exercised.

## Gold dispensary sets

Five frozen suites, 284 listings total (~$0.12/model/run). Inputs are literal strings in
the case files — no scraping, no DB — so runs are comparable; only the model call is live.

| suite | n | store / platform | what it stresses |
| --- | --- | --- | --- |
| `gold_the_plug.json` | 108 | The Plug (Dutchie) | `Brand - Strain \| Size Format`; `other` = **vapes** |
| `gold_the_spot_bk.json` | 50 | The Spot BK (Tymber) | brand **last**, lineage + THC% inline, trailing shelf codes; `other` = **flower** |
| `gold_hold_up_roll_up.json` | 48 | Hold Up Roll Up (Tymber) | brand **absent from the name**; 64% of the menu is `other` |
| `gold_coney_island.json` | 56 | Coney Island (Dutchie) | **no descriptions at all**; variant column actively wrong (`.1g` for a 100mg gummy); `other` = **pre-rolls** |
| `gold_cross_dispensary.json` | 6 clusters / 22 rows | six stores | same product across stores must converge to one identity tuple |

Three stores, three different meanings of `other` — which is why hint override is the
single most load-bearing behavior in the pipeline.

`gold_cross_dispensary.json` is the one that measures what a wrong answer *costs*: a split
product group in the products view. It includes a matched pair — Ayrloom Honeycrisp as a
beverage and as a vape — that must converge within each cluster without merging across them.

```bash
python evals/enrich/run_eval.py --models haiku --cases 'cases/gold_*.json'
```

### The Plug set (first, most detailed)

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
first deepseek run reported 11/108 having burned 0 tokens: no call was made, so the
rule-based hints scored on their own. run_eval now fails loudly on a zero-token run.

Since checked against the live OpenRouter catalogue: **`deepseek/deepseek-v4-flash` is
a valid slug** — the cause was the missing call, not a bad name, so the "verify slug"
TODO is resolved. Its listed price is $0.0826/$0.1652 per M, slightly under the
$0.09/$0.18 in `MODELS`. Still unrun end to end here (no accuracy number for it yet).

## Full gold-suite run — v5, all five suites (2026-08-25)

First run of `_ENRICH_VERSION` 4 and 5, and the first run of the four newer suites.
All 268 cases / 284 listings, `anthropic/claude-haiku-4.5`.

**Transport caveat:** run via OpenRouter (`haiku-or`), not the native Anthropic
path — this environment has `OPENROUTER_API_KEY` but no `ANTHROPIC_API_KEY`. Same
model, same prompts; the OpenAI-compatible transport differs and OpenRouter bills
$1.00/$5.00 per M vs Anthropic's $0.80/$4.00, so **cost here runs ~25% high** and
absolute comparison to the recorded 97.2% is confounded. Accuracy comparisons
*within* this report are all same-transport and unaffected.

| suite | mean pass | range over 4 runs | n |
| --- | --- | --- | --- |
| `gold_the_plug` | 104.5 (96.8%) | 104–106 | 108 |
| `gold_coney_island` | 53.0 (94.6%) | 53–53 | 56 |
| `gold_the_spot_bk` | 46.75 (93.5%) | 46–49 | 50 |
| `gold_hold_up_roll_up` | 40.75 (84.9%) | 40–42 | 48 |
| `gold_cross_dispensary` | 4.75 (79.2%) | 4–5 | 6 |
| **total** | **249.75 (93.2%)** | **249–250** | **268** |

Per field, across the four item suites: **category 262/262 (100%)**, subtype 97.9%,
strain 97.9%, variant 97.3%, product_line 17/20 (85%). 98.1% of individual fields.

Two things this establishes:

- **`category` generalizes.** 100% across three stores with three different meanings
  of `other` (vapes / flower / pre-rolls) and one store with brand absent from the
  name. Hint override plus `format_tokens.json` is the most load-bearing and most
  portable part of the pipeline.
- **`product_line` does not, exactly as predicted.** The Plug 11/11 and Coney Island
  5/5, but The Spot BK **1/4** — the maps are seeded from The Plug's brands, and
  CAMINO is absent from `product_lines.json` entirely. This is a data gap, not a
  model failure: all three misses spell the line in quotes in the name
  (`Sour Orchard Peach 'Balance'`), so a curated entry converts them to string facts.

The Plug scored 104–106 against the recorded 105/108, i.e. **v4 and v5 changed
nothing measurable there** — the delta is inside the noise floor below.

## Noise floor — the same commit, run four times

Every prior conclusion attributed single-case deltas to prompt edits without knowing
run-to-run variance. Measured, it is large enough to invalidate that reasoning at the
suite level.

| level | spread over 4 identical runs |
| --- | --- |
| full-suite total | 249–250, sd **0.50 cases** (0.19pp) — stable |
| per suite | up to **±3 cases** (The Spot BK 46→49, ±6pp on 50 cases) |
| per case | **13/268 (4.9%) are non-deterministic** |

Only 244/268 cases (91%) pass on all four runs; 11 (4.1%) fail on all four; the
remaining 13 flip. So:

- **The full-suite total is a usable metric. A single suite's score is not.** A
  2-case per-suite improvement is indistinguishable from noise in a single run.
- **Noise is batch-correlated, not per-case independent.** The three Spot BK
  `product_line` misses flip in lockstep (all wrong, all wrong, all wrong, all
  right) because they share one Pass B batch — verified: rows 264/267/269, all in
  batch 6 at `batch_size=50`. The Spot BK's ±3 swing is really *one* batch event.
  Effective independent sample size for batch-correlated failure modes is ~6, not 284.
- Treat a per-suite delta as real only with replicates, or when it moves the
  full-suite total by more than ~1.5 cases.

## Description cap on Pass A — tested, not worth it

Pass A gets category/subtype mostly from the name's format words, so capping its
description while Pass B keeps the full text was projected to cut ~25% of cost.
Measured over 3 runs per condition, it cuts **3–5%**, and destabilizes the pipeline:

| cap | mean pass (sd) | input tokens | cost | vs base |
| --- | --- | --- | --- | --- |
| off | 249.75 (0.50) | 70,443 | $0.1497 | — |
| 120 chars | 248.33 (1.15) | 66,043 (−6.2%) | $0.1454 | −2.9% |
| 60 chars | 247.00 (**4.36**) | 63,319 (−10.1%) | $0.1426 | −4.7% |

The projection assumed cost tracks the description payload. It does not:

- **Output tokens are 52.9% of cost and are invariant to the cap** (15,851 → 15,867,
  +0.1%). Output bills at 5× input. The cap can only reach the input side, and only
  Pass A's half of it, so ~25% was never available.
- Accuracy falls monotonically, and **variance grows 8.7×** at cap=60 (sd 0.50 →
  4.36; The Plug swings 97–105). Truncation removes the disambiguating text
  unevenly, so which cases break changes per run.

Trading a stable pipeline for 3% is a bad deal at $0.21/dispensary. **Left off.**

The instrument is kept: `ENRICH_PASS_A_DESC_CAP` (chars, 0 = off, word-boundary
truncation) in `enrich.py`. One reason to revisit — gold-set descriptions are
pre-truncated at 300 chars (median 220), so this measures a *floor*. Production
descriptions are ~4× longer, where the input side is a bigger share and the cap
would save more. Re-test against real scrape CSVs before adopting.

## Merch had no identity at all (2026-08-27)

`_TOKENS` carried entries for vaporizers, edible, preroll, flower and concentrate
but **not merch**, so `classify_by_token` returned `None` for every accessory and
they fell through to `_CATEGORY_DEFAULTS["merch"] == "merch"`. `SUBTYPES["merch"]`
was `["merch"]` — a single allowed value — so `_valid_subtype` could not return
anything else even when the model tried. With strain and variant also blank, the
products VIEW was grouping merch on **brand alone**.

Measured across the fleet's 1,514 merch listings (7.7% of everything):

| | |
| --- | --- |
| product rows they collapsed into | **223** |
| distinct (brand, name) pairs | 1,496 |
| products merged away | **1,273** |

RAW: 183 listings → 1 product row. Blazy Susan: 108 → 1, so pink and purple,
cones and papers, 20pk and 50pk were all one product.

### The fix, and what each layer recovers

Three deterministic layers, all string facts about the name, none asked of the
model. Modeled over the same 1,514 rows:

| grouping key | product rows | % of ceiling |
| --- | ---: | ---: |
| brand only (the bug) | 223 | 15% |
| + subtype — 19 form-factor tokens | 309 | 21% |
| + variant — pack count, else size | 468 | 31% |
| + strain — colour or flavour | 765 | 51% |

Verified end to end on kaya-bliss-bay-ridge: its 215 merch listings went from
**57 to 143 product rows** against a 215 ceiling — 27% → 66%. Blazy Susan there
went 18 listings → 15 product rows.

Two rulings encoded:

- **Pack count beats a dimension.** "Pink 98mm Cones 20pk" and "... 50pk" differ
  by pack; 98mm is a spec they share. So `_MERCH_PACK` is tried before
  `_MERCH_DIM`.
- **Colour and flavour live in `strain`.** For merch, `strain` means "the variant
  of this thing" rather than a cultivar — the same reasoning that already puts
  topical scent names there. It is the only field that separates otherwise
  identical accessories without a schema change.

Token order matters and is load-bearing: `bong` before `pipe` (a "water pipe" is
a bong), `charger` before `battery` ("510 Thread USB Charger" is not a battery),
`ashtray` before `tray`, `filter-tip` before the generic patterns.

**This bumps `_ENRICH_VERSION` to 6, which invalidates every cached answer**, not
just merch — the stamp is per-entry but not per-category. A full fleet re-enrich
is ~$5-6. To pay only for merch, drop the `"category": "merch"` entries from
`data/enrich_cache/*.json` and leave the rest at v5; that is ~$0.40, at the cost
of the version stamp no longer describing what is in the cache.

## Model comparison — DeepSeek v4 vs Haiku 4.5 (2026-08-25)

Same gold suites, same prompts, `haiku-or` transport throughout. Haiku has 4 runs
(the noise-floor set); DeepSeek 2 each, except `-0813` which was cut after one.

| model | n | acc | sd | secs | out tok | $/run | $/fleet¹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **claude-haiku-4.5** | 4 | **93.2%** | **0.50** | **15** | 15,851 | $0.1497 | $10.07 |
| deepseek-v4-flash | 2 | 89.0% | 4.95 | 332 | 58,647 | **$0.0152** | **$1.03** |
| deepseek-v4-pro | 2 | 85.3% | 2.12 | 538 | 81,436 | $0.1346 | $9.05 |
| deepseek-v4-pro-0813 | 1 | 51.1% | — | 821 | 100,453 | $0.4054 | $27.27 |

¹ scaled from $/run to the 19,106-listing fleet.

**Haiku wins on every axis except price.** Three findings worth keeping:

- **"Pro" is worse than "flash", at 9× the cost.** deepseek-v4-pro scores 85.3% vs
  its cheaper sibling's 89.0%. Its per-token rate is roughly half Haiku's, but it
  emits **5× the output tokens**, so a run costs the same. Per-token price is not
  cost; verbosity is. The dated `-0813` pin is worse again — 51.1% and $0.41/run,
  mostly truncated JSON — and was cut after one run, a 42-point gap being 84× the
  noise floor.
- **The sd column decides it for this system.** deepseek-v4-flash's run-to-run
  variance is **10× Haiku's** (4.95 vs 0.50 cases). Since `products` is a VIEW keyed
  on the model's own strings, unstable output means product groups churn between
  runs. Consistency matters more than raw accuracy here, and that is the axis
  DeepSeek loses worst on — the 4.2pp accuracy gap is the smaller problem.
- **Wall clock is a real constraint at fleet scale.** 15s vs 332–821s on 284
  listings. Extrapolated to a fleet refresh, Haiku's ~11 minutes becomes ~6.5 hours.
  Part of this is that the DeepSeek entries run `batch_size=15` (vs 50) because they
  truncate JSON at larger batches — which is itself a robustness signal.

deepseek-v4-flash remains the one genuinely interesting option: **10× cheaper**
($1.03 vs $10.07 per fleet refresh). It is a reasonable fallback if cost ever
becomes the binding constraint. It is not one today — the README's own baseline
note stands: accuracy is binding, not cost.

### claude-haiku-4.5:batch — half price, but not reachable from here

Worth knowing since it is the same weights and therefore cannot differ on accuracy:
`anthropic/claude-haiku-4.5:batch` bills **$0.50/$2.50 per M, exactly half** the
sync rate. OpenRouter rejects it on `/chat/completions`:

```
404 — This model is only available through the Batch API.
      Use the /api/beta/batches endpoint instead.
```

So it is not a `MODELS` entry, it is a submit → poll → retrieve rewrite against an
async endpoint with a 24h SLA. For a nightly scrape → enrich → import run that
latency is free, and it would halve a fleet refresh from **$6.65 to $3.32**
(~$100/month at nightly cadence). Worth doing as plumbing; there is nothing to
eval, because the weights are identical.

A related trap found while checking slugs: `~deepseek/deepseek-v4-flash-latest`
(the tilde is part of the slug) currently **resolves to** `deepseek-v4-flash-0731`,
but bills $0.035/$0.280 against that pin's $0.040/$0.080 — cheaper input, 3.5× the
output rate. For output-light work the pin is cheaper. More importantly, a floating
alias changes weights without notice, which silently invalidates a frozen gold
suite. Pin models in the eval path.

## Fleet report — all 24 live stores (2026-08-25)

`dispensary_report.py` runs the audit checks **per store** and normalizes to
findings per 100 listings, so every menu can be ranked. Full output in
`results/dispensary_report.md` / `.json`.

```bash
python evals/enrich/enrich_csvs.py     --csv 'data/scrapes/*.csv' --model haiku-or
python evals/enrich/dispensary_report.py --csv 'data/scrapes/*.csv' \
    --md results/dispensary_report.md --json results/dispensary_report.json
```

25 stores, 19,106 listings, **579 suspects = 3.03 per 100**. Spread runs from
`emerald-dispensary-bk` at 0.2 to `garden-club-carroll-gardens` at 6.7 — a 30×
range, but every store lands in single digits.

| metric | fleet |
| --- | --- |
| rows landing in `other` | **8 of 19,106 (0.04%)** |
| strain fill | min 95.8%, median 99.2% |
| variant fill | min 95.2%, median 99.9% |

**The category result generalizes.** `category` held 100% on the gold suites;
across the fleet only 8 rows out of 19,106 fall through to `other`. CATEGORY_MAP
plus `format_tokens.json` now covers 25 stores, not just the one they were seeded
from. That is the strongest evidence so far for moving work out of the model and
into curated data.

**Suspect rate is not accuracy, and does not track it.** `hold-up-roll-up` is the
*worst* gold store (84.9% of cases) yet scores 3.3 suspects/100 — mid-pack. The
audit catches fill gaps, strain splits and line leaks; it is structurally blind to
the subtype and variant judgment errors that dominate the gold failures. Use the
rate to target curation, not to rank quality.

### Where the 579 findings sit

| check | n | what it implies |
| --- | ---: | --- |
| missing enrichment | 163 | rows with no strain/subtype in an enrichable category |
| lineage as strain | 125 | strain is just Indica/Sativa/Hybrid |
| category token conflict | 85 | 22 tinctures look like edibles, 18 merch look like prerolls |
| strain split | 85 | near-duplicate spellings within a brand (ruby farms 6, ayrloom 5) |
| line leaked into strain | 85 | see below |
| unmapped raw category | 4 | ready-to-add CATEGORY_MAP entries |

Four raw categories are unmapped and each is a one-line fix: `CBD (Non-Cannabis)`
(21 rows), `Pet CBD (Non-Cannabis)` (8), `Gift Cards` (4), `Infused Pre-Rolled
Flower` (2).

### The Plug moved platforms — its gold suite no longer mirrors production

The Plug left Flowhub for Dutchie (`theplug-brooklyn.dispensary.shop` → the store
now sits at `dutchie.com/dispensary/the-plug-brooklyn`, dispensaryId
`68dc46d938899896d40a1beb`; `dispensaries.json` updated). It scrapes cleanly again:
842 listings, 2.9 suspects/100, 99.5% strain fill, full descriptions.

But the migration invalidated the suite's premise. `gold_the_plug.json` is built
around "a whole raw category the scraper's CATEGORY_MAP missed — vapes landing in
`other`, testing hint override at scale". On the new Dutchie feed the raw
categories are clean:

```
Pre-Rolls 233 · Edible 204 · Vaporizers 190 · Flower 174 · Concentrate 29 · ...
```

**0% of the live store now lands in `other`.** The 108 frozen cases stay valid as a
regression test — that is what freezing is for, and the naming convention
(`Brand - Strain | Size Format`) is unchanged — but the store no longer exercises
the failure mode the suite was built to measure. Coney Island, the other
`other`-heavy suite, is gone entirely (marked `inactive`; its domain 404s at the
root). Of the three stores that gave `other` three different meanings, only
`hold_up_roll_up` is still live and still `other`-heavy.

If hint override at scale matters going forward, it needs a new gold set from a
store that still has the problem.

### The de-lining bug, measured at fleet scale

`gold-105` traced `_strip_line_from_strain` returning `stripped or strain`, so a
strain that is *nothing but* the product line keeps the line as its strain. Across
the fleet that is **24 of the 85 line leaks** — `Ayrloom` "Pillow Talk",
`Papa & Barkley` "Releaf", `Eaton Botanicals` "Apple-A-Day", `Off Hours` "Offline".
Returning `None` on a total match is a safe one-line fix worth 24 rows.

**The other 61 are not the same bug and must not be fixed the same way.** 72 of 85
leaks are on brands with no curated entry, where de-lining never runs at all — but
blindly de-lining with the *model's* product_line would corrupt real strains:

```
Weekenders     strain='Blue Dream'  line='Dream'    ->  de-lining gives 'Blue'
Camino         strain='Sour Deep Sleep Blackberry Dream'  line='Sleep'
Supernaturals  strain='Interspecies Erotica'  line='Erotica'
```

These are the model over-extracting a product line out of a genuine strain name,
not a strain that swallowed a line. De-line only against **curated** vocabularies,
never against the model's own guess — which is the whole argument for
`product_lines.json` over prompt instructions.

### Papa & Barkley Releaf / Relief, now with counts

The open spelling question has numbers: **`Releaf` 11 rows, `Relief` 2**, plus
`1906` using `Relief` as its own line and `Papa & Barkley` "Relief Balm" appearing
as a strain. `Releaf` as canonical is the majority spelling as well as the brand's
trademark. Still not encoded — your ruling.

## What is actually broken — the 11 always-fail cases

Failing on all four runs, so these are real defects rather than noise. Grouped by
root cause, with the deterministic fix each one implies. Together they are 11 of the
18.25 mean failures; the other ~7 are the flaky cases above.

| # | root cause | cases | fix |
| --- | --- | --- | --- |
| 5 | **mg dose in the name never reaches `variant` for topicals/balms/sprays** — `variant` comes back empty | `coney-054`, `coney-055`, `holdup-046`, `holdup-047`, `spot-048` | rule: when category is `topical`/`tincture` and variant is empty, take `\d+(\.\d+)?\s*mg` from the name (note `spot-048` writes it `1000.00mg`) |
| 3 | **CAMINO absent from `product_lines.json`** | `spot-030` Balance, `spot-033` Bliss, `spot-035` Energy | add the brand's lines; all three are quoted in the name |
| 2 | **descriptor read as strain** | `holdup-016` `Lemon Lavender Serenity`, `gold-022` `Milk Chocolate` | see below — `gold-022` is the v5 regression fix that **did not work** |
| 1 | **10-pack preroll weight** — 10 × 0.28g instead of 10 × 0.35g | `coney-050` (`holdup-014` flaky, same shape) | pack math rail, or a curated pack-weight default |
| 1 | **`Releaf` lands in `strain`** rather than being dropped | `gold-105` | see open question below |
| 1 | **Honeycrisp cluster splits 3 ways** — `Honeycrisp` / `Honeycrisp Apple Cider` / `Honeycrisp Cider` | `x-ayrloom-honeycrisp-beverage` | `strain_aliases.json` entry for Ayrloom |
| 1 | **tea sachet → `other`, want `beverage`** | `holdup-023` | `_TOKENS['edible']` already has `tea\s+sachet`; the row isn't reaching the edible branch — needs tracing |

The single highest-value item is the first: one regex fixes 5 of 11, and it is a
string fact about the name, not a model judgment.

### v5 did not do what it was meant to

`_ENRICH_VERSION` 5 was the ruling that "a format word alone is not a strain" —
written specifically for `gold-022`, `GR N Milk Chocolate Full Bar Sativa`, which
should answer `strain: Sativa`. It still answers `Milk Chocolate`, **0/4 runs**.
That is a fourth data point for the pattern already in this file: every regression
so far came from a prompt edit, and prompt edits have done the least work. This one
should move to `format_tokens.json`-style curated data or a post-model rule.

### Flagged for a human ruling — not encoded

Three gold labels look arguable; leaving them as-is rather than silently deciding:

- `holdup-016` — expects `strain: Lemon Lavender`, dropping `Serenity`. But
  `Serenity` reads like a **product line** (cf. CAMINO's `Balance`/`Bliss`/`Energy`,
  which the labels *do* treat as lines). If it is a line, the label wants
  `product_line: Serenity` too, and the case is mislabeled rather than failing.
- `holdup-046` — expects `strain: None` for `Unscented CBD Lotion`. Consistent with
  merch/topical null-strain, but the file's own taxonomy note says "topical scent
  names ARE strains", and `Unscented` is a scent name. `spot-048` cuts the other way:
  it expects `strain: Restore`, a topical scent/benefit name. One of these two is wrong.
- `holdup-043` — `Organic Medium Dog CBD Oil`: expects `strain: None`, model answers
  `Medium Dog` on 2/4 runs. `Medium Dog` is a size descriptor, not a strain, so the
  label looks right — but this is the same "descriptor as strain" failure as
  `gold-022`, and fixing one should fix both.

### Papa & Barkley `Releaf` / `Relief` — the open question

`Papa & Barkley -> ["Releaf"]` is **already** in `product_lines.json`, and `gold-105`
still fails: `product_line: Releaf` is set correctly but `strain: Releaf` stays.
Traced to `canonical._strip_line_from_strain`, last line:

```python
return stripped or strain   # "Releaf" minus "Releaf" -> "" -> falls back to "Releaf"
```

The fallback is deliberate ("returns strain unchanged if removing the line would
leave nothing") and right for a partial match, but wrong when the strain is
*nothing but* the product line — there is no strain then, and it should go to `None`.
Confirmed directly:

```
_strip_line_from_strain("Releaf Balm", "Releaf") -> 'Balm'     # correct
_strip_line_from_strain("Releaf",      "Releaf") -> 'Releaf'   # should be None
```

Two notes: `strain_delined` counts this as a de-line that did not happen, so that
stat over-reports; and this is a de-lining bug **independent of the spelling
question**, worth fixing first since it is what actually breaks the cluster.

On the spelling itself (`Releaf` at two stores, `Relief` at The Spot BK, a genuine
source typo): this is exactly the `strain_aliases.json` shape — one canonical
spelling, variants mapped onto it — except it needs the same mechanism for
`product_lines`. Recommend `Releaf` as canonical (it is the brand's actual trademark,
and two of three stores spell it that way), with `Relief` as the mapped variant.
Still your call; not encoded.

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

Taxonomy rulings encoded so far: beverages are dosed in mg, not volume; topical scent
names ARE strains; version suffixes ("2.0") stay in the strain; concentrate `diamonds`
is its own subtype; and a word that only restates the format is not a strain — "Milk
Chocolate" on a chocolate bar is the format, so the lineage (Sativa) is the strain,
while a strain that merely contains a format word ("Chocolate Diesel") is kept. `_ENRICH_VERSION` in `scripts/enrich.py` stamps every
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
