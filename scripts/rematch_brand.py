#!/usr/bin/env python3
"""
rematch_brand.py — Re-read and re-match every active listing of one brand against its
current catalog, and write what an import would: the reading, the match columns and,
for a trusted match, the entry's identity and size (import_listings.overlay_entry).

An import only touches the listings in the CSVs it imports. After a catalog change
(a storefront push, a curation plan), listings no recent scrape carried keep their old
reading and match until their store is scraped again: 21 of MFNY's 563 on 2026-10-12,
still on pre-push readings. This brings them in line now.

Reading as catalog_fix --measure does (catalog_fix.read_against: catalog_reading with
the working copy's reading_examples.json; a listing the read leaves out keeps its
stored reading), then catalog_match.resolve without Jev, as the import's join decides.
A manual match keeps its entry ('manual' is a reviewer's); only its reading is renewed.
Over Supabase's REST API (DB_VIA_HTTP=1).

Usage
-----
  DB_VIA_HTTP=1 python scripts/rematch_brand.py --brand MFNY            # dry run: what would change
  DB_VIA_HTTP=1 python scripts/rematch_brand.py --brand MFNY --write    # write it
  DB_VIA_HTTP=1 python scripts/rematch_brand.py --brand MFNY --stored-readings [--write]
      # matching only, on the stored readings: no Jev calls (a matching-rule change)
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_match as cm  # noqa: E402
import import_listings  # noqa: E402

COLS = ("id,scraped_name,scraped_category,subtype,strain,product_line,variant,size,"
        "catalog_entry_id,catalog_match_confidence,catalog_match_method,reading")
# The columns an overlay writes, and the listing's columns they are read from.
OVERLAID = ("scraped_category", "subtype", "strain", "product_line", "size")


def patches(rows: list[dict], catalog: dict, decisions: list,
            keep_jev: bool = False) -> dict[str, dict]:
    """{listing id: the columns to write} for the listings whose stored values differ
    from what this run decides. `rows` are the listings as stored (COLS), `decisions`
    catalog_match.resolve's over the re-read listings (each listing carrying its new
    reading).

    `keep_jev` (--stored-readings): a listing the join leaves, matched by Jev before,
    keeps Jev's pick, re-gated at today's bar (catalog_match.gate on its stored
    confidence): this run asks Jev nothing, so it has no answer of its own there."""
    by_id = {str(r["id"]): r for r in rows}
    entries = {e.get("id"): e for e in catalog.get("entries") or []}
    out: dict[str, dict] = {}
    for d in decisions:
        lid = str(d.listing["id"])
        row = by_id.get(lid)
        if row is None or d.method == "error":
            continue
        want: dict = {"reading": d.listing.get("reading")}
        if keep_jev and d.entry is None and row.get("catalog_match_method") in ("jev", "jev_review") \
                and row.get("catalog_entry_id") in entries:
            conf = float(row.get("catalog_match_confidence") or 0.0)
            method = cm.gate("pick", conf, cm.auto_threshold(catalog))
            if method in ("jev", "jev_review"):
                d = SimpleNamespace(**{**vars(d), "entry": entries[row["catalog_entry_id"]],
                                       "confidence": conf, "method": method})
        if row.get("catalog_match_method") != "manual":
            entry = d.entry or {}
            want.update(catalog_entry_id=entry.get("id"),
                        catalog_match_confidence=round(d.confidence, 4) if d.entry else None,
                        catalog_match_method=d.method)
            if d.entry and d.method in cm.OVERLAY_METHODS:
                rec = {k: row.get(k) for k in ("scraped_name", "variant", *OVERLAID)}
                import_listings.overlay_entry(rec, catalog, d.entry)
                want.update({k: rec.get(k) for k in OVERLAID})
            else:
                want["size"] = row.get("variant")       # an untrusted listing shows the store's
        diff = {k: v for k, v in want.items() if not _same(row.get(k), v)}
        if diff:
            out[lid] = diff
    return out


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(float(a) - float(b)) < 1e-3
    return (a or None) == (b or None) if not isinstance(a, dict) else a == b


def write(changes: dict[str, dict], workers: int = 8) -> int:
    import db_http

    def one(item) -> int:
        lid, cols = item
        for attempt in range(4):
            try:
                return len(db_http.update("listings", f"id=eq.{lid}", cols))
            except db_http.DbHttpError as exc:
                if attempt == 3:
                    print(f"  [WARN] {lid}: {exc}", file=sys.stderr)
                    return 0
                time.sleep(2 ** attempt)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return sum(pool.map(one, changes.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True, help="the brand as written in listings")
    ap.add_argument("--write", action="store_true", help="write the changes (else print them)")
    ap.add_argument("--stored-readings", action="store_true",
                    help="match only: keep each listing's stored reading (no Jev calls) and "
                         "keep stored Jev picks re-gated at today's bar")
    args = ap.parse_args(argv)

    import catalog_fix
    import catalog_store
    import db_http
    import jev
    catalog = catalog_store.for_brand(catalog_store.load_all("db"), args.brand)
    if not catalog:
        sys.exit(f"No catalog for {args.brand!r}")
    if not args.stored_readings and not jev.available():
        sys.exit("No OPENROUTER_API_KEY: the reading needs Jev")
    listings = catalog_fix.brand_listings(args.brand)
    rows = db_http.select_all("listings", f"select={COLS}&is_active=is.true"
                                          f"&scraped_brand=ilike.{urllib.parse.quote(args.brand)}")
    read = catalog_fix.read_against(catalog, listings, use_jev=not args.stored_readings)
    decisions = cm.resolve(catalog, read, use_jev=False)
    changes = patches(rows, catalog, decisions, keep_jev=args.stored_readings)
    trusted = Counter(d.method in cm.OVERLAY_METHODS for d in decisions)
    print(f"{args.brand}: {len(decisions)} active listings, {trusted[True]} trusted after re-reading; "
          f"{len(changes)} to update")
    names = {str(r["id"]): r.get("scraped_name") or "" for r in rows}
    moved = {lid: {k: v for k, v in cols.items() if k != "reading"} for lid, cols in changes.items()}
    moved = {lid: cols for lid, cols in moved.items() if cols}
    print(f"  {len(moved)} with a new match, identity or size (the rest: the reading only)")
    for lid, cols in list(moved.items())[:40]:
        print(f"  {names[lid][:60]:60} {cols}")
    if not args.write:
        print("(dry run; --write writes them)")
        return 0
    print(f"wrote {write(changes)} listing(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
