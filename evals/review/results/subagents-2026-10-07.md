# Review agent: Sonnet, Opus and Haiku 5.5 (2026-10-07)

**Setup.** The 72 labelled queued listings in `cases/` (35 gold cases, 37 Hold Up Roll Up
rows), reviewed by Claude Code subagents rather than the API loop:

- **Models:** the `sonnet`, `opus` and `haiku` aliases. `haiku` ran Claude Haiku 5.5,
  released the same day.
- **Instructions and tools:** the same prompt (`review_agent.system_prompt`) and the same
  read-only tools, called through `scripts/review_cli.py`.
- **Batches:** 13 per model, grouped by store, at most 6 listings each.

Answers, catalog proposals and per-listing scores are in `subagents-2026-10-07.json`.

**Scoring.** As `run_review.py` scores. "Applied" is what the pipeline would write: an
unsure answer keeps the first pass.

## Accuracy

| | Fields right | Listings fully right | Fields fixed / broken | Listings left unsure |
|---|---|---|---|---|
| First pass (Jev only) | 246/279 (88%) | 50/72 (69%) | | |
| Sonnet, applied | 274/279 (98%) | 68/72 (94%) | 32 / 4 | 3 |
| Opus, applied | 272/279 (97%) | 67/72 (93%) | 32 / 6 | 3 |
| Haiku 5.5, applied | 261/279 (94%) | 61/72 (85%) | 21 / 6 | 13 |

On the 37 Hold Up Roll Up rows, today's production path gets 153/168 of the fields it
answers right (91%).

Stated confidence:

- **"Sure":** right on every field for Sonnet (60/60) and Opus (91/91); Haiku 36/37.
- **"Likely":** right on 98% (Sonnet), 96% (Opus) and 96% (Haiku).

### By field (applied)

| Field | n | First pass | Sonnet | Opus | Haiku 5.5 |
|---|---|---|---|---|---|
| category | 70 | 69 | 70 | 70 | 70 |
| subtype | 56 | 55 | 56 | 56 | 55 |
| strain | 53 | 42 | 50 | 48 | 47 |
| product line | 35 | 25 | 34 | 33 | 26 |
| size | 65 | 55 | 64 | 65 | 63 |

## Haiku 5.5: behind, and unsure too often

- **Product lines.** It got 26 of 35, against 34 and 33.
  - It takes format words for lines, which `CONVENTIONS.md` rules out: "Drops" on Doctor
    Solomon's Unwind Drops, and "Hash Rosin Nano Gummies" on two Vacation gummies.
  - It misses Rove's Premier line on a Minibar, and files that Minibar as a pod rather
    than an all-in-one.
- **Unsure on 13 listings, against 3.**
  - Seven of the 13 were already right in the first pass, and Haiku's own answer agreed.
    Each of those would cost a person a look for nothing.
  - Its unsure answers were right on 48 of 52 fields: it doubts answers it has right.
- **One wrong "sure".** It left the strain of Layup's Iced Tea Variety Pack empty
  ("Iced Tea is the format"); the label wants "Iced Tea Variety".
- **The convention disputes below.**
  - It sides with the labels on the dog oils (no strain).
  - It leaves TOKE and Harney's Spicy Pound Town unsure.
  - On Harney's Sleep tea it reads line = name, like the other two.
- **It looks less.** It made 42 tool calls a batch, against 80 (Sonnet) and 67 (Opus).

## What is left: convention disputes, not mistakes

- **Dog oils** (holdup-043, hur-087, hur-089). Sonnet and Opus give the strain as
  "Small Dog", "Medium Dog" or "Large Dog"; the labels have none.
  - Head & Heal also sells human 600mg and 1200mg oils that would otherwise share all
    five fields, so this reading avoids a collision.
  - Decide and relabel.
- **TOKE Blueberry Glue** (coney-038).
  - Sonnet says 1.5g: TOKE's site and every other NY store sell 3 × 0.5g.
  - Opus marked it unsure.
  - The label says 0.5g, and the listing gives no count or price.
- **Harney Brothers** (hur-351, hur-584).
  - The models read the catalog's "Wake & Bake | Yaupon Mint" pattern as line = name,
    strain = blend.
  - The labels follow the stores: strain = name, no line.
  - The catalog's Harney entries are inconsistent. Curate them, then relabel.
- **Layup Iced Tea Variety Pack** (hur-778). Sonnet's strain is "Iced Tea"; the label
  wants "Iced Tea Variety". Opus matched the label.

## Labels corrected by this run

- **hur-252 and hur-321:** Sonnet and Opus independently found the THC total on the
  store page.
  - Doctor Solomon's: 25mg (475mg CBD, the 19:1 ratio).
  - Juniper Jill: 300mg (600mg CBD, 2:1).

  Both had been labelled with no size.
- **gold-015:** now follows Eaton's brand-site entry: strain Apple, line Apple-A-Day.

## Effort per batch (about 5.5 listings)

| | Tokens | Tool calls | Time |
|---|---|---|---|
| Sonnet | ~179k | 80 | ~11 min |
| Opus | ~148k | 67 | ~10 min |
| Haiku 5.5 | ~151k | 42 | ~9 min |

These are Claude Code subagent figures. They include Claude Code's own prompt on every
turn, so they don't price the API loop in `review_agent.py`.

## Found along the way

- **Catalog proposals:** 189 in all (63 Sonnet, 62 Opus, 64 Haiku), all in the JSON for
  the daily audit. The ones worth acting on:
  - **1906 Drops sizes are inflated:** "2pk 20mg" should be 10mg, "4pk 40mg" should be
    10mg, and the Genius "20pk" is a 30pk.
  - **Head & Heal:** the catalog holds tinctures only.
    - It lacks the spray, the pet oils and the 600mg Focus CBG oil.
    - Its Focus and Focus Blend entries may be duplicates.
  - **Eaton:** a duplicate "Apple A Day" entry.
  - **Papa & Barkley:** a stray "Releaf Releaf" entry.
  - **Layup:**
    - a duplicate "Futbol Punch";
    - the Lemonade Variety Pack is review-matched to the single can.
  - **Missing entries:** Rove Premier Green Crack.
  - **Censored strain:** Ayrloom ATF's catalog strain is spelled "Fu*k".
- **Brand spellings that miss their catalog.**
  - The gold inputs' GRON, Caminos, Eaton and Jetty no longer occur in live data.
  - About 70 live listings still miss their catalog by spelling, for example "5Boro
    Cannabis", "bouk", "Canna Cure Farms" and "Preferred".
- **Tooling:**
  - **Apostrophes:** quoting JSON with an apostrophe broke shell commands, and the agents
    retried. The CLI now takes the JSON on stdin.
  - **Web search:** the shared search budget ran out partway through, so later batches
    used direct page fetches.
  - **Size readings:** the tool's pack readings missed a few cases, which the agents
    caught: TOKE's 3-pack, and REMZzz's two THC figures.
