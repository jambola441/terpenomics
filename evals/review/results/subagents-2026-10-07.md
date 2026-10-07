# Review agent, Sonnet vs Opus (2026-10-07)

**Setup.** The 72 labelled queued listings in `cases/` (35 gold cases, 37 Hold Up Roll Up
rows), reviewed by Claude Code subagents rather than the API loop:

- **Models:** the `sonnet` and `opus` aliases.
- **Instructions and tools:** the same prompt (`review_agent.system_prompt`) and the same
  read-only tools, called through `scripts/review_cli.py`.
- **Batches:** 13 per model, grouped by store, at most 6 listings each.

Answers, catalog proposals and per-listing scores are in `subagents-2026-10-07.json`.

**Scoring.** As `run_review.py` scores. "Applied" is what the pipeline would write: an
unsure answer keeps the first pass.

## Accuracy

| | Fields right | Listings fully right | Fields fixed / broken |
|---|---|---|---|
| First pass (Jev only) | 246/279 (88%) | 50/72 (69%) | |
| Sonnet, applied | 274/279 (98%) | 68/72 (94%) | 32 / 4 |
| Opus, applied | 272/279 (97%) | 67/72 (93%) | 32 / 6 |

On the 37 Hold Up Roll Up rows, today's production path gets 153/168 of the fields it
answers right (91%).

Stated confidence is well calibrated. "Sure" answers were right on every field: Sonnet
60/60, Opus 91/91. "Likely" answers were right on 98% (Sonnet) and 96% (Opus).

### By field (applied)

| Field | n | First pass | Sonnet | Opus |
|---|---|---|---|---|
| category | 70 | 69 | 70 | 70 |
| subtype | 56 | 55 | 56 | 56 |
| strain | 53 | 42 | 50 | 48 |
| product line | 35 | 25 | 34 | 33 |
| size | 65 | 55 | 64 | 65 |

## What is left: convention disputes, not mistakes

- **Dog oils** (holdup-043, hur-087, hur-089). Both models give the strain as "Small Dog",
  "Medium Dog" or "Large Dog"; the labels have none. Head & Heal also sells human 600mg
  and 1200mg oils that would otherwise share all five fields, so the models' reading
  avoids a collision. Decide and relabel.
- **TOKE Blueberry Glue** (coney-038).
  - Sonnet says 1.5g: TOKE's site and every other NY store sell 3 × 0.5g.
  - Opus marked it unsure.
  - The label says 0.5g, and the listing gives no count or price.
- **Harney Brothers** (hur-351, hur-584). Both models read the catalog's "Wake & Bake |
  Yaupon Mint" pattern as line = name, strain = blend. The labels follow the stores (strain
  = name, no line). The catalog's Harney entries are inconsistent; curate them, then
  relabel.
- **Layup Iced Tea Variety Pack** (hur-778). Sonnet's strain is "Iced Tea"; the label wants
  "Iced Tea Variety". Opus matched the label.

## Labels corrected by this run

- **hur-252 and hur-321:** both models independently found the THC total on the store
  page: Doctor Solomon's 25mg (475mg CBD, the 19:1 ratio) and Juniper Jill 300mg (600mg
  CBD, 2:1). They had been labelled with no size.
- **gold-015:** now follows Eaton's brand-site entry: strain Apple, line Apple-A-Day.

## Effort per batch (about 5.5 listings)

| | Tokens | Tool calls | Time |
|---|---|---|---|
| Sonnet | ~179k | 80 | ~11 min |
| Opus | ~148k | 67 | ~10 min |

These are Claude Code subagent figures. They include Claude Code's own prompt on every
turn, so they don't price the API loop in `review_agent.py`.

## Found along the way

- **Catalog proposals:** 125 in all (63 Sonnet, 62 Opus), all in the JSON for the daily
  audit. The ones worth acting on:
  - **1906 Drops sizes are inflated:** "2pk 20mg" should be 10mg, "4pk 40mg" should be
    10mg, and the Genius "20pk" is a 30pk.
  - **Head & Heal:** the catalog holds tinctures only. It lacks the spray, the pet oils
    and the 600mg Focus CBG oil, and its Focus and Focus Blend entries may be duplicates.
  - **Eaton:** a duplicate "Apple A Day" entry.
  - **Papa & Barkley:** a stray "Releaf Releaf" entry.
  - **Layup:** a duplicate "Futbol Punch", and the Lemonade Variety Pack is
    review-matched to the single can.
  - **Missing entries:** Rove Premier Green Crack; Ayrloom ATF's catalog strain is
    censored ("Fu*k").
- **Brand spellings that miss their catalog.** The gold inputs' GRON, Caminos, Eaton and
  Jetty no longer occur in live data. About 70 live listings still miss their catalog by
  spelling, for example "5Boro Cannabis", "bouk", "Canna Cure Farms" and "Preferred".
- **Tooling:**
  - **Apostrophes:** quoting JSON with an apostrophe broke shell commands, and the agents
    retried. The CLI now takes the JSON on stdin.
  - **Web search:** the shared search budget ran out partway through, so later batches
    used direct page fetches.
  - **Size readings:** the tool's pack readings missed a few cases (TOKE's 3-pack,
    REMZzz's two THC figures), which the agents caught.
