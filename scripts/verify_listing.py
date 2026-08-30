#!/usr/bin/env python3
"""
verify_listing.py — sign off on a listing's fields, or inspect what is signed.

A verified field is protected from the pipeline: enrich() will not re-derive it,
import_listings.py will not overwrite it on the next scrape, and an
_ENRICH_VERSION bump does not sweep it away with the cache. See verification.py
for the lapse rule.

    # what is verified, and what has lapsed
    python scripts/verify_listing.py --status
    python scripts/verify_listing.py --show <listing-id>

    # sign off — takes the values already on the row unless told otherwise
    python scripts/verify_listing.py --id <listing-id> --fields strain,variant --by pablo
    python scripts/verify_listing.py --id <listing-id> --set strain="Blue Dream" --by pablo

    # withdraw
    python scripts/verify_listing.py --id <listing-id> --clear strain --by pablo

Writes over PostgREST (see DB_ACCESS.md); it only ever PATCHes verification
columns on the one row named, and never touches anything else.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import httpx
except ImportError:
    sys.exit("httpx required: pip install httpx")

import verification  # noqa: E402

SELECT = ("id,scraped_name,scraped_brand,scraped_category,subtype,strain,"
          "product_line,variant,verified_fields,verified_at")


def client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return (url.rstrip("/") + "/rest/v1",
            {"apikey": key, "Authorization": f"Bearer {key}",
             "Content-Type": "application/json"},
            httpx.Client(timeout=60))


def fetch(base, h, c, listing_id: str) -> dict:
    r = c.get(f"{base}/listings", headers=h,
              params={"select": SELECT, "id": f"eq.{listing_id}"})
    r.raise_for_status()
    rows = r.json()
    if not rows:
        sys.exit(f"no listing {listing_id}")
    return rows[0]


def show(row: dict) -> None:
    print(f"{row['scraped_name']}")
    print(f"  brand={row.get('scraped_brand')!r} category={row.get('scraped_category')!r}")
    for f in verification.VERIFIABLE:
        print(f"  {f:13s} {row.get(f)!r}")
    live = verification.verified_fields(row)
    lapsed = verification.lapsed_fields(row)
    print(f"\n  verified: {json.dumps(live) if live else 'none'}")
    if lapsed:
        print(f"  LAPSED (renamed since review, re-check): {', '.join(sorted(lapsed))}")
        for f, cl in lapsed.items():
            print(f"    {f}: was {cl.get('value')!r}, signed by {cl.get('by')} at {cl.get('at')}")


def status(base, h, c) -> None:
    r = c.get(f"{base}/listings", headers={**h, "Prefer": "count=exact", "Range": "0-0"},
              params={"select": "id", "is_active": "is.true"})
    total = int(r.headers.get("content-range", "0-0/0").split("/")[-1])
    r = c.get(f"{base}/listings", headers=h,
              params={"select": "scraped_name,verified_fields",
                      "verified_fields": "not.is.null", "is_active": "is.true"})
    r.raise_for_status()
    rows = r.json()
    live = sum(1 for x in rows if verification.verified_fields(x))
    lapsed = sum(1 for x in rows if verification.lapsed_fields(x))
    print(f"active listings      {total:,}")
    print(f"with any claim       {len(rows):,}")
    print(f"  live               {live:,}")
    print(f"  lapsed (re-check)  {lapsed:,}")
    if total:
        print(f"\nverified coverage    {live/total*100:.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify listing fields")
    ap.add_argument("--id", help="listing id to modify")
    ap.add_argument("--show", metavar="ID", help="print one listing's verification state")
    ap.add_argument("--status", action="store_true", help="fleet-wide coverage")
    ap.add_argument("--fields", help="comma-separated fields to verify at their current values")
    ap.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                    help="verify a field at an explicit value (repeatable)")
    ap.add_argument("--clear", help="comma-separated fields to withdraw")
    ap.add_argument("--by", help="who is signing (required for any write)")
    args = ap.parse_args()

    base, h, c = client()

    if args.status:
        return status(base, h, c)
    if args.show:
        return show(fetch(base, h, c, args.show))
    if not args.id:
        ap.error("give --id, --show or --status")

    row = fetch(base, h, c, args.id)
    existing = row.get("verified_fields") or {}

    if args.clear:
        drop = [f.strip() for f in args.clear.split(",") if f.strip()]
        kept = {k: v for k, v in existing.items() if k not in drop}
        payload = {"verified_fields": kept or None,
                   "verified_at": datetime.now(timezone.utc).isoformat() if kept else None}
        r = c.patch(f"{base}/listings", params={"id": f"eq.{args.id}"},
                    headers={**h, "Prefer": "return=minimal"}, content=json.dumps(payload))
        r.raise_for_status()
        print(f"withdrew {', '.join(drop)}")
        return show(fetch(base, h, c, args.id))

    if not args.by:
        ap.error("--by is required when signing (a claim without an author is not a claim)")

    fields = {}
    for f in (args.fields or "").split(","):
        f = f.strip()
        if f:
            fields[f] = row.get(f)
    for pair in args.set:
        if "=" not in pair:
            ap.error(f"--set expects FIELD=VALUE, got {pair!r}")
        k, v = pair.split("=", 1)
        fields[k.strip()] = v
    if not fields:
        ap.error("give --fields and/or --set")

    try:
        claims = verification.claim(fields, row["scraped_name"], args.by, existing)
    except ValueError as exc:
        ap.error(str(exc))

    payload = {"verified_fields": claims,
               "verified_at": datetime.now(timezone.utc).isoformat()}
    r = c.patch(f"{base}/listings", params={"id": f"eq.{args.id}"},
                headers={**h, "Prefer": "return=minimal"}, content=json.dumps(payload))
    r.raise_for_status()
    print(f"signed {', '.join(sorted(fields))} as {args.by}\n")
    show(fetch(base, h, c, args.id))


if __name__ == "__main__":
    main()
