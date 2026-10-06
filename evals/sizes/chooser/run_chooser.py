"""Measure Jev choosing a listing's size among the readings size_candidates.py finds.

The cases are the 285 listings of evals/sizes whose readings conflicted on 2026-10-06,
labelled by model readers who saw everything a person would: the text, the store's
size field, the price, and the matched catalog product's sizes and prices. See
../README.md. The chooser is the one measured there:

  1. the code settles what it can (size_candidates.assess);
  2. for weights, a size whose price per gram is under a third or over three times the
     brand's usual is dropped, and if one size is left it is the answer;
  3. Jev picks among the rest, each option saying in words which readings give it and
     what a package that size sells for; under the confidence bar the store's size
     field stands.

    python evals/sizes/chooser/run_chooser.py                  # asks Jev (~$0.007), then scores
    python evals/sizes/chooser/run_chooser.py --split test --threshold 0.7
    python evals/sizes/chooser/run_chooser.py --answers answers.json   # re-score saved answers
    python evals/sizes/chooser/run_chooser.py --show S0216     # print one question
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent.parent / "scripts"))

import jev  # noqa: E402
import size_candidates as sc  # noqa: E402
import sizes  # noqa: E402
from size_choice import Item, PriceBook, decide_or_ask, field_size as _field_size  # noqa: E402

CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
PRICES = PriceBook.load(HERE / "prices.json")


def item(case: dict) -> Item:
    return Item(name=case["name"], category=case["category"], variant=case["field"],
                description=case["description"], brand=case["brand"], price_cents=case["price_cents"],
                product_sizes=case["product_sizes"])


def field_size(case: dict) -> float | None:
    return _field_size(item(case))


def parse_size(case: dict) -> float | None:
    s = sizes.parse(case["field"], case["name"], category=case["category"])
    return s.mg if case["unit"] == "mg" else s.grams


def ask(cases: list[dict], price: str = "both") -> dict[str, dict]:
    out, jobs = {}, []
    for c in cases:
        pick, question = decide_or_ask(item(c), PRICES, price)
        if pick:
            out[c["sid"]] = {"value": pick.value, "p": 1.0, "by": pick.by}
        else:
            jobs.append((c, question))
    usage = jev.Usage()
    results = jev.ask_many([(state, qs) for _, (state, qs, _) in jobs], usage=usage)
    for (c, (_, _, labels)), r in zip(jobs, results):
        pick, p, _ = r.choice("size") if r else (None, 0.0, {})
        out[c["sid"]] = {"value": labels.get(pick), "p": p, "by": "jev"}
    print(usage.summary())
    return out


def _label(s) -> float | None:
    m = re.match(r"^\s*(\d+(?:\.\d+)?|\.\d+)\s*(g|mg)\s*$", str(s or ""), re.I)
    return float(m.group(1)) if m else None


def score(cases: list[dict], answers: dict[str, dict], threshold: float) -> None:
    rows = {"store size field": lambda c: field_size(c),
            "sizes.parse (field, then name)": lambda c: parse_size(c),
            f"chooser (Jev below {threshold} -> field)": lambda c: (
                answers[c["sid"]]["value"] if answers[c["sid"]]["value"] is not None
                and answers[c["sid"]]["p"] >= threshold else field_size(c)),
            "chooser, only its confident answers": lambda c: (
                answers[c["sid"]]["value"] if answers[c["sid"]]["p"] >= max(threshold, 0.8) else None)}
    for label_name in ("label", "blind"):
        judged = [c for c in cases if _label(c[label_name]) is not None]
        print(f"\nagainst the {'full-information' if label_name == 'label' else 'blind (name + description)'} labels: {len(judged)} cases")
        for name, pick in rows.items():
            verdicts = Counter()
            for c in judged:
                v = pick(c)
                verdicts["none" if v is None else "right" if sc.same(v, _label(c[label_name]), c["unit"]) else "wrong"] += 1
            answered = verdicts["right"] + verdicts["wrong"]
            print(f"  {name:<40} {verdicts['right']:>4} right {verdicts['wrong']:>4} wrong {verdicts['none']:>4} no answer"
                  f"   {verdicts['right'] / answered:.1%} of answers" if answered else "")
    print("\ndecided by:", dict(Counter(answers[c["sid"]]["by"] for c in cases)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--split", choices=["all", "dev", "test"], default="all")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--answers", help="score these saved answers instead of asking Jev")
    ap.add_argument("--save", help="save the answers here")
    ap.add_argument("--show", help="print the question for one case id")
    ap.add_argument("--price", choices=["both", "code", "jev", "none"], default="both",
                    help="where the price is used (an ablation; the chooser uses both)")
    args = ap.parse_args()
    cases = [c for c in CASES if args.split == "all" or c["split"] == args.split]
    if args.show:
        c = next(x for x in CASES if x["sid"] == args.show)
        pick, question = decide_or_ask(item(c), PRICES, args.price)
        if pick:
            print(f"decided by {pick.by}: {pick.value}")
            return
        state, qs, _ = question
        print(json.dumps(state, indent=1, ensure_ascii=False))
        print(qs["size"].instructions)
        for k, v in qs["size"].criteria.items():
            print(f"  [{k}] {v}")
        return
    answers = json.loads(Path(args.answers).read_text()) if args.answers else ask(cases, args.price)
    if args.save:
        Path(args.save).write_text(json.dumps(answers, indent=1))
    score(cases, answers, args.threshold)


if __name__ == "__main__":
    main()
