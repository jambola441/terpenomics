#!/usr/bin/env python3
"""
backfill_attributes.py — populate listings.attributes from product names.

Attributes are derived, not asked for: scripts/attributes.py reads them from the
name with a curated vocabulary, so this costs nothing and can run as often as the
vocabulary changes.

Runs additively on purpose. It writes `attributes` without touching `strain`, so
the products view keeps grouping on strain while the new column fills in. Only
once the view groups on attributes too, and the product count is confirmed
unchanged, is it safe to demote strain — otherwise merch re-merges the moment
colour leaves the column the view is keyed on.

    python scripts/backfill_attributes.py            # report, change nothing
    python scripts/backfill_attributes.py --run
    python scripts/backfill_attributes.py --category merch --run
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import httpx
except ImportError:
    sys.exit("httpx required: pip install httpx")

import attributes as attrs  # noqa: E402

PAGE = 1000


def main() -> None:
    ap = argparse.ArgumentParser(description="Populate listings.attributes")
    ap.add_argument("--run", action="store_true", help="apply (default: dry run)")
    ap.add_argument("--category", help="limit to one category (default: every modelled one)")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    base = url.rstrip("/") + "/rest/v1"
    h = {"apikey": key, "Authorization": f"Bearer {key}",
         "Content-Type": "application/json"}
    c = httpx.Client(timeout=120)

    categories = [args.category] if args.category else sorted(attrs.EXTRACTORS)
    unknown = [x for x in categories if x not in attrs.EXTRACTORS]
    if unknown:
        sys.exit(f"no attribute shape modelled for: {', '.join(unknown)}")

    grand = Counter()
    for category in categories:
        rows, offset = [], 0
        while True:
            r = c.get(f"{base}/listings", headers={**h, "Range": f"{offset}-{offset+PAGE-1}"},
                      params={"select": "id,scraped_name,attributes",
                              "scraped_category": f"eq.{category}", "is_active": "is.true"})
            r.raise_for_status()
            batch = r.json()
            rows.extend(batch)
            if len(batch) < PAGE:
                break
            offset += PAGE

        changes, shapes = [], Counter()
        for row in rows:
            want = attrs.for_category(category, row.get("scraped_name") or "") or None
            if (row.get("attributes") or None) != want:
                changes.append((row["id"], want))
            if want:
                shapes[",".join(sorted(want))] += 1

        print(f"{category}: {len(rows):,} listings, {len(changes):,} would change")
        for shape, n in shapes.most_common():
            print(f"    {shape:22s} {n:5d}")
        grand["rows"] += len(rows)
        grand["changes"] += len(changes)

        if args.run:
            for i, (row_id, want) in enumerate(changes, 1):
                r = c.patch(f"{base}/listings", params={"id": f"eq.{row_id}"},
                            headers={**h, "Prefer": "return=minimal"},
                            content=json.dumps({"attributes": want}))
                if r.status_code >= 300:
                    raise RuntimeError(f"{r.status_code} {r.text[:300]}")
                if i % 250 == 0:
                    print(f"    ...{i:,}/{len(changes):,}")

    print(f"\n{'updated' if args.run else 'would update'} {grand['changes']:,} "
          f"of {grand['rows']:,} rows")
    if not args.run:
        print("Pass --run to apply.")


if __name__ == "__main__":
    main()
