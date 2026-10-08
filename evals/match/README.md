# Catalog matcher eval

Measures the catalog matcher (`scripts/catalog_match.py`) against true labels. It reports
how often a trusted match picks the right product (precision) and how many listings
whose product is in the catalog get one (recall), at each bar a Jev pick could be
trusted at. Catalogs from a brand's own site and catalogs built from store listings
are reported apart, as they have separate bars (`CATALOG_MATCH_AUTO` 0.85 and
`CATALOG_MATCH_AUTO_BOOTSTRAP` 0.90).

The matcher's built-in `--eval` uses silver labels: listings where the lexical tier and
Jev already agree, plus a holdout. It can't see a wrong sibling picked when the right
product is present, or a product the matcher missed. This set can.

## Steps

```bash
DB_VIA_HTTP=1 python evals/match/build_sample.py                          # done: cases/sample.json
DB_VIA_HTTP=1 python evals/match/label_sample.py --model claude-sonnet-5-5  # needs ANTHROPIC_API_KEY
# or, without the key, Claude Code subagents driving scripts/review_cli.py (how the labels below were made)
# a person checks cases/spot_check.md (30 labels)
DB_VIA_HTTP=1 python evals/match/run_match.py                             # needs OPENROUTER_API_KEY
```

**`cases/sample.json`.** 300 live listings: 10 from each of 30 brands with catalogs, 15
whose catalog comes from the brand's site and 15 built from store listings. Each brand's
10 are spread over how the matcher last decided them (2 exact, 3 jev, 2 jev_review, 3
none, filled from the others where a stratum runs short). Seeded, so it rebuilds the
same.

**Labels** come from the review agent's match mode (`scripts/review_agent.py`,
`task="match"`). It searches the brand's catalog, works out the size, and checks other
stores and the web when the name doesn't settle it. It never sees what the matcher
decided: in this mode the other-stores tool hides recorded matches, strains and lines.
A label is one of:

- `entry_id`: the entry that is this product in this size;
- `product_entry_id`: the catalog has the product, but not in this size;
- both null: the catalog lacks the product.

Each label also has a confidence, the evidence, and the model that gave it. Unsure
labels are left out of the scoring.

**`run_match.py`** re-runs the matcher live on each labelled listing, with the lexical
tiers then Jev and no answer cache. It writes `results/summary.md`: a table per catalog
kind by bar, plus the listings trusted today that are wrong.

## Labels (2026-10-07)

The labels came from Claude Code subagents rather than the API. Each batch was one brand,
labelled by a subagent on the `sonnet` alias that drove `scripts/review_cli.py` in match
mode, with the same instructions and tools as `label_sample.py`.

Of the 300 cases:

- 210 are an entry;
- 26 are the product in a size the catalog lacks;
- 59 are products the catalog lacks;
- 5 are unsure and left out.

Of the 295 used, 230 labels are sure and 65 likely.

Two checks before use:

- **Early batches.** The first batches ran with a `search_catalog` that cut every list at
  25 entries without saying so (fixed since). Their not-in-catalog and product-only labels
  were rechecked against the full catalogs, and all hold.
- **Disagreements.** All 14 cases where the matcher picks another product were read
  against their labels; the results below say what they are.

The files:

- `cases/spot_check.md`: 30 labels for a person to check.
- `cases/proposals.json`: the 57 catalog fixes the labellers proposed. They are queued
  for the audit; nothing was changed.

## Results (2026-10-07)

The live matcher on the 295 used labels (`results/summary.md`):

| catalogs | listings | bar today | trusted | wrong | precision | recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| brand site | 148 | 0.85 | 84 | 4 | 95.2% | 62.0% |
| store-built | 147 | 0.90 | 79 | 1 | 98.7% | 72.9% |

Recall is the share of the listings whose product the catalog has (129 and 107) that get
a trusted match to the right product. When the product is right, the entry (the size) is
right 157 times in 158.

**The 5 trusted and wrong:**

- **3 are duplicate catalog entries.** The matcher took a second entry for the same
  product:
  - Grön's "Milk Chocolate Sea Salt" beside "Mini Bar 1:1 Milk Chocolate";
  - Off Hours' "Melt" beside "Melt Blueberry Pie";
  - Off Hours' "Party Party Animal" beside "Party Animal Passion Pop".

  The listing lands on a duplicate product. Curating the duplicates fixes these.
- **1 is a mistake.** Layup's Lemonade Variety Pack (8 × 10mg) was matched to the single
  Lemonade can.
- **1 is a disputed label.** A Grassroots Foreign Kush Mints 14g is titled "(Flower)", but
  the labeller read it as smalls from another store's listing.

**Where the bars could move.** A bigger sample would be needed before acting on these:

- Store-built catalogs at 0.7 instead of 0.9 would trust 15 more listings, all right. That
  takes recall from 72.9% to 86.9%, with 1 wrong at either bar.
- Brand-site catalogs at 0.7 instead of 0.85 would trust 15 more, 2 of them wrong.
  Precision goes from 95.2% to 93.9%, and recall from 62.0% to 72.1%.
