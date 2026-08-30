#!/usr/bin/env python3
"""
migrate_add_verification.py — add human-verification columns to listings.

Today a human correction survives exactly one scrape. import_listings.py's
ON CONFLICT DO UPDATE rewrites subtype, strain, product_line and variant
unconditionally, and enrich() rewrites them again from the model or the token
rules. There is no column the pipeline will not overwrite, so review work has a
lifetime of one cycle. These columns are what let it persist.

Adds:

  verified_fields  jsonb        per-field claims, see below
  verified_at      timestamptz  most recent verification, for indexing and reporting

verified_fields holds one entry per verified field:

  {
    "strain":  {"value": "Blue Dream", "by": "pablo", "at": "2026-08-27T...",
                "name_hash": "9f2c..."},
    "variant": {"value": "3.5g", ...}
  }

Provenance is per field rather than per row because fields get verified at
different times and by different people, and because a claim needs to say what it
was checked against.

name_hash is the point of the design. Verification attaches to a
(listing, scraped_name) pair, not to a listing: if a dispensary renames a product,
the row is now describing different text and the claim should lapse rather than
silently vouch for something nobody read. scripts/verification.py compares the
stored hash to the live name and treats a mismatch as unverified.

Idempotent — safe to re-run.

    python scripts/migrate_add_verification.py            # show the SQL
    python scripts/migrate_add_verification.py --run
"""

import argparse
import os
import sys

STEPS = [
    ("add verified_fields",
     "ALTER TABLE listings ADD COLUMN IF NOT EXISTS verified_fields jsonb"),
    ("add verified_at",
     "ALTER TABLE listings ADD COLUMN IF NOT EXISTS verified_at timestamptz"),
    # Partial: the overwhelming majority of rows are unverified, and every query
    # that cares wants only the ones that are not.
    ("index verified rows",
     "CREATE INDEX IF NOT EXISTS listings_verified_idx ON listings (verified_at) "
     "WHERE verified_fields IS NOT NULL"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description="Add verification columns to listings")
    ap.add_argument("--run", action="store_true", help="execute (default: print the SQL)")
    args = ap.parse_args()

    if not args.run:
        print("-- would run:\n")
        for label, sql in STEPS:
            print(f"-- {label}\n{sql};\n")
        print("Pass --run to execute, or paste the above into the SQL editor.")
        return

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db_http import run_sql

    for label, sql in STEPS:
        print(f"{label} ...")
        run_sql(sql)
    print("\ndone")


if __name__ == "__main__":
    main()
