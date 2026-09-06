#!/usr/bin/env python3
"""
migrate_add_brand_catalogs.py — Brand catalogs as a first-class table.

Why the database and not just files: `products` is a view over `listings` with no
table behind it, so nothing can hold a foreign key to a product. That is why "verify
once, covers every store" is not expressible today — a verification claim can only
attach to one store's listing. `order_items` snapshots name/brand/variant/price at
submission precisely because listings get rewritten under it, and
`listing_terpenes` / `listing_cannabinoids` / `lab_reports` are keyed per-listing
when a terpene profile really belongs to a product or batch. Those three are empty
today, so re-pointing them at catalog entries is free now and expensive later.

The generated `data/catalogs/<brand>.json` export stays the read path for enrichment,
which must keep working with no DB access — enrichment runs in sandboxes where 5432
is blocked, and a CSV plus a cache file is a self-contained handoff. Postgres is the
system of record; the file is a build artifact.

Entries are never deleted. When a product drops off the source, set is_active = false
and leave last_seen_at: listings point at these rows, so a delete would dangle the FK
and destroy history. Staleness is a state, not a deletion — the same rule the
verification lapse model already uses.

Usage:
  python scripts/migrate_add_brand_catalogs.py            # show the SQL, change nothing
  python scripts/migrate_add_brand_catalogs.py --run
"""

import argparse
import os
import sys

try:
    import psycopg2
except ImportError:
    sys.exit("psycopg2-binary required: pip install psycopg2-binary")

DDL = """
CREATE TABLE IF NOT EXISTS brand_catalogs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_slug    text NOT NULL UNIQUE,
  brand_name    text NOT NULL,
  source_url    text,
  source_method text NOT NULL,
  fetched_at    timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS brand_catalog_entries (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  catalog_id    uuid NOT NULL REFERENCES brand_catalogs(id) ON DELETE CASCADE,
  external_id   text,
  name          text NOT NULL,
  product_line  text,
  category      text,
  subtype       text,
  strain        text,
  variant       text,
  attributes    jsonb,
  match_terms   text[],
  is_active     boolean NOT NULL DEFAULT true,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  verified_fields jsonb,
  verified_by   text,
  verified_at   timestamptz,
  UNIQUE (catalog_id, external_id)
);

CREATE INDEX IF NOT EXISTS brand_catalog_entries_catalog_idx
  ON brand_catalog_entries (catalog_id) WHERE is_active;

ALTER TABLE listings
  ADD COLUMN IF NOT EXISTS catalog_entry_id         uuid REFERENCES brand_catalog_entries(id),
  ADD COLUMN IF NOT EXISTS catalog_match_confidence real,
  ADD COLUMN IF NOT EXISTS catalog_match_method     text;

CREATE INDEX IF NOT EXISTS listings_catalog_entry_idx
  ON listings (catalog_entry_id) WHERE catalog_entry_id IS NOT NULL;
"""


def load_env(root: str) -> None:
    path = os.path.join(root, ".env")
    if not os.path.isfile(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description="Add brand catalog tables")
    ap.add_argument("--run", action="store_true", help="Execute (default: print only)")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env(root)

    if not args.run:
        print("-- DDL that WOULD be executed (nothing has run):")
        print(DDL)
        print("-- Pass --run to apply.")
        return

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()

    cur.execute("""
        SELECT table_name, count(*) AS columns
        FROM information_schema.columns
        WHERE table_name IN ('brand_catalogs','brand_catalog_entries')
        GROUP BY 1 ORDER BY 1
    """)
    for name, cols in cur.fetchall():
        print(f"  {name}: {cols} columns")
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='listings' AND column_name LIKE 'catalog%' ORDER BY 1
    """)
    print("  listings gained: " + ", ".join(r[0] for r in cur.fetchall()))
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
