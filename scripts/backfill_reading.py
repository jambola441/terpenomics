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

--catalog reads each listing of a brand with a catalog against that catalog instead
(catalog_reading: category, subtype, line, strain, size in the catalog's own values),
which is how the importer reads them; a listing Jev could not read keeps its reading.

Usage
-----
  DB_VIA_HTTP=1 python scripts/backfill_reading.py --limit 200      # read, print a sample
  DB_VIA_HTTP=1 python scripts/backfill_reading.py --write          # every listing without one
  DB_VIA_HTTP=1 python scripts/backfill_reading.py --catalog --all --write   # catalog readings
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("ENRICH_LLM", "0")

import db_http  # noqa: E402
import enrich  # noqa: E402
import import_listings  # noqa: E402

BATCH = 500
COLS = "id,scraped_name,scraped_brand,scraped_category,subtype,variant,description,reading"


def pending(everything: bool) -> list[dict]:
    query = f"select={COLS}&is_active=is.true&order=id"
    rows = db_http.select_all("listings", query)
    return rows if everything else [r for r in rows if not r.get("reading")]


def read(listings: list[dict]) -> dict[str, dict]:
    rows = [{"id": l["id"], "name": l.get("scraped_name") or "", "brand": l.get("scraped_brand") or "",
             "category": l.get("scraped_category") or "", "subtype": "", "strain": "",
             "description": l.get("description") or "", "variant": l.get("variant") or "",
             "dispensary_slug": "backfill-reading"} for l in listings]
    enrich.enrich(rows)
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("enrich_failed"):
            continue
        rec = {"scraped_category": r.get("category"), "subtype": r.get("subtype"),
               "strain": r.get("strain"), "product_line": r.get("product_line"),
               "variant": r.get("variant")}
        out[r["id"]] = {k: rec.get(col) or None for k, col in import_listings.READING}
    return out


def read_by_catalog(listings: list[dict]) -> dict[str, dict]:
    """catalog_reading's readings for the listings of brands with a catalog."""
    import catalog_reading
    import catalog_store
    import jev
    catalogs = catalog_store.load_all("db")
    by_brand: dict[str, list[dict]] = {}
    for l in listings:
        key = catalog_store.brand_key(l.get("scraped_brand"))
        if key in catalogs:
            by_brand.setdefault(key, []).append(
                {"id": l["id"], "name": l.get("scraped_name") or "", "variant": l.get("variant"),
                 "description": l.get("description"), "category": l.get("scraped_category"),
                 "store_category": (l.get("reading") or {}).get("store_category"),
                 "subtype": l.get("subtype")})
    usage = jev.Usage()
    out: dict[str, dict] = {}
    for key, rows in by_brand.items():
        out.update(catalog_reading.read(catalogs[key], rows, usage=usage))
        print(f"  {catalogs[key]['brand_name']}: {len(rows)} listing(s); {len(out)} read so far", flush=True)
    print(usage.summary())
    return out


def write(readings: dict[str, dict], workers: int = 8, tries: int = 4) -> int:
    """One PATCH a listing. A dropped connection is retried with backoff (2026-10-08: one
    reset 6,000 rows into a run lost the rest of it); a listing still failing after
    that is left without a reading for the next run."""
    def one(item):
        lid, reading = item
        for attempt in range(tries):
            try:
                return len(db_http.update("listings", f"id=eq.{lid}", {"reading": reading}))
            except db_http.DbHttpError as exc:
                if attempt == tries - 1:
                    print(f"  [WARN] {lid}: {exc}", file=sys.stderr)
                    return 0
                time.sleep(2 ** attempt)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return sum(pool.map(one, readings.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="re-read listings that have a reading too")
    ap.add_argument("--limit", type=int, default=0, help="only this many (a sample)")
    ap.add_argument("--write", action="store_true", help="write the readings (else print a sample)")
    ap.add_argument("--catalog", action="store_true",
                    help="read brands with a catalog against it (catalog_reading)")
    args = ap.parse_args(argv)
    listings = pending(args.all)
    if args.limit:
        listings = listings[:args.limit]
    print(f"{len(listings)} listing(s) to read")
    if not listings:
        return 0
    if args.catalog:
        readings = read_by_catalog(listings)
        if not args.write:
            for l in listings[:15]:
                print(f"  {(l.get('scraped_name') or '')[:60]:60} -> {readings.get(l['id'])}")
            print("(dry run; --write writes them)")
            return 0
        wrote = write(readings)
        print(f"wrote {wrote} catalog reading(s) of {len(listings)} listing(s)")
        return 0
    if not args.write:
        readings = read(listings[:args.limit or 500])
        for l in listings[:15]:
            print(f"  {(l.get('scraped_name') or '')[:60]:60} -> {readings.get(l['id'])}")
        print("(dry run; --write writes them)")
        return 0
    # Read and write a batch at a time, so a failure loses one batch at most.
    read_n = wrote = 0
    for i in range(0, len(listings), BATCH):
        chunk = listings[i:i + BATCH]
        readings = read(chunk)
        for wait in (60, 300, 900):
            # A batch the model mostly failed is an outage or a rate limit (2026-10-08:
            # once Jev's breaker opened, every later batch failed at once): wait, retry.
            if len(readings) >= len(chunk) // 2:
                break
            print(f"  only {len(readings)} of {len(chunk)} read; waiting {wait}s and retrying", flush=True)
            time.sleep(wait)
            readings = read(chunk)
        read_n += len(readings)
        wrote += write(readings)
        print(f"  {min(i + BATCH, len(listings))} of {len(listings)}: {read_n} read, {wrote} written", flush=True)
    print(f"wrote {wrote} reading(s); {len(listings) - wrote} left without one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
