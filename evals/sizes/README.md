# Size readings eval

Checks [`scripts/size_candidates.py`](../../scripts/size_candidates.py), the code that lists every size a listing's text could mean. Two questions:

- Does the code produce the size a careful reader would pick?
- Does it settle on its own only when that reader agrees?

The design it serves: the code proposes readings, and when they disagree a chooser model picks among them. That only works if the right size is always among the options.

## How the cases were made (2026-10-06)

1,000 active listings from production, in the categories that have a size. Each distinct brand + name + size field was eligible once. The sample is stratified by how `sizes.parse` reads the store's size field against the name:

| Stratum | Cases | Meaning |
| --- | --- | --- |
| `conflict` | 185 | Field and name state different sizes. This is all of them. |
| `pack_vs_measure` | 250 | One states a weight or dose, the other only a pack count: "1g" beside "- 2pk". |
| `agree` | 250 | Both state the same size. |
| `one` | 215 | Only one of them states a size. |
| `neither` | 100 | Neither states a size. |

Five model readers (Sonnet) read 200 listings each. They saw only the brand, the category, the name and the description, cut at 1,500 characters. They did not see this code, the store's size field or the catalog.

Their rules:
- **Size:** the package total, in grams for weight categories and in THC milligrams for dose categories.
- **Readings:** every size the text could reasonably mean.
- **Best:** the one they believe.
- **Sure:** how confident they are.

In `cases.json`, each case also carries the store's size field and the variants its matched catalog product had that day. That lets the eval run offline.

The readers are a model, not ground truth. Their low-confidence calls are judgments:
- Boutiq's "(5 x .05g)" is read as a typo for .5g.
- Drops' "20pc 20mg" is read as a 20mg micro-dose pack.

Treat `best` as a silver label.

## Splits

- `tuning`: the 450 cases looked at while the generator was being built.
- `holdout`: the other 550, scored once before any change was made from them.
  - At that first scoring, the reader's size was among the options in 334/335.
  - The code settled on a different size in 2/335.

The gaps found in both splits were then fixed: hyphenated units, "1oz", count nouns, and the dose floor for 20:1 gummies. So the numbers below are on data the generator has now seen.

Two rules added later, from the chooser cases in `chooser/`:
- a size field that adds THC to the other cannabinoids ("150MG THC : 450MG CBD" as 600mg) is not the size;
- an edible figure above New York's 100mg cap counts only when nothing under it does.

## Results

| | All | Holdout |
| --- | --- | --- |
| Reader's size among the code's options | 597/598 (99.8%) | 335/335 |
| ... among the name and description readings | 591/598 (98.8%) | 332/335 |
| Code settles on a size the reader does not | 2/598 (0.3%) | 2/335 |
| Reader sees 2+ readings, code flags a conflict | 76/100 | 47/63 |
| Reader sees 1 reading, code flags a conflict | 141/498 | 83/272 |

Notes on the misses:
- **The one size outside the options:** "F Strength 100" mints, which give no unit.
- **The text misses:** store typos where the size field has the right figure ("(5 x .05g)", a "5g" 510 cart).
- **The two false agreements:**
  - a CBG capsule bottle, read as 30 x 50mg of CBG;
  - Ruby Farms' "100MG CBN 300MG CBD 200MG" gummies. The reader's low-confidence 200mg is over the edible cap; the size field and the catalog say 100mg.

"Reader sees 1 reading, code flags a conflict" overstates over-flagging. Most of those conflicts are the store's size field against the text, and the readers never saw the field.

## Run

```bash
python evals/sizes/run_eval.py                          # all cases
python evals/sizes/run_eval.py --split holdout
python evals/sizes/run_eval.py --show misses,false_agreement --n 20
```

`scripts/test_size_candidates.py` gates CI on it:
- the reader's size must be among the options in at least 99.5% of cases;
- false agreement must stay at or below 0.5%.
