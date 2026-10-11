#!/usr/bin/env python3
"""
reenrich_csv.py — Run a scrape CSV's rows back through enrichment, in place.

`scrape.py --import-only` runs this on a store's newest CSV before importing it, so a
taxonomy or prompt change reaches listings without a fresh scrape. It is the same
enrich() a scraper calls, so ENRICH_LLM, ENRICH_CACHE, --model, the enrich cache and
its version gates all apply: a row whose cached answer is still current costs nothing.

A CSV holds enrichment's output, not just the scrape, so each row is put back to what
the scraper handed enrich() before it is asked again:
  - category  <- map_category(raw_category), the store's category (the model's hint);
  - variant   <- scraped_variant, the scraper's size string (also the cache key);
                 a CSV written before that column existed keeps its enriched variant,
                 which can miss the cache for rows whose size was normalized;
  - subtype, strain, product_line, attributes, enrich_failed are dropped, so the
    fresh answers replace them rather than being read back as the "stored" value.

Usage
-----
  python scripts/reenrich_csv.py --csv data/scrapes/<slug>_<stamp>.csv [--model haiku]

Writes the CSV (atomically) and its .usage.json sidecar. Exit 0 on success, 3 on an
empty CSV.
"""

import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper_common import map_category, write_csv  # noqa: E402

# Enrichment's outputs: cleared so a re-run answers them afresh.
ENRICHED = ("subtype", "strain", "product_line", "attributes", "enrich_failed")


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def restore_scraped(row: dict) -> dict:
    """Put a CSV row back to the shape the scraper handed enrich(). In place."""
    raw_cat = (row.get("raw_category") or "").strip()
    if raw_cat:
        row["category"] = map_category(raw_cat)
    if row.get("scraped_variant") not in (None, ""):
        row["variant"] = row["scraped_variant"]
    for col in ENRICHED:
        row.pop(col, None)
    return row


def reenrich(path: Path, model: str = "haiku") -> tuple[int, dict]:
    from enrich import enrich, write_usage

    rows = read_rows(path)
    if not rows:
        return 0, {}
    for row in rows:
        restore_scraped(row)
    usage = enrich(rows, model=model)
    tmp = path.with_suffix(".csv.tmp")
    write_csv(rows, str(tmp))
    os.replace(tmp, path)
    write_usage(usage, str(path))
    return len(rows), usage


def main() -> None:
    p = argparse.ArgumentParser(description="Re-enrich a scrape CSV in place")
    p.add_argument("--csv", required=True)
    p.add_argument("--model", default="haiku", help="Enrichment model id (see MODELS in scripts/enrich.py)")
    args = p.parse_args()
    n, _ = reenrich(Path(args.csv), model=args.model)
    if n == 0:
        print(f"  [error] empty CSV: {args.csv}", file=sys.stderr)
        sys.exit(3)
    print(f"  re-enriched {n} rows -> {args.csv}")


if __name__ == "__main__":
    main()
