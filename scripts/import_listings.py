"""
import_listings.py — Import scraped listing CSVs into the DB.

Inserts new listings keyed on (dispensary_id, sku). Skips rows whose SKU
already exists for that dispensary. Product matching is not performed here —
it happens in the admin UI.

Usage:
  python scripts/import_listings.py \\
    --csv prototypes/alleaves-scraper/brooklynorganicbuds_listings.csv \\
    [--dry-run]

  DATABASE_URL must be set in the environment or in .env at the project root.
"""

import argparse
import csv
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2-binary required: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_args():
    p = argparse.ArgumentParser(description="Import scraped listings into terpenomics DB")
    p.add_argument("--csv", required=True, help="Path to scraper CSV file")
    p.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    return p.parse_args()


def load_env(project_root: str) -> None:
    env_path = os.path.join(project_root, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key not in os.environ:
                os.environ[key] = val


def parse_bool(val: str) -> bool:
    return str(val).strip().upper() in ("TRUE", "1", "YES")


def parse_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env(project_root)

    args = parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.csv):
        print(f"Error: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("CSV is empty.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Importing {len(rows)} rows from {args.csv}")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # Load brand alias map
    # ------------------------------------------------------------------
    cur.execute("SELECT alias, canonical_brand FROM brand_aliases")
    brand_aliases: dict[str, str] = {a: c for a, c in cur.fetchall()}
    print(f"  {len(brand_aliases)} brand aliases loaded")

    def resolve_brand(brand: str) -> str:
        return brand_aliases.get(brand, brand)

    # ------------------------------------------------------------------
    # Resolve dispensary slugs
    # ------------------------------------------------------------------
    slugs = {r["dispensary_slug"].strip() for r in rows if r.get("dispensary_slug")}
    cur.execute("SELECT id, slug FROM dispensaries WHERE slug = ANY(%s)", (list(slugs),))
    dispensary_map: dict[str, str] = {slug: str(did) for did, slug in cur.fetchall()}
    missing = slugs - set(dispensary_map)
    if missing:
        print(f"  [WARN] Dispensaries not found (rows will be skipped): {missing}")

    now = utcnow()
    total_inserted = 0
    total_skipped  = 0

    for slug, dispensary_id in dispensary_map.items():
        # Load existing SKUs for this dispensary
        cur.execute(
            "SELECT sku FROM listings WHERE dispensary_id = %s AND sku IS NOT NULL",
            (dispensary_id,),
        )
        existing_skus: set[str] = {sku for (sku,) in cur.fetchall()}

        disp_rows = [r for r in rows if r.get("dispensary_slug", "").strip() == slug]
        to_insert: list[tuple] = []

        for row in disp_rows:
            sku = (row.get("sku") or "").strip() or None
            if sku and sku in existing_skus:
                total_skipped += 1
                continue

            scraped_name     = (row.get("name")     or "").strip() or None
            scraped_name_raw = (row.get("name_raw") or "").strip() or None
            scraped_brand    = resolve_brand((row.get("brand") or "").strip()) or None

            if not scraped_name:
                total_skipped += 1
                continue

            to_insert.append((
                str(uuid.uuid4()),
                dispensary_id,
                sku,
                parse_int(row.get("price_cents")),
                (row.get("variant") or "").strip() or None,
                (row.get("product_url") or "").strip() or None,
                parse_bool(row.get("in_stock", "true")),
                True,                                          # is_active
                (row.get("scraped_at") or "").strip() or None,
                scraped_name,
                scraped_name_raw,
                scraped_brand,
                (row.get("category") or "").strip() or None,
                now,
                now,
            ))

        if to_insert and not args.dry_run:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO listings
                   (id, dispensary_id, sku, price_cents, variant, url,
                    in_stock, is_active, scraped_at,
                    scraped_name, scraped_name_raw, scraped_brand, scraped_category, created_at, updated_at)
                   VALUES %s""",
                to_insert,
            )

        total_inserted += len(to_insert)
        print(f"  {slug}: {len(to_insert)} inserted, {len(disp_rows) - len(to_insert)} skipped")

    if not args.dry_run:
        conn.commit()
    conn.close()

    print()
    print("Done.")
    print(f"  Listings: {total_inserted} inserted, {total_skipped} skipped")


if __name__ == "__main__":
    main()
