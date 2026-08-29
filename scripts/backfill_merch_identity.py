#!/usr/bin/env python3
"""
backfill_merch_identity.py — recompute merch identity in place, no model calls.

Merch enrichment is entirely deterministic as of _ENRICH_VERSION 7: subtype comes
from the form-factor tokens in enrich.py, variant from size + pack + tips, strain
from colour or flavour, and product_line from the curated map in
data/product_lines.json. None of it asks the model anything.

So a listing already in the database can be corrected from its scraped_name and
scraped_brand alone — no re-scrape, no re-enrich, no cache invalidation, no cost.
That is worth doing directly, because the alternative (bump the version, re-scrape,
re-enrich, re-import) pays for a model pass to reproduce output that is a pure
function of text already stored.

Writes over PostgREST because the Postgres wire protocol is unreachable from some
sandboxes (see DB_ACCESS.md). It only ever PATCHes the four identity columns on
rows whose values actually change; it never inserts or deletes.

    python scripts/backfill_merch_identity.py            # report, change nothing
    python scripts/backfill_merch_identity.py --run
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import httpx
except ImportError:
    sys.exit("httpx required: pip install httpx")

import enrich as e  # noqa: E402
from canonical import find_product_line  # noqa: E402

FIELDS = ("subtype", "variant", "strain", "product_line")
PAGE = 1000
CHUNK = 200


def identity(name: str, brand: str, current_subtype: str | None = None) -> dict:
    """The four identity fields, all read from the name.

    subtype falls back to whatever is already stored rather than to "merch": the
    tokens do not cover everything, and the model legitimately answers subtypes
    they miss — "Doob Tube" is storage, "Glass Tips" are filter-tips, neither
    matches a pattern. Overwriting those with "merch" would be a downgrade, so a
    token only wins when it actually fires.
    """
    token = e.classify_by_token("merch", name)
    fallback = (current_subtype or "merch") if (current_subtype in e.SUBTYPES["merch"]) else "merch"
    return {
        "subtype": token or fallback,
        "variant": e.merch_variant(name) or None,
        "strain": e.merch_strain(name),
        "product_line": find_product_line(brand or "", name) or None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Recompute merch identity in the DB")
    ap.add_argument("--run", action="store_true", help="apply (default: dry run)")
    ap.add_argument("--limit-report", type=int, default=12, help="sample rows to print")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    base = url.rstrip("/") + "/rest/v1"
    h = {"apikey": key, "Authorization": f"Bearer {key}",
         "Content-Type": "application/json"}
    client = httpx.Client(timeout=120)

    rows, offset = [], 0
    while True:
        r = client.get(f"{base}/listings", headers={**h, "Range": f"{offset}-{offset+PAGE-1}"},
                       params={"select": "id,scraped_name,scraped_brand," + ",".join(FIELDS),
                               "scraped_category": "eq.merch", "is_active": "is.true"})
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    print(f"{len(rows):,} active merch listings\n")

    changes, churn = [], Counter()
    for row in rows:
        want = identity(row.get("scraped_name") or "", row.get("scraped_brand") or "",
                        row.get("subtype"))
        diff = {f: v for f, v in want.items() if (row.get(f) or None) != v}
        if diff:
            changes.append((row, diff))
            for f in diff:
                churn[f] += 1

    print(f"{len(changes):,} rows would change")
    for f in FIELDS:
        print(f"  {f:13s} {churn[f]:5d}")

    print(f"\nsample (first {args.limit_report}):")
    for row, diff in changes[:args.limit_report]:
        print(f"  {(row.get('scraped_name') or '')[:54]}")
        for f, v in diff.items():
            print(f"      {f:13s} {row.get(f)!r} -> {v!r}")

    if not args.run:
        print("\nPass --run to apply.")
        return

    written = 0
    for row, diff in changes:
        r = client.patch(f"{base}/listings", params={"id": f"eq.{row['id']}"},
                         headers={**h, "Prefer": "return=minimal"}, content=json.dumps(diff))
        if r.status_code >= 300:
            raise RuntimeError(f"{r.status_code} {r.text[:300]}")
        written += 1
        if written % 200 == 0:
            print(f"  ...{written:,}/{len(changes):,}")
    print(f"\nupdated {written:,} rows")


if __name__ == "__main__":
    main()
