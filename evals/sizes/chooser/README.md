# Size chooser eval

What happens to a listing whose size readings conflict (see [`../README.md`](../README.md)): how often does a chooser pick the right size?

## Cases (2026-10-06)

The 285 listings of the 1,000-listing sample whose readings conflicted.

Two model readers (Sonnet) labelled each one. They saw:
- the name and description;
- the store's size field;
- the price;
- the matched catalog product's sizes, with what each typically sells for;
- a category price guide.

They did not see the code's options. 284 got a size; one, a dry-herb vaporizer, is unknown.

Each case also keeps the blind reader's answer from `../cases.json` (name and description only). The two labels agree on 206 of the 246 cases both answer (84%). They split mostly where the store's size field or the price settles what the text cannot.

`split` follows the parent eval:
- `dev`: the 118 cases looked at while the chooser was built;
- `test`: the other 167, scored once with the chooser frozen.

## The chooser

1. **Code settles what it can** with `size_candidates.assess`.
2. **Price check, weights only.** A size whose price per gram is under a third or over three times the brand's usual (the category's when the brand has too few listings) is dropped. If one size is left, it is the answer. Dose sizes are priced too unevenly for this.
3. **Jev picks among the rest.** Each option says, in words, which readings give it and what a package that size typically sells for. The state carries the price and the description's size sentences.
   - No abstain option: Jev answered "none" whenever it was unsure, including cases where one option was plainly better.
   - Below the confidence bar (0.7), the store's size field stands.

## Results (labels from the full-information readers)

| | All 284 | Test 167 |
| --- | --- | --- |
| Store's size field | 66.7% | 69.3% |
| `sizes.parse` (field, then name) | 57.4% | 57.8% |
| Chooser, price nowhere | 72.4% | 72.3% |
| Chooser, price only in the code check | 75.3% | 74.7% |
| Chooser, price only in Jev's context | 83.7% | 83.7% |
| **Chooser, price in both** | **84.8%** | **83.7%** |
| Jev's answers at p ≥ 0.8 alone, price in both | 190/201 (94.5%) | 113/120 (94.2%) |

What the results show:
- **Price in Jev's context is the lever.** Without it, Jev's confident answers are right 77% of the time. With it, 94%.
- **The code check adds nothing on the test split.** It was tuned on dev. It still answers 25 cases without a Jev call.
- **Run-to-run stability:** two identical runs changed 8 of 285 picks, all at probabilities from 0.4 to 0.57.
- **Cost:** about $0.007 a run.

What is still wrong:
- **Catalog entries that record a piece's dose as the size.** Eaton's "Daily Elevation 5mg" draws Jev to 5mg.
- **A size field that is count × a figure already the total, where the price cannot tell them apart.** Amedicanna's "2pk (1.3g)" listed at 2.6g.
- **Store copy pasted from another pack size.** MyHi's 3-pack carries its 10-pack's 100mg.

## Run

```bash
python evals/sizes/chooser/run_chooser.py                      # asks Jev, then scores
python evals/sizes/chooser/run_chooser.py --split test --price jev
python evals/sizes/chooser/run_chooser.py --show S0216         # one case's question, or how code settled it
```

Needs `OPENROUTER_API_KEY`. `prices.json` is the price snapshot the cases were run with: category medians by size, and brand medians by size and per gram, from listings whose readings settle.
