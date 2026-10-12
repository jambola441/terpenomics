#!/usr/bin/env python3
"""
fix_catalog_lines.py — One-time cleanup: a listing of a brand with a catalog carries
only a line that catalog has (catalog_match.catalog_line, the rule imports and
rematch_brand now apply). Untrusted listings (not overlaid by a trusted match) keep
enrichment's guessed line until their next import ("Bagel Hole", "Mini"); this sets
each to the line of the entry it points at, else the reading's line if the catalog
has it, else NULL. Trusted listings and brands without a catalog are not touched.
Over Supabase's REST API (DB_VIA_HTTP=1). Each write is guarded on the stored line.

Usage
-----
  DB_VIA_HTTP=1 python scripts/fix_catalog_lines.py            # dry run: counts per brand
  DB_VIA_HTTP=1 python scripts/fix_catalog_lines.py --write    # write it
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_match as cm  # noqa: E402
import catalog_store  # noqa: E402

COLS = "id,scraped_brand,scraped_category,product_line,catalog_entry_id,catalog_match_method,reading"


def plan(rows: list[dict], catalogs: dict) -> list[tuple[dict, str | None]]:
    """[(row, new line)] for the rows whose line the rule changes."""
    by_id = catalog_store.entries_by_id(catalogs)
    out = []
    for r in rows:
        catalog = catalogs.get(catalog_store.brand_key(r.get("scraped_brand")))
        if not catalog:
            continue
        eid = str(r["catalog_entry_id"]) if r.get("catalog_entry_id") else ""
        if r.get("catalog_match_method") in cm.OVERLAY_METHODS and eid in by_id:
            continue
        line = cm.catalog_line(catalog, eid or None, r.get("reading"), r.get("scraped_category"))
        if (r.get("product_line") or None) != line:
            out.append((r, line))
    return out


def write(changes: list[tuple[dict, str | None]]) -> int:
    import db_http
    groups: dict[tuple, list[str]] = defaultdict(list)
    for r, line in changes:
        groups[(r.get("product_line") or None, line)].append(str(r["id"]))
    n = 0
    for (old, new), ids in groups.items():
        guard = f"product_line=eq.{urllib.parse.quote(old)}" if old else "product_line=is.null"
        for i in range(0, len(ids), 100):
            for attempt in range(4):
                try:
                    n += len(db_http.update("listings", f"id=in.({','.join(ids[i:i + 100])})&{guard}",
                                            {"product_line": new}))
                    break
                except db_http.DbHttpError:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write the changes (else print them)")
    ap.add_argument("--top", type=int, default=15, help="brands to list")
    args = ap.parse_args(argv)
    import db_http
    catalogs = catalog_store.load_all("db")
    rows = db_http.select_all("listings", f"select={COLS}&is_active=is.true&order=id")
    changes = plan(rows, catalogs)
    by_brand = Counter(r.get("scraped_brand") for r, _ in changes)
    print(f"{len(changes)} listing(s) across {len(by_brand)} brand(s) would change line")
    for brand, n in by_brand.most_common(args.top):
        moves = Counter((r.get("product_line"), line) for r, line in changes
                        if r.get("scraped_brand") == brand)
        print(f"  {brand}: {n}  " + "; ".join(f"{o!r} -> {w!r} x{c}" for (o, w), c in moves.most_common(6)))
    if not args.write:
        print("(dry run; --write writes them)")
        return 0
    print(f"wrote {write(changes)} listing(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
