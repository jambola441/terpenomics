#!/usr/bin/env python3
"""
compare_runs.py — Summarise repeated run_eval.py runs of the same models.

One run of the suite moves a few cases either way (README: "Noise floor"), so a
comparison needs several. run_eval.py overwrites results/<model>.json each time, so copy
every run aside, one directory per run, then point this at them:

    for i in 1 2 3; do
        python evals/enrich/run_eval.py --models haiku-or,luna
        mkdir -p /tmp/runs/run_$i && cp evals/enrich/results/{haiku-or,luna}.json /tmp/runs/run_$i/
    done
    python evals/enrich/compare_runs.py /tmp/runs/run_* --models haiku-or,luna

Prints, per model: cases passed per suite as mean (min-max) over the runs; cost, wall clock
and tokens per run; failed rows; and stability — how many listings came back with a
different answer in any field between runs. That last one is the number the README
calls binding: `products` is a view keyed on these strings.
"""

import argparse
import itertools
import json
import statistics
import sys
from pathlib import Path

FIELDS = ["category", "subtype", "strain", "product_line", "variant"]


def norm(v) -> str:
    return (v if v is not None else "").strip().lower()


def passed(item: dict) -> bool:
    """An item case's `passed`; a cluster case's converged-and-canonical match."""
    return item["passed"] if "passed" in item else item["canonical_match"]


def answers(result: dict) -> dict[str, dict]:
    """Listing key -> the five enriched fields, across every suite (cluster members too)."""
    out = {}
    for suite in result["scores"].values():
        for item in suite:
            if "members" in item:
                for i, member in enumerate(item["members"]):
                    out[f"{item['id']}#{i}"] = member
            else:
                out[item["id"]] = item["got"]
    return out


def spread(values: list[float], fmt: str = "{:.1f}") -> str:
    return f"{fmt.format(statistics.mean(values))} ({fmt.format(min(values))}–{fmt.format(max(values))})"


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarise repeated run_eval.py runs")
    ap.add_argument("runs", nargs="+", help="one directory per run, each holding <model>.json")
    ap.add_argument("--models", required=True, help="comma-separated model ids")
    args = ap.parse_args()

    for model in (m.strip() for m in args.models.split(",") if m.strip()):
        runs = [json.loads((Path(d) / f"{model}.json").read_text()) for d in args.runs]
        suites = list(runs[0]["scores"])
        print(f"\n## {model} — {len(runs)} runs\n")

        print("| suite | cases | passed, mean (min–max) |\n| --- | ---: | ---: |")
        for s in suites:
            print(f"| {s.removesuffix('.json')} | {len(runs[0]['scores'][s])} | "
                  f"{spread([sum(map(passed, r['scores'][s])) for r in runs])} |")
        totals = [sum(sum(map(passed, r["scores"][s])) for s in suites) for r in runs]
        cases = sum(len(runs[0]["scores"][s]) for s in suites)
        print(f"| **all** | {cases} | **{spread(totals)}** |")

        print("\n| run | $ | of which Jev $ | s | prompt tok | out tok | of which reasoning | failed rows |"
              "\n| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for i, r in enumerate(runs, 1):
            u = r["usage"]
            prompt = sum(u.get(k, 0) for k in ("input_tokens", "cache_write_tokens", "cache_read_tokens"))
            print(f"| {i} | {u.get('cost_usd', 0):.4f} | {u.get('jev_cost_usd', 0):.4f} | {r['secs']:.0f} | "
                  f"{prompt:,} | {u.get('output_tokens', 0):,} | {u.get('reasoning_tokens', 0):,} | "
                  f"{u.get('failed_rows', 0)} |")

        rows = [answers(r) for r in runs]
        keys = sorted(rows[0])

        def differs(a: dict, b: dict, fields=FIELDS) -> bool:
            return any(norm(a.get(f)) != norm(b.get(f)) for f in fields)

        across = sum(1 for k in keys if any(differs(a[k], b[k]) for a, b in itertools.combinations(rows, 2)))
        by_field = {f: sum(1 for k in keys
                           if any(differs(a[k], b[k], [f]) for a, b in itertools.combinations(rows, 2)))
                    for f in FIELDS}
        pairs = [sum(1 for k in keys if differs(a[k], b[k])) for a, b in itertools.combinations(rows, 2)]
        print(f"\nlistings whose answer changed across the {len(runs)} runs, any field: "
              f"**{across}** of {len(keys)}  (" + ", ".join(f"{f} {n}" for f, n in by_field.items()) + ")")
        if pairs:
            print(f"listings that change between two runs, mean of {len(pairs)} pairs: "
                  f"{statistics.mean(pairs):.1f}  {pairs}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("--help")
    main()
