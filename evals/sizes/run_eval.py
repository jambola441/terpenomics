"""Score scripts/size_candidates.py against blind model readings of 1,000 listings.

Each case is a real listing (name, store size field, description, and the sizes its
matched catalog product came in on 2026-10-06) with what a model reader made of it
from the name and description alone: every size the text could mean, and the one it
believes. The readers never saw the code's output, the store's size field, or the
catalog. See README.md.

    python evals/sizes/run_eval.py                       # all cases
    python evals/sizes/run_eval.py --split holdout       # the 550 the generator was not tuned on first
    python evals/sizes/run_eval.py --show misses,false_agreement --n 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))

import size_candidates as sc  # noqa: E402

_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?|\.\d+)\s*(g|mg)\s*$", re.I)
TEXT_SOURCES = {"name", "description", "name+description", "description+name"}


def load_cases(split: str = "all") -> list[dict]:
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    return [c for c in cases if split == "all" or c["split"] == split]


def _value(size: str | None) -> float | None:
    m = _SIZE.match(size or "")
    return float(m.group(1)) if m else None


def score_case(case: dict) -> dict:
    listing = {"variant": case["variant"], "scraped_name": case["name"],
               "description": case["description"], "scraped_category": case["category"]}
    entries = [{"variant": v, "category": case["category"]} for v in case["catalog"]]
    a = sc.assess(listing, entries)
    unit = sc.unit_of(case["category"])
    text = sc.distinct_values([c for c in a.candidates if c.source in TEXT_SOURCES])
    best = _value(case["best"])
    model = sc.distinct_values([sc.Candidate(v, unit, "model", "") for r in case["readings"]
                                if (v := _value(r["size"])) is not None])

    def among(v, pool):
        return any(sc.same(v, p, unit) for p in pool)

    return {
        "case": case, "assessment": a, "text": text, "best": best, "model": model,
        "best_in_options": best is not None and among(best, a.options()),
        "best_in_text": best is not None and among(best, text),
        "found": [among(v, text) for v in model],
        "false_agreement": best is not None and len(a.values) == 1 and not sc.same(best, a.values[0], unit),
        "missed_ambiguity": len(model) >= 2 and a.status != "conflict",
        "extra": [v for v in text if not among(v, model)],
    }


def score(cases: list[dict]) -> dict:
    rows = [score_case(c) for c in cases]
    judged = [r for r in rows if r["best"] is not None]
    found = [f for r in rows for f in r["found"]]
    one = [r for r in judged if len(r["model"]) == 1]
    return {
        "rows": rows, "cases": len(rows), "judged": len(judged),
        "best_in_options": sum(r["best_in_options"] for r in judged),
        "best_in_text": sum(r["best_in_text"] for r in judged),
        "found": sum(found), "readings": len(found),
        "false_agreement": sum(r["false_agreement"] for r in judged),
        "ambiguous": sum(len(r["model"]) >= 2 for r in rows),
        "ambiguous_flagged": sum(len(r["model"]) >= 2 and r["assessment"].status == "conflict" for r in rows),
        "one_reading": len(one),
        "one_reading_flagged": sum(r["assessment"].status == "conflict" for r in one),
        "status": Counter(r["assessment"].status for r in rows),
    }


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d:.1%})" if d else "0/0"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--split", choices=["all", "tuning", "holdout"], default="all")
    ap.add_argument("--show", default="", help="misses, false_agreement, missed_ambiguity, extra")
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()

    s = score(load_cases(args.split))
    print(f"{s['cases']} listings, {s['judged']} where the reader named a size ({args.split})")
    print("  reader's size among the code's options:      ", _pct(s["best_in_options"], s["judged"]))
    print("  ... among the name and description readings: ", _pct(s["best_in_text"], s["judged"]))
    print("  reader's readings the code also has:         ", _pct(s["found"], s["readings"]))
    print("  code settles on a size the reader does not:  ", _pct(s["false_agreement"], s["judged"]))
    print("  reader sees 2+ readings, code flags conflict:", _pct(s["ambiguous_flagged"], s["ambiguous"]))
    print("  reader sees 1 reading, code flags conflict:  ", _pct(s["one_reading_flagged"], s["one_reading"]))
    print("  status:", dict(s["status"]))

    tests = {"misses": lambda r: r["best"] is not None and not r["best_in_options"],
             "false_agreement": lambda r: r["false_agreement"],
             "missed_ambiguity": lambda r: r["missed_ambiguity"],
             "extra": lambda r: bool(r["extra"])}
    for what in filter(None, args.show.split(",")):
        picked = [r for r in s["rows"] if tests[what](r)]
        print(f"\n## {what}: {len(picked)}")
        for r in picked[:args.n]:
            c, a = r["case"], r["assessment"]
            print(f"\n{c['sid']} [{c['category']}] {c['name']!r}  field={c['variant']!r}")
            print(f"   reader: {[x['size'] for x in c['readings']]} best={c['best']} ({c['sure']})")
            print(f"   code:   {a.status}, values {a.values}, catalog {a.catalog}")
            for cand in a.candidates:
                flag = "" if cand.likely else "  (unlikely)"
                print(f"           {cand.label():>8}  {cand.source:<18} {cand.reading}{flag}")


if __name__ == "__main__":
    main()
