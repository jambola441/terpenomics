#!/usr/bin/env python3
"""
migrate_listing_variant_key.py — In-place migration for the variant-aware listing key.

Non-destructive (unlike migrate.py, which drops everything). Idempotent — safe to
re-run. Does three things:

  1. Replaces the unique index (dispensary_id, sku) with
     (dispensary_id, sku, COALESCE(variant, '')) so one SKU can hold a row per
     weight/price tier (Dutchie, Tymber reuse SKUs across tiers).
  2. Adds listings.last_seen_at if missing (import_listings.py writes it, but
     models.py only recently defined it).
  3. Clears synthetic batch_ids — values derived from the SKU ("<sku>", "<sku>-0",
     "<sku>~1g") that scrapers used to fabricate. batch_id is reserved for real
     batch/lot IDs (METRC lookups); only Alleaves provides those.

Usage:
    python scripts/migrate_listing_variant_key.py          # dry-run
    python scripts/migrate_listing_variant_key.py --run    # execute
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import text
from database import engine

STEPS = [
    ("drop old unique index",
     "DROP INDEX IF EXISTS listings_dispensary_sku_unique"),
    ("create variant-aware unique index",
     "CREATE UNIQUE INDEX IF NOT EXISTS listings_dispensary_sku_variant_unique "
     "ON listings (dispensary_id, sku, COALESCE(variant, '')) "
     "WHERE sku IS NOT NULL"),
    ("add last_seen_at column if missing",
     "ALTER TABLE listings ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP"),
    ("clear synthetic batch_ids (sku-derived, not real batches)",
     "UPDATE listings SET batch_id = NULL "
     "WHERE batch_id IS NOT NULL AND sku IS NOT NULL "
     "AND (batch_id = sku OR batch_id LIKE sku || '-%' OR batch_id LIKE sku || '~%')"),
]


def run(execute: bool) -> None:
    with engine.connect() as conn:
        with conn.begin():
            for label, sql in STEPS:
                print(f"{'' if execute else '[dry-run] '}{label}:\n  {sql}")
                if execute:
                    result = conn.execute(text(sql))
                    if result.rowcount is not None and result.rowcount >= 0:
                        print(f"  -> {result.rowcount} row(s) affected")
    if not execute:
        print("\nPass --run to execute.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Execute (default is dry-run)")
    args = parser.parse_args()
    run(execute=args.run)
