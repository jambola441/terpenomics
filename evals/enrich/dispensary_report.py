#!/usr/bin/env python3
"""
dispensary_report.py — Per-dispensary enrichment quality, across every store.

run_eval.py measures accuracy against hand-labeled gold cases, but only four
stores have gold sets. audit.py sweeps full output for suspects, but reports one
pooled result. This sits between them: it runs the audit checks *per store* and
normalizes them, so 30 menus can be ranked and the weak ones found.

What it reports per store
-------------------------
  coverage    what the scrape gave us     — listings, % with a description,
                                            % of rows landing in `other`
  fill        what enrichment produced    — % of enrichable rows with a strain /
                                            subtype / variant
  suspects    what the audit flagged      — findings per 100 listings, by check

IMPORTANT — suspects are not errors. A finding is a row worth looking at, not a
row known to be wrong; there is no label to check it against. Use the rate to
rank stores and target curation, not as an accuracy figure. For the four stores
with gold suites, run_eval.py gives the real number.

Usage
-----
  python evals/enrich/dispensary_report.py --csv 'data/scrapes/*.csv'
  python evals/enrich/dispensary_report.py --csv 'data/scrapes/*.csv' \
      --json report.json --md report.md
"""

import argparse
import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "scripts"))

import audit  # noqa: E402

# Categories where a missing strain is a real gap rather than correct-by-nature.
# Merch has no strain; topicals and tinctures often legitimately have none.
STRAIN_EXPECTED = {"flower", "preroll", "vaporizers", "concentrate", "edible"}

# Rows in these categories should carry a variant (weight or dose).
VARIANT_EXPECTED = {"flower", "preroll", "vaporizers", "concentrate", "edible", "tinctures"}


def pct(num: int, den: int) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def load_rows(patterns: list[str]) -> dict[str, list[dict]]:
    """Load every CSV and bucket rows by dispensary_slug. When a store has been
    scraped more than once, the newest file wins so re-runs don't double-count."""
    paths: list[str] = []
    for pat in patterns:
        paths.extend(sorted(glob.glob(pat)))
    newest: dict[str, tuple[str, list[dict]]] = {}
    for p in paths:
        with open(p, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            continue
        slug = rows[0].get("dispensary_slug") or Path(p).stem
        # filenames carry a UTC timestamp, so lexical max == newest
        if slug not in newest or p > newest[slug][0]:
            newest[slug] = (p, rows)
    return {slug: rows for slug, (_, rows) in sorted(newest.items())}


def store_metrics(slug: str, rows: list[dict]) -> dict:
    n = len(rows)
    cats = Counter((r.get("category") or "").strip().lower() for r in rows)

    def nonempty(r: dict, field: str) -> bool:
        return bool((r.get(field) or "").strip())

    strain_rows = [r for r in rows
                   if (r.get("category") or "").strip().lower() in STRAIN_EXPECTED]
    variant_rows = [r for r in rows
                    if (r.get("category") or "").strip().lower() in VARIANT_EXPECTED]
    sub_rows = [r for r in rows if (r.get("category") or "").strip().lower() != "merch"]

    # Per-store audit: run every check over just this store's rows.
    findings = {name: fn(rows) for name, fn in audit.CHECKS}
    # unmapped_category_bucket returns grouped findings carrying their own count;
    # everything else is one finding per row.
    counts = {}
    for name, fs in findings.items():
        if name == "unmapped_category_bucket":
            counts[name] = sum(f.get("count", 0) for f in fs)
        else:
            counts[name] = len(fs)
    total_suspect = sum(counts.values())

    # A store whose strain column is essentially empty was never enriched (a failed
    # or interrupted run), not a store the model did badly on. Its suspect count is
    # dominated by missing_enrichment and must not be ranked against real output.
    strain_fill = pct(sum(1 for r in strain_rows if nonempty(r, "strain")), len(strain_rows))
    enriched = strain_fill >= 50.0

    return {
        "slug": slug,
        "listings": n,
        "enriched": enriched,
        "coverage": {
            "with_description": pct(sum(1 for r in rows if nonempty(r, "description")), n),
            "other_share": pct(cats.get("other", 0), n),
            "categories": dict(cats.most_common()),
        },
        "fill": {
            "strain": pct(sum(1 for r in strain_rows if nonempty(r, "strain")), len(strain_rows)),
            "strain_n": len(strain_rows),
            "subtype": pct(sum(1 for r in sub_rows if nonempty(r, "subtype")), len(sub_rows)),
            "subtype_n": len(sub_rows),
            "variant": pct(sum(1 for r in variant_rows if nonempty(r, "variant")), len(variant_rows)),
            "variant_n": len(variant_rows),
            "product_line": pct(sum(1 for r in rows if nonempty(r, "product_line")), n),
        },
        "suspects": {
            "total": total_suspect,
            "per_100": round(100.0 * total_suspect / n, 1) if n else 0.0,
            "by_check": counts,
        },
        "findings": findings,
    }


def _table(rows: list[dict]) -> list[str]:
    lines = ["| store | listings | desc % | other % | strain fill | variant fill | suspects/100 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in sorted(rows, key=lambda x: -x["suspects"]["per_100"]):
        c, f = r["coverage"], r["fill"]
        lines.append(
            f"| `{r['slug']}` | {r['listings']:,} | {c['with_description']} | "
            f"{c['other_share']} | {f['strain']} | {f['variant']} | "
            f"**{r['suspects']['per_100']}** |"
        )
    return lines


def to_markdown(reports: list[dict]) -> str:
    total = sum(r["listings"] for r in reports)
    done = [r for r in reports if r["enriched"]]
    pending = [r for r in reports if not r["enriched"]]
    lines = [
        f"# Per-dispensary enrichment report — {len(reports)} stores, {total:,} listings\n",
        "`suspects/100` counts audit findings per 100 listings. A finding is a row "
        "**worth reviewing**, not a row known to be wrong — there is no label behind "
        "it. Rank stores with it; do not read it as an error rate.\n",
        f"## Enriched — {len(done)} stores, {sum(r['listings'] for r in done):,} listings\n",
    ]
    lines += _table(done)
    if pending:
        lines += [
            f"\n## Not enriched — {len(pending)} stores, "
            f"{sum(r['listings'] for r in pending):,} listings\n",
            "Pass B never ran on these (the run was interrupted), so `strain` is empty "
            "and their suspect counts are almost entirely `missing_enrichment`. **These "
            "are not quality scores** — the stores are simply unprocessed. Re-run "
            "`enrich_csvs.py`; rows already answered are cached, so only the gaps cost.\n",
        ]
        lines += _table(pending)

    lines.append("\n## Suspects by check — enriched stores only\n")
    all_checks = [name for name, _ in audit.CHECKS]
    lines.append("| store | " + " | ".join(c.replace("_", " ") for c in all_checks) + " |")
    lines.append("|---|" + "---:|" * len(all_checks))
    for r in sorted(done, key=lambda x: -x["suspects"]["per_100"]):
        cells = [str(r["suspects"]["by_check"].get(c, 0)) for c in all_checks]
        lines.append(f"| `{r['slug']}` | " + " | ".join(cells) + " |")

    agg = defaultdict(int)
    for r in done:
        for k, v in r["suspects"]["by_check"].items():
            agg[k] += v
    lines.append("\n## Fleet totals — enriched stores only\n")
    lines.append("| check | findings |")
    lines.append("|---|---:|")
    for k, v in sorted(agg.items(), key=lambda x: -x[1]):
        lines.append(f"| {k.replace('_', ' ')} | {v:,} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Per-dispensary enrichment quality report")
    ap.add_argument("--csv", action="append", default=[],
                    help="glob of scrape CSVs (repeatable)")
    ap.add_argument("--json", help="write full per-store findings here")
    ap.add_argument("--md", help="write the markdown report here")
    args = ap.parse_args()
    if not args.csv:
        ap.error("give --csv GLOB (repeatable)")

    by_slug = load_rows(args.csv)
    if not by_slug:
        sys.exit("no rows matched")
    reports = [store_metrics(slug, rows) for slug, rows in by_slug.items()]

    md = to_markdown(reports)
    print(md)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(reports, indent=1, ensure_ascii=False),
                                   encoding="utf-8")
        print(f"full findings -> {args.json}")


if __name__ == "__main__":
    main()
