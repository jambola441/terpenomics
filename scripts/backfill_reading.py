#!/usr/bin/env python3
"""
backfill_reading.py — Give listings imported before listings.reading existed their own
reading, so the matcher's attribute join (catalog_match.CatalogIndex.join) can decide them.

The reading is enrichment's category, subtype, strain, product line and size for the
listing, with the rule files applied (canonical.py), as import_listings.record_reading
saves it for a new import. The stored columns cannot give it: the catalog overlay
replaced them with the matched entry's. So each listing is enriched again from its name,
description and size field, on the Jev-only path (ENRICH_LLM=0, about $0.0001 a listing),
uncached. The store's own category is not kept either; the stored (overlaid) one goes in
as the hint, and enrichment still decides.

Writes only `reading`, only where it is empty (or every active listing with --all).

Usage
-----
  DB_VIA_HTTP=1 python scripts/backfill_reading.py --limit 200      # read, print a sample
  DB_VIA_HTTP=1 python scripts/backfill_reading.py --write          # every listing without one
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("ENRICH_LLM", "0")

import db_http  # noqa: E402
import enrich  # noqa: E402
import import_listings  # noqa: E402

COLS = "id,scraped_name,scraped_brand,scraped_category,subtype,variant,description,reading"


def pending(everything: bool) -> list[dict]:
    query = f"select={COLS}&is_active=is.true&order=id"
    rows = db_http.select_all("listings", query)
    return rows if everything else [r for r in rows if not r.get("reading")]


def read(listings: list[dict], batch: int = 500) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(listings), batch):
        rows = [{"id": l["id"], "name": l.get("scraped_name") or "", "brand": l.get("scraped_brand") or "",
                 "category": l.get("scraped_category") or "", "subtype": "", "strain": "",
                 "description": l.get("description") or "", "variant": l.get("variant") or "",
                 "dispensary_slug": "backfill-reading"} for l in listings[i:i + batch]]
        enrich.enrich(rows)
        for r in rows:
            if r.get("enrich_failed"):
                continue
            rec = {"scraped_category": r.get("category"), "subtype": r.get("subtype"),
                   "strain": r.get("strain"), "product_line": r.get("product_line"),
                   "variant": r.get("variant")}
            out[r["id"]] = {k: rec.get(col) or None for k, col in import_listings.READING}
        print(f"  read {min(i + batch, len(listings))} of {len(listings)}", flush=True)
    return out


def write(readings: dict[str, dict], workers: int = 8) -> int:
    def one(item):
        lid, reading = item
        return len(db_http.update("listings", f"id=eq.{lid}", {"reading": reading}))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return sum(pool.map(one, readings.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="re-read listings that have a reading too")
    ap.add_argument("--limit", type=int, default=0, help="only this many (a sample)")
    ap.add_argument("--write", action="store_true", help="write the readings (else print a sample)")
    args = ap.parse_args(argv)
    listings = pending(args.all)
    if args.limit:
        listings = listings[:args.limit]
    print(f"{len(listings)} listing(s) to read")
    if not listings:
        return 0
    readings = read(listings)
    print(f"{len(readings)} read ({len(listings) - len(readings)} failed, left without one)")
    if not args.write:
        for l in listings[:15]:
            print(f"  {(l.get('scraped_name') or '')[:60]:60} -> {readings.get(l['id'])}")
        print("(dry run; --write writes them)")
        return 0
    print(f"wrote {write(readings)} reading(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
