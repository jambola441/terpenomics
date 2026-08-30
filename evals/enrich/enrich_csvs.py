#!/usr/bin/env python3
"""
enrich_csvs.py — Enrich already-scraped CSVs in place, one store at a time.

The scrapers enrich inline, so re-running them to get enrichment would re-fetch
every menu. This takes the CSVs a `--no-enrich` scrape already produced and runs
only the model pass over them, writing each file back with subtype / strain /
product_line / variant filled in.

Per store it prints the row count, token usage and cost, so a fleet-wide run is
auditable line by line rather than as one lump sum. Enrichment is cached per
dispensary in data/enrich_cache/, so a re-run costs nothing until the next
_ENRICH_VERSION bump.

Usage
-----
  python evals/enrich/enrich_csvs.py --csv 'data/scrapes/*.csv' --model haiku-or
  python evals/enrich/enrich_csvs.py --csv 'data/scrapes/*.csv' --dry-run
"""

import argparse
import csv
import glob
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import enrich as enrich_mod
import enrichers  # noqa: E402

FIELDS = ["subtype", "strain", "product_line", "variant", "category"]


def newest_per_store(patterns: list[str]) -> list[tuple[str, Path]]:
    """One CSV per dispensary — the newest, so repeated scrapes don't double-run."""
    paths: list[str] = []
    for pat in patterns:
        paths.extend(sorted(glob.glob(pat)))
    best: dict[str, Path] = {}
    for p in paths:
        path = Path(p)
        with path.open(newline="", encoding="utf-8") as fh:
            head = next(csv.DictReader(fh), None)
        if not head:
            continue
        slug = head.get("dispensary_slug") or path.stem
        # filenames carry a UTC timestamp, so lexical max == newest
        if slug not in best or str(path) > str(best[slug]):
            best[slug] = path
    return sorted(best.items())


def main() -> None:
    ap = argparse.ArgumentParser(description="Enrich scraped CSVs in place")
    ap.add_argument("--csv", action="append", default=[], help="glob of CSVs (repeatable)")
    ap.add_argument("--model", default="haiku-or", help="model id from MODELS")
    ap.add_argument("--dry-run", action="store_true", help="list what would run, then stop")
    args = ap.parse_args()
    if not args.csv:
        ap.error("give --csv GLOB (repeatable)")

    stores = newest_per_store(args.csv)
    if not stores:
        sys.exit("no CSVs matched")

    total_rows = 0
    for slug, path in stores:
        with path.open(newline="", encoding="utf-8") as fh:
            total_rows += sum(1 for _ in csv.DictReader(fh))
    print(f"{len(stores)} stores, {total_rows:,} listings, model={args.model}")
    if args.dry_run:
        for slug, path in stores:
            print(f"  {slug:40s} {path.name}")
        return

    grand = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    t0 = time.time()
    for i, (slug, path) in enumerate(stores, 1):
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        print(f"\n[{i}/{len(stores)}] {slug} — {len(rows)} rows")
        t = time.time()
        # Keep a copy so a batch that fails mid-run cannot blank a value the file
        # already had. enrich() leaves unanswered rows empty; without this, a
        # partial failure would overwrite a previously good CSV with holes.
        before = [{f: r.get(f) for f in FIELDS} for r in rows]
        try:
            usage = enrich_mod.enrich(rows, model=args.model)
        except Exception as e:  # one bad store must not sink the fleet run
            print(f"  [error] {type(e).__name__}: {e}")
            continue
        # Restore ONLY on rows enrichment actually failed on, which enrich() marks.
        # Restoring every empty field instead silently reverts deliberate nulls: the
        # merch refactor sets strain to None on purpose, and this loop used to put
        # the old colour straight back. The tell was a single row changing variant
        # ('20pk' -> '98mm 20pk', non-empty so kept) while its strain stayed 'Purple'
        # — the deterministic path had run and only the blanking was undone.
        restored = 0
        for row, prev in zip(rows, before):
            if not row.pop("_enrich_failed", False):
                continue
            for f in FIELDS:
                if not (row.get(f) or "").strip() and (prev.get(f) or "").strip():
                    row[f] = prev[f]
                    restored += 1
        if restored:
            print(f"  kept {restored} pre-existing value(s) on rows the model did not answer")

        # Same trap as the restore loop, one level up: categories whose owner answers
        # them without a model have no cultivar, so counting them here makes a
        # merch-heavy store look like a failed pass B. Measure over rows that can
        # actually carry a strain.
        eligible = [r for r in rows
                    if not enrichers.skips_model(enrich_mod._hint_category(r))]
        filled = sum(1 for r in eligible if (r.get("strain") or "").strip())
        if eligible and filled / len(eligible) < 0.5:
            print(f"  [warn] strain filled on only {filled}/{len(eligible)} rows that can "
                  f"carry one — pass B likely failed; re-run to fill from cache")

        for f in FIELDS:
            if f not in fieldnames:
                fieldnames.append(f)
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

        for k in grand:
            grand[k] += usage.get(k, 0)
        print(f"  {time.time()-t:.0f}s  in={usage.get('input_tokens',0):,} "
              f"out={usage.get('output_tokens',0):,} ${usage.get('cost_usd',0):.4f} "
              f"| running total ${grand['cost_usd']:.2f}")

    print(f"\n=== fleet done in {time.time()-t0:.0f}s ===")
    print(f"input={grand['input_tokens']:,}  output={grand['output_tokens']:,}  "
          f"cost=${grand['cost_usd']:.2f}")


if __name__ == "__main__":
    main()
