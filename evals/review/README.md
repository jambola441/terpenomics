# Review agent eval

Measures the review agent (`scripts/review_agent.py`, tools in `scripts/review_tools.py`)
on fixed queues of the listings it would get: the ones a Jev-only first pass was unsure
of and no trusted catalog match settled. For each field it compares the agent's answer
with the label, beside the first pass it would replace and, for Hold Up Roll Up, today's
production path (Haiku).

```bash
DB_VIA_HTTP=1 python evals/review/run_review.py --models claude-sonnet-5-5,claude-opus-5-5
DB_VIA_HTTP=1 python evals/review/run_review.py --models claude-sonnet-5-5 --limit 3   # smoke run
```

It needs `ANTHROPIC_API_KEY` and the database: the agent reads live catalogs, other
stores' listings and prices. It writes `results/<model>.json` (answers, scores, usage and
each conversation's trace) and `results/summary.md`.

## The queues (`cases/`)

**The flag rule.** A listing goes to review when Jev's probability is below 0.7 on
category, subtype, strain or size (the product line aside: it is unsure of lines far
more often), or the size was left to the store's field. A trusted catalog match at
import takes it back out.

- `gold_queue.json`: 35 labelled gold cases.
  - 32 the rule flags on a Jev-only run of 2026-10-07; the first pass already has most
    of them right, so they mostly test that the agent doesn't break them.
  - 3 Jev got wrong while sure ("missed"), outside the queue: a capability check.

  Labels are read by id from `evals/enrich/cases`, so they have one home.
- `hold_up_roll_up_queue.json`: the store's raw scrape of 2026-10-06, run through
  Jev-only. It holds the 37 rows the rule sends to review: 40 flagged without a trusted
  match, less 3 that are already gold cases. Labels were judged on 2026-10-07 against
  `evals/enrich/CONVENTIONS.md`.

**How labels are scored.**

- A field a case leaves out is unsettled and not scored. Examples: whether REMZzz's MAX
  belongs in the strain or the line, and whether "Dark Chocolate" is a chocolate bar's
  strain.
- `accept` lists the spellings that count.
- `note` says why a label is what it is. Read the notes when spot-checking.
- A pre-roll's subtype isn't scored, because the importer drops it.
- "Applied" is what the pipeline would write: the agent's answer, or the first pass's
  where the agent said unsure.

**Three gold cases left out** because their labels predate the conventions:

- `var-tincture-ml` wants a volume ("30ml") where sizes are mg of THC.
- `cat-grinder-merch` and `cat-papers-merch` want subtype "merch" where the taxonomy has
  "grinder" and "paper".

## What the agent does

One conversation per store and brand, at most five listings. It reads the conventions
and taxonomy in its system prompt, plus each listing with the first pass's answers and
how sure Jev was. Its tools:

- the brand's catalog;
- other stores' listings of the brand (never the listing's own store);
- the size readings with typical prices;
- the listing's own page;
- web search and fetch.

It records one answer per listing with `submit_labels` (sure, likely or unsure), and can
propose catalog fixes for a person to approve. Nothing is written to the database.
