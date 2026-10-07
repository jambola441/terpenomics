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

## Status

The set is drawn but not labelled yet; labelling waits on `ANTHROPIC_API_KEY`. The
whole path was checked end to end with a stand-in labeller on a copy of the set:
labelling, the live matcher over all 300 listings (Jev about $0.006), and the scoring.
