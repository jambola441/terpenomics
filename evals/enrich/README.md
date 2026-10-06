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

## Category-owned enrichers — merch off the model entirely (2026-08-30)

`scripts/enrichers.py` gives each category an owner that declares whether it needs a
model at all. `MerchEnricher.needs_model = False`, so merch rows are answered from
the name before a batch is ever formed: **1,070 of 16,031 live listings (6.7%) never
reach the model**, and their answers stop moving run to run.

Equivalence was checked before the eval, not after: `backfill_merch_identity.py`
repointed at the enricher reports **0 rows would change** across 1,300 live merch
listings, and a 14-row A/B of committed HEAD against the registry agreed on 13 and
differed on 1 (in the registry's favour).

### The gold suite said −13.75 cases. It was wrong, and it was also right.

The first run after the registry scored 236/268, i.e. −13.75 against the 249.75
baseline. Three separate things were tangled in that number, and only running the
comparison separated them:

1. **13 of the 18 new failures were stale labels, not a regression.** Every one was
   `subtype: got 'lighter'/'paper'/'battery'/... want 'merch'` — labels written when
   merch had a single subtype, before v6 widened the rail. Running committed HEAD on
   the same 14 rows scored **0/14 too**: those cases had been failing since v6 and the
   baseline predates it. The labels are now updated to the current taxonomy.
2. **The remaining failures were the known flaky set** — `holdup-017`, `holdup-034`,
   `holdup-043`, the `x-camino` cluster — none of which is merch, so none of which the
   registry can touch.
3. **A real regression the suite could not see at all.** Routing on `_hint_category`
   means a row the *scraper* called merch is never offered to the model, and the model
   had been quietly fixing those. Joining the scrape CSVs against the DB found
   **20 of 1,090 routed rows (1.8%)** that HEAD had reclassified away from merch —
   19 vaporizers sold as accessories ("Covert 2.0 Blue Cartridge Vaporizer -
   Accessories - Kind Pen", "PAX Plus | Periwinkle") plus one gift card. No gold case
   covers this, so the suite scored it as an improvement.

The fix is curated, not prompted: three `format_tokens.json` entries — `*/Vaporizer`,
`*/Exxus`, `PAX/Plus`, `Cartisan/Pillar` — divert 19 of the 20 before the merch route
fires. The 20th is `HURU Gift Card`, where HEAD answered `other` and the registry
answers `merch`/`gift-card`; that one is a win.

Blast radius was measured before adding them, and it is why they are tokens and not
brand rules: `Vaporizer` matches 104 active listings and all 104 are vape hardware,
`Exxus` matches 6 and all 6 are. **Brand-wide rules for Yocan and Wulf were rejected
on the same measurement** — both sell genuine accessories (batteries, knife kits,
torches) beside their vaporizers, and a blanket rule would have dragged 9 correct
merch rows into `vaporizers`.

### Subtyping merch from descriptions — measured and rejected

376 of 1,300 live merch names carry no form word. Falling back to the description
recovers a subtype for 173 of them, so it looks like a free 46% coverage gain. A
sample of 25 was **wrong roughly 10 times**: merch descriptions are sales copy that
names adjacent gear constantly — "Hemp Wick" reads as paper, "Puck Press" as pipe,
"Raw - Original Tips 50ct" as paper, a Dr.Dabber vape pen as dab-tool. A confident
wrong subtype is worse than the category default, so the gap gets closed with name
tokens. Those 376 rows are the next piece of work; `tips`, `beaker`, `downstem`,
`sherlock` and a bare width token ("Elements King Size Wide" is a paper) are the
obvious candidates, each needing its own blast-radius check.

### Where it landed

| | runs | mean | sd | range |
| --- | ---: | ---: | ---: | ---: |
| baseline (pre-v6) | 4 | 249.75 | 0.50 | 249–250 |
| registry + corrected labels | 5 | **248.80** | 1.64 | 247–251 |

−0.95 cases, ~1.2 standard errors — inside the noise, and the ranges overlap. No merch
case fails in any of the four runs. Every residual failure is a long-standing class
already catalogued below: topical `Nmg` never reaching `variant` (5 cases), 10-pack
preroll math (4), and the `strain` overload on edibles and topicals (6).

The sd tripling (0.50 → 1.73) is worth watching but is not established: with n=4 the
estimate is very imprecise, and pulling 14 rows out of the batches moves every batch
boundary, which given that this suite's noise is **batch-correlated** is enough on its
own to reshuffle which cases flip.

### Two labels I am not confident in

Both are recorded as a `note` on the case rather than left implicit:

- `gold-097` *Human Grade - 5" Recycler 1A Dab Rig* → `bong`. A dab rig is not a bong.
  They share a rail today because splitting them needs a `rig` subtype.
- `spot-044` *Matte Black 3.2v Auto Start 510 Vape Cartridge Battery & Charger* →
  `charger`. This is a battery sold *with* a charger; `charger` wins only because token
  order puts it first (so a plain "510 USB Charger" is not read as a battery).

## Closing the merch token gap — and a prompt regression I caused doing it (2026-08-30)

376 of 1,300 merch names carried no subtype token. Widening the token table closed
most of that gap, and cost 3 cases on the way for a reason worth writing down.

### The tokens

Every candidate was measured against all 16,031 live listings before adoption —
how many rows it newly covers, what those rows' stored subtype already is, and
whether it outranks a token that should win instead.

| added | joins | newly covered | stored subtype already agreed |
| --- | --- | ---: | --- |
| `beaker`, `hookah` | bong | 16 | 16/16 |
| `sherlock`, `steamroller`, `gandalf*`, `taster`, `hammer` | pipe | 16 | 16/16 |
| `hot knife`, `knife kit`, `nectar collector`, `terp pearls`, `dab station`, `poker` | dab-tool | 24 | 24/24 |
| `grynder` | grinder | 4 | 4/4 |
| `jersey`, `beanie`, `jacket`, `shorts`, `sweater`, `sweat pants/shirt`, bare `shirt` | apparel | 16 | 16/16 |
| `bowl` | **new subtype** | 15 | — |
| `downstem` | **new subtype** | 14 | — |
| `cotton buds`, `resin blaster`, `air sanitizer`, `odor` | cleaning | 15 | 6/15 |
| `butane`, `matches`, `hemp wick` | lighter | 11 | 2/11 |
| `case`, `bag`, `dugout`, `caddy`, `doob tube` | storage | 20 | 12/20 |
| bare `tip(s)` | filter-tip | 41 | 32/41 |

Token coverage went **71.1% → 84.9%** (924 → 1,104 of 1,300). With the
model-answer fallback on top, only **106 rows (8.2%) are still the generic
`merch`**. The backfill changed 55 stored subtypes, and merch product rows went
**892 → 889** — a small *merge*, not a split, because several of these unified
groups that were already split across two subtypes (Ozium's air sanitiser sat in
`cleaning` at 8oz and `merch` at 0.8oz).

Two rules needed care:

- **Bare `tip(s)` cannot sit beside the strong tip rule.** Papers, cones and wraps
  are all sold "with tips", and at the front of the order the modifier outranked the
  head noun — it dragged 7 papers and 3 cones into `filter-tip`. Fixed two ways: a
  `for_tokens()` hook strips the "w/ tips" phrase before any rule runs, and the bare
  rule is placed near the end so anything earlier wins. `hose` and `tube` are excluded
  outright — a "Glass Hose Tip" is a bong part, a "Pre-Roll Tube with a Glass Tip" is
  a tube.
- **`bowl` and `downstem` must come after bong, pipe and dab-tool.** A piece that
  merely *has* a bowl is not a bowl. That keeps "Bong Bowl", "Beaker Ufo Bong With
  Flower Bowl" and "Quartz Banger Bowl" where they were.

**Rejected:** `screens` → filter-tip. It gains 2 rows and costs 7 — pipe and grinder
sets that include a screen would flip — and a bowl screen is not a filter tip anyway.

**One known miss:** `10" 9mm Indigo Double Downstem USA Color Mouthpiece …` is a 10"
bong described by its parts, and now reads as a `downstem`. One row against 53 correct
changes; a rule for it would be fitted to that row, so it stands.

### The regression: a subtype rail is part of the prompt

Adding `bowl` and `downstem` scored **245.75** over 4 runs against 248.80 — −3.05
cases, t ≈ −3.2, outside the noise. Every one of the 14 merch gold cases passed in
every run, so the damage was entirely in categories the tokens never touch.

The mechanism: `_SUBTYPE_LINES` interpolates **`SUBTYPES` into the classify prompt**.
Widening the merch rail rewrote the prompt for all 268 cases. This is the same failure
this repo keeps hitting — *every regression this cycle came from a prompt edit* — and
this time the edit was invisible, a side effect of a data change two files away.

The fix makes it structurally impossible rather than merely fixed: `_SUBTYPE_LINES`
now skips any category whose owner declares `needs_model = False`. Merch is settled
from the name before a batch is formed, so the model never needs its rail, and merch
taxonomy changes can no longer perturb anything else.

| arm | runs | mean | sd |
| --- | ---: | ---: | ---: |
| registry only (previous commit) | 5 | 248.80 | 1.64 |
| \+ tokens, merch rail still in the prompt | 4 | **245.75** | 1.26 |
| \+ tokens, merch rail out of the prompt | 4 | **248.50** | 3.00 |

Back inside the noise (−0.30 vs the previous commit), with all 14 merch cases passing
in all four runs.

**No `_ENRICH_VERSION` bump.** The stamp exists to invalidate cached answers, and
merch rows now bypass the cache entirely. Exactly one live row reaches the merch path
with a cached answer — one the scraper called something else and the model moves into
merch — and the new `*/Vaporizer` format token settles that one first. A bump would
re-enrich all 16,031 listings (~$5-6) to fix nothing.

### What this bought in enrich.py

`scripts/enrich.py` went **1,117 → 1,007 lines**, and its 44 merch mentions are down to
two. `_merch_size`, `_merch_pack`, `merch_variant`, `_MERCH_COLOR`, `_MERCH_FLAVOR`,
`merch_strain` and `_TOKENS["merch"]` are gone — `merch_strain` was not just dead but
wrong, still returning a colour after colour moved to `attributes`. `SUBTYPES["merch"]`
is now read from the enricher, so a new merch subtype cannot be added to the tokens and
forgotten in the rail.

The two model-answer appliers were **not** dead and were not deleted: a row hinted as
another category can still come back `merch` from the model. They now ask the owning
enricher for the subtype, variant and strain, so the registry governs both paths.

## Jev classifies, code sizes, Haiku writes text (2026-10-04)

Pass A asked Haiku three things: category, subtype and size. The first two are
picks from taxonomy.py's rails, which is the only kind of question Jev
(`typesafe/jev-1.13`, [`scripts/jev.py`](../../scripts/jev.py)) answers, with a
calibrated probability, for input tokens only. Jev cannot write text, so the size
had to go somewhere else. Now the default (`ENRICH_CLASSIFIER=jev`):

1. **Jev** answers category and subtype ([`scripts/jev_classify.py`](../../scripts/jev_classify.py)):
   one request per listing, asking the category and the subtype within each
   category at once. The same curated-token overrides as pass A follow.
2. **Code** writes the size when the store's figure is unambiguous
   (`enrich.stated_size`): a weight as the store states it (pass A is told to
   prefer it), a dose as the package total under the 100mg cap (pass A is told
   to multiply). It refuses when the name and the size field disagree, or when
   more than one dose is named (THC beside CBD).
3. **Haiku**, one call, writes strain and product line, and the size where code
   refused (`_EXTRACT_PROMPT_SIZED`).
4. Rows where Jev's probability is under 0.80 (`ENRICH_JEV_MIN_CONFIDENCE`), or the
   call failed, take the old path: pass A and pass B. On the gold suites that is
   7% of rows, and every wrong Jev answer was among them.

`ENRICH_CLASSIFIER=llm` is the old pipeline, unchanged, and the rollback.

**A/B, all nine case files** (302 cases), `haiku-or`, arms interleaved, catalogs off.
Haiku-only has nine runs; the other arms have six each.

| arm | cases passed (of 302) | category | subtype | strain | line | size | rows that changed between two runs: any field / size | $/run | s/run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Haiku only (before) | 278.7 (277–282) | 100% | 98.3% | 98.0% | 69.4% | 97.2% | 29.4 / 12.9 | $0.164 | 16 |
| Jev + Haiku writes the size | 281.7 (280–284) | 100% | 98.5% | 97.9% | 79.2% | 97.3% | 35.1 / **19.6** | $0.122 | 30 |
| **Jev + code sizes + Haiku** | **285.2 (281–289)** | 100% | 98.5% | 98.4% | 81.7% | **98.8%** | **26.1 / 8.9** | **$0.108** | 28 |

- **More accurate, more consistent, 34% cheaper.** +6.5 cases over Haiku alone,
  every field equal or better, and fewer answers move between runs. That last
  column matters most here, because `products` is a view keyed on these strings
  (see the DeepSeek comparison below).
- **The middle row is why code writes the size.** Moving the size into pass B
  (one longer prompt for strain, line and size) made sizes *less* stable: 19.6
  rows changed between runs against 12.9. One run lost a whole batch of edible and
  topical sizes to "100mg". Code answers 74% of the sizes Jev's rows need, the
  same way every time.
- **Slower.** Jev is one request per listing, against Haiku's 50-item batches.
  That adds about 12s per 300 rows with 8 workers: under a minute for the largest
  store's full re-enrichment, and nothing on a normal day.
- **Caveats.** I wrote Jev's option text on a dev split (The Plug, categorization,
  common errors). Two descriptions were corrected there: "badder" is `other`, not
  `resin`, and a live resin gummy is an edible. On the held-out suites Jev alone
  scored category 146/146 and subtype 131/132. The size rule's two refusals came
  from its four gold misses, so check it outside the gold too. On 1,703 listings
  scraped today, code was willing on 82% and agreed with the size Haiku had stored
  on 96.1%. Most disagreements are stored values that are wrong: topicals in
  grams from before topical became a dose, and a gummy stored as "50g". A few are
  genuinely ambiguous ("4c" beside "20mg").

Reproduce: `python evals/enrich/run_eval.py --models haiku-or` (Jev) and
`--classifier llm` (Haiku only). Run each several times: one run moves ±3 cases.

## Jev picks strain and line too — and Haiku needs the easy rows (2026-10-04)

After Jev took category and subtype, Haiku's remaining job was strain and product line
(80% of the cost). Jev cannot write text, but a strain does not have to be written: in
all 263 gold cases with a strain, it is a phrase of the listing's name.

**How** ([`scripts/jev_extract.py`](../../scripts/jev_extract.py)):
- **Code proposes phrases.** It cuts the name at separators, sizes, potencies and
  ratios, and offers the pieces and their sub-phrases. That's 6.7 phrases per row,
  with the right strain among them for 99.6% of rows.
- **Jev picks the strain and the line,** with "none" offered first. A phrase in quotes
  is shown as quoted; that alone took lines from 13/20 to 20/20.
- **Bars:** a strain is taken at p ≥ 0.90, a named line at 0.80, "no line" at 0.50.
  Anything less, or the same phrase picked for both, goes to Haiku.
- **Size:** code now also reads it from the name when the size field is empty. On
  gold it's willing on 92% of rows and right on all of them (it was 87%). On 1,703 real
  listings it answers 91% and agrees with Haiku's stored size 96.3% of the time.

**The surprise.** The first A/B lost about 3 strain answers per run, and none of them
were Jev's picks. Tracing one run showed Haiku itself reading the leftover rows worse
once the easy rows were taken out of its batch:

| listing | Haiku with the full batch | Haiku with only the leftovers |
| --- | --- | --- |
| Lemon Candy Runtz (brand Runtz) | "Lemon Candy Runtz" | "Lemon Candy" |
| Unscented CBD lotion | no strain | "Unscented" |

The fix: Jev's settled answers ride along as context, as name and answer only. That
costs a few input tokens and no output (`_with_context`).

**A/B, all nine case files, six interleaved runs each:**

| | Jev classify + code sizes (before) | + Jev picks strain and line |
| --- | ---: | ---: |
| cases passed (of 302) | 285.5 | **287.7** |
| strain / product line right | 97.8% / 85.0% | 97.7% / **100%** (every run) |
| size right | 98.9% | 98.6% |
| rows that change between two runs | 33.0 | **22.5** |
| $/run | $0.107 | **$0.086** |

Jev settles 47% of rows outright. The rest get one Haiku call with the context.
- **Real listings:** at the same bars Jev settles 48% of 400 real listings. Its
  strains agree with what Haiku stored 98.5% of the time, and its lines 94.3%; most
  line differences are stored lines of doubtful value ("Exotic Flower", "Moonrock
  Infused").
- **Cost so far on the gold run:** Haiku alone was $0.164; Jev classification plus
  code sizes is $0.107; adding Jev strain and line is $0.086, 48% less than Haiku alone.

**Tried and not shipped:**
- **Jev picking the size where code declines.** Jev was 6/6 right on the gold rows
  where code could offer readings. But 11 of the 17 declined rows have no number in the
  name or size field at all, so it would settle about 2% of rows. Not worth the code.
- **Shorter Jev classification requests.** Asking the subtype only for categories in
  play cut Jev's tokens by 39%. But Haiku escalations rose from 7.9% to 13.9%, which
  cost more than the tokens saved.

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

## Model comparison — GPT-6 Luna vs Haiku 4.5 (2026-10-06)

A candidate enrichment model, measured against `haiku-or`, which is what the cron runs
(`SCRAPE_ARGS=--all --parallel --model haiku-or`). **Not adopted**: `DEFAULT_MODEL` stays
`haiku`, and the `luna` entry in `MODELS` (`openai/gpt-6-luna`, pinned) is there so the
result can be reproduced.

All nine case files (302 cases, 333 listings), catalogs off, three runs per arm with the
arms interleaved. The first table is the **production path**, `--classifier jev`: it is
the default and the cron overrides neither the flag nor `ENRICH_CLASSIFIER`. Jev
classifies, code sizes, Jev picks the strain and line it is sure of, and the model gets
what is left, which is 7% of the rows for classification and about half for strain and
line. The Jev calls are the same in both arms. Production also answers a listing from its
brand's catalog before any of this (`ENRICH_CATALOG_FIRST`, on by default); the harness
turns that off to measure the model, so the model's share of production is smaller still.

| production path, 3 runs each | haiku-or | luna |
| --- | ---: | ---: |
| cases passed, of 302 | 287.7 (287–289) | 286.7 (284–290) |
| gold suites, of 268 | 257.7 = 96.1% (257–259) | 256.7 = 95.8% (254–260) |
| the four type suites, of 34 | 30 every run | 30 every run |
| `gold_the_plug`, of 108 | 104.7 (104–105) | 103.7 (101–106) |
| `gold_the_spot_bk`, of 50 | 49.7 (49–50) | 49.3 (49–50) |
| `gold_hold_up_roll_up`, of 48 | 44.0 (44–44) | 44.0 (43–45) |
| `gold_coney_island`, of 56 | 54.7 (54–55) | 55.7 (55–56) |
| `gold_cross_dispensary`, of 6 | 4.7 (4–5) | 4.0 (4–4) |
| $ per run | $0.0859 | $0.0350 |
| — of which Jev | $0.0305 | $0.0305 |
| — of which the model | $0.0555 | $0.0046 |
| seconds per run | 51 (40–71) | 46 (39–57) |
| failed rows / model errors (empty or invalid JSON, timeout, cut off) | 0 / 0 | 0 / 0 |
| rows whose answer changed across the 3 runs, any field (of 333) | **26** | **44** |
| — by field: strain / line / size / subtype | 12 / 0 / 12 / 2 | 13 / 13 / 22 / 2 |
| rows that change between two runs (mean of the 3 pairs) | 17.3 | 33.3 |

Means, with the range over the three runs. On this path the four type suites score the
same in every run of both arms (categorization 10 of 12, variant_fix 9 of 10,
common_error 7 of 7, identity_cluster 4 of 5), and miss the same four cases: two
categorization labels that still expect the single `merch` subtype, a tincture labelled
`30ml`, and the Night Cap cluster. That is not the model.

`--classifier llm`, the rollback, where the model answers every row:

| llm path, 3 runs each | haiku-or | luna |
| --- | ---: | ---: |
| cases passed, of 302 | 279.7 (278–281) | 273.0 (272–274) |
| gold suites, of 268 | 250.7 = 93.5% (249–252) | 243.3 = 90.8% (242–244) |
| `gold_the_plug` / `spot_bk` / `hold_up` / `coney` | 105.7 / 49.0 / 41.0 / 50.0 | 103.7 / 46.7 / 40.0 / 49.0 |
| $ per run | $0.1639 | $0.0103 ($0.0152 cold, $0.0077 and $0.0080 on the repeats) |
| seconds per run | 17 (16–18) | 31 (26–36) |
| failed rows / model errors | 0 / 0 | 0 / 0 |
| rows changed across the 3 runs (of 333): total / line / size | 32 / 2 / 22 | 50 / 22 / 15 |
| expected fields left empty, per run | 9, 7, 11 | 13, 13, 12 |

### What the numbers say

- **Level on accuracy where it counts, behind when it has to do everything.** On the
  production path the totals differ by one case and the ranges overlap, which is inside
  the run-to-run spread of either arm. On the llm path Luna is 6.7 cases (2.2 points)
  behind and the ranges do not overlap: the model alone is not better than Haiku.
- **The model's cost fell 12×, but a run's only by 59%.** Jev is $0.0305 of every run,
  so $0.0555 → $0.0046 for the model is $0.0859 → $0.0350 for the run. Scaled by rows
  to the 19,106-listing fleet that is about $4.9 → $2.0 per full re-enrichment. A normal
  night only enriches new or changed listings: at $0.00026 a row all-in with Haiku, a
  thousand of them is $0.26, so the saving is cents. The earlier baseline stands:
  accuracy and consistency bind, not cost. Wall clock is the same on the production
  path (Jev's one request per listing sets it) and 1.8× slower on the llm path.
- **It is less steady, and in one field specifically.** 44 rows changed across three
  runs against 26 (33.3 against 17.3 between two runs); on the llm path 50 against 32.
  Three runs is thin for a count of rows, and both counts include Jev's own noise (see
  the floor below), but the excess is not spread evenly. Luna flips `product_line` on 13
  rows where Haiku flips none (22 against 2 on the llm path): `Reserve`, `Mega Dose` and
  `Fusion` come and go, `Bliss` appeared once on a Camino Chews whose name does not
  contain it, and `1:1` became the line of a tincture once. Its sizes flip more on the
  production path too (22 rows against 12).
- **Nothing broke.** No failed batch, empty reply, invalid JSON or timeout in any
  measured run of either arm, probes included.

### What a live call showed, and what changed in `enrich.py`

Checked with one raw call before any run (8 pass-B rows, the request path as it stood):

- **The request sends** `model`, `max_tokens` (4096 by default) and the two messages.
  No `temperature`, `response_format`, `seed` or reasoning setting, which is also how
  every other entry is called. `temperature` is not in Luna's supported parameters; a
  request with `temperature: 0` was accepted and the model reasoned just the same.
- **Reasoning is spent and billed by default**: 386 of the call's 514 completion
  tokens. `completion_tokens` already includes them: OpenRouter's own `usage.cost`
  priced the completion at exactly 514 × $0.50/M. Adding `reasoning_tokens` on top
  would bill them twice, so `reasoning_tokens` is now reported beside `output_tokens`
  (and in `summary.md`) and the cost still comes from `output_tokens` alone.
- **The prompt cache is billed too.** 1,493 of the call's 1,496 prompt tokens were a
  cache *write* at $0.125/M, 25% over input; reads cost $0.01/M. Treating them as plain
  input put that call 8% low. They are now split out of `input_tokens` and priced from
  the entry's `cache_write`/`cache_read`; an entry with no cache rate bills them as plain
  input, so no other model's cost moved. Re-running an eval sends byte-identical
  requests, which the cache then serves: $0.0152 on the first llm-path run, $0.0077 on
  the repeats. Plan on the cold figure, since production payloads differ every night.
- **A new per-model knob**, `params`, in the style of `batch_size`/`timeout`/
  `max_tokens`: extra chat-completions parameters sent on every request to that model.
  Luna's is `{"reasoning_effort": "low"}`; no entry sends anything it does not name.
- A reply cut off at `max_tokens` now says so in the `[model error]` line. A reasoning
  model can spend the whole budget thinking and return nothing, which used to read as
  "Expecting value: line 1 column 1". It never happened here.

### Choosing the reasoning setting

One suite (`gold_the_plug`, 108 cases), two runs per setting, `max_tokens` 16384 so a
cap could not decide it, on both paths. The unset default reasons about as much as
`medium` (3–5k reasoning tokens a run against 1k at `low`).

| `reasoning_effort` | production path: passed | llm path: passed | llm path: reasoning tok / run | llm path: s / run, longest call | llm path: rows changed r1→r2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `none` | 105, 104 | 101, 104 | 0 | 15 s, 8 s | 15 |
| `minimal` | 104, 106 | 106, 105 | 754 | 19 s, 12 s | 6 |
| **`low`** | 105, 102 | 105, 105 | 1,082 | 20 s, 12 s | 6 |
| unset | 105, 106 | 104, 105 | 4,152 | 31 s, 20 s | 11 |
| `medium` | 105, 105 | 104, 104 | 5,164 | 47 s, 34 s | 8 |
| `high` | 105, 104 | 104, 102 | 8,259 | 61 s, 42 s | 6 |

On the production path the model sees too few rows for any setting to show (103.5 to
105.5, and the same three cases fail in every arm). On the llm path `none` is the least
steady and its extra misses are scattered (`20MG x 2PK` left at `20mg`, two subtype
slips, an empty size, an invented strain); more thinking than `low` buys nothing (`high`
is no better, and its longest production-path call took 69 s against the 90 s timeout);
and `minimal` and `low` cannot be told apart at two runs. `low` it is: the same score and
steadiness as `minimal` with a little more room to think, at the cheap end of the cost
range, and the longest call at it took 12 s.

### Where Luna and Haiku differ

Cases where Luna passed fewer runs than Haiku: 9 on the production path, 18 on the llm
path. Classified by the field it got wrong:

| Luna's miss | production path (9 cases) | llm path (18 cases) | example |
| --- | ---: | ---: | --- |
| writes the store's size where a dose is wanted | 4 | 4 | `Camino - Sleep … 5:1 CBN 20pk`, store size `72g`: Luna `72g` (1 run in 3; every run on the llm path), want `100mg`. `gold-020` the same; `gold-023` `50.2g`; `coney-054/055`, 1000mg topicals, filed `1g` |
| trusts the store's size over the name | 1 | 1 | `Runtz - 28G Flower`, store `1/8 oz`: Luna `3.5g` (2 runs in 3), want `28g` |
| leaves the size empty | 0 | 3 | `Nordic Blueberry - 100MG Gummies`: no size (2 runs in 3) |
| strain trimmed or dropped | 2 | 3 | `Sour Orchard Peach 'Balance'` → `Orchard Peach` (2 runs in 3); `Apple-A-Day` → `Apple` |
| strain invented | 1 | 0 | `Old Pal x Babish - THC Infused Sugar` → `Infused Sugar` (1 run in 3), want none |
| product line missed or invented | 0 | 4 | Camino's quoted `'Balance'`, `"Bliss"`, `'Energy'` dropped on 1–2 runs in 3 |
| identity cluster splits | 1 | 2 | the Honeycrisp cluster's strain, three spellings |
| pack math | 0 | 1 | `Pineapple Float - 100MG 20pk` → `2000mg` on 2 runs in 3 |
| **category** | **0** | **0** | Luna never misses a category, as Haiku never does |

The shape is one habit: **Luna takes the escape hatch.** The size rules end "if unsure,
return hint_variant unchanged" (pass B's sized prompt says it in other words), and Luna
returns the store's figure (`72g`, `1g`, `30`) far more readily than Haiku writes the
dose from the name, and leaves the size empty where Haiku reads it. It is not weaker at
the arithmetic itself. Luna also passed more runs than Haiku in 6 cases on the
production path and 8 on the llm path, among them `coney-053` (`150MG THC : 450MG CBD`
drops, which Haiku sums to `600mg` every time), `holdup-023` (10mg tea sachets, `50mg`)
and `gold-018` (a Camino gummy Haiku calls `other`), and that is why the totals are
level. Both models fail the same nine cases in every production-path run: the two
`merch` labels, `var-tincture-ml`, `holdup-016`, `holdup-017`, `holdup-044`, `gold-013`,
and the `x-camino` and Night Cap clusters.

### No request knob makes it repeat itself

Haiku's run-to-run noise is why this repo calls consistency binding, so the levers were
tried: eight identical 50-row pass-B requests per setting, compared row by row.

| setting | distinct replies of 8 | rows (of 50) with more than one answer |
| --- | ---: | ---: |
| luna `low` | 8 | 8 |
| luna `low` + `seed: 0` | 5 | 7 |
| luna `low` + `temperature: 0` | 7 | 7 |
| luna `low` + both | 5 | 7 |
| luna `none` / `none` + `seed` / `none` + `temperature` | 6 / 5 / 6 | 8 / 6 / 10 |
| haiku-or, as the cron calls it | 5 | 6 |
| haiku-or + `temperature: 0` | **1** | **0** |

`seed` and `temperature` do nothing useful for Luna. Haiku, given `temperature: 0`,
repeated itself exactly: a one-line `"params": {"temperature": 0}` on `haiku-or` (the knob
now exists) is the cheapest consistency lever this comparison found. It is **not
applied**, because `haiku-or` is production. On the production path it moved the full
eval from 26 changed rows to 21 (288.3 cases passed, 287–290; three runs), and no
further: Jev's own probabilities move by about ±0.02 between runs, so it settles 149–158
of the 245 rows it is offered one run and a different set the next, and every row it
hands to the model in one run and keeps in another can differ whichever model answers.
That sets a floor of roughly 20 changed rows (the temperature-0 arm's 21) that no model
choice removes. Roughly, then, 5 of Haiku's 26 changed rows are its own sampling and
23 of Luna's 44; one three-run arm sets the floor, so read that as an estimate.

### Verdict

Do not replace Haiku. Luna is level on the production path and cheaper by pennies a
night, but not more accurate (2.2 points behind where it works alone), measurably less
steady (44 rows against 26, and a field Haiku never flips), and it offers no request
setting that would fix that. The first things to test, in order: `temperature: 0` on
`haiku-or`, over several nights rather than three runs, because it costs nothing and
bears on the property that binds; then, only if cost ever binds, Luna with the size
rule's escape hatch removed, as its own measured prompt change.

`openai/gpt-6-luna:batch` is half price ($0.05/$0.25 per M) and the same weights, and,
like the Haiku batch above, OpenRouter refuses it on `/chat/completions`
(`404 … cannot be used with the chat/completions endpoint (adapter OpenAIBatchAdapter)`,
checked 2026-10-06). It would be a submit → poll → retrieve rewrite, not an entry. Not
built.

Reproduce: three runs, copied aside because each run overwrites `results/` (which now
holds run 3 of the production-path comparison), then summarised by `compare_runs.py`,
which gives the pass counts, cost, seconds, failed rows and changed-row counts above.
`luna` needs `OPENROUTER_API_KEY` and the `openai` package:

```bash
for i in 1 2 3; do
    python evals/enrich/run_eval.py --models haiku-or,luna        # add --classifier llm for the rollback path
    mkdir -p /tmp/runs/run_$i && cp evals/enrich/results/{haiku-or,luna}.json /tmp/runs/run_$i/
done
python evals/enrich/compare_runs.py /tmp/runs/run_* --models haiku-or,luna
```

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
