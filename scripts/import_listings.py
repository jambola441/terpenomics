"""
import_listings.py — Import scraped listing CSVs directly into the DB.

For each row in the CSV:
  - Match or create a Product by (name, brand) — case-insensitive exact match
  - Create or update a Listing keyed on (dispensary_id, sku)

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
    # Resolve dispensary slugs
    # ------------------------------------------------------------------
    slugs = {r["dispensary_slug"].strip() for r in rows if r.get("dispensary_slug")}
    cur.execute("SELECT id, slug FROM dispensaries WHERE slug = ANY(%s)", (list(slugs),))
    dispensary_map: dict[str, str] = {slug: str(did) for did, slug in cur.fetchall()}
    missing = slugs - set(dispensary_map)
    if missing:
        print(f"  [WARN] Dispensaries not found (rows will be skipped): {missing}")

    # ------------------------------------------------------------------
    # Load existing products → {(name_lower, brand_lower): id}
    # ------------------------------------------------------------------
    cur.execute("SELECT id, LOWER(name), LOWER(COALESCE(brand, '')) FROM products")
    product_cache: dict[tuple, str] = {
        (name, brand): str(pid) for pid, name, brand in cur.fetchall()
    }
    print(f"  {len(product_cache)} existing products loaded")

    now = utcnow()

    # ------------------------------------------------------------------
    # Collect new products (deduplicate within the CSV too)
    # ------------------------------------------------------------------
    new_products: list[tuple] = []
    for row in rows:
        name = (row.get("name") or "").strip()
        brand = (row.get("brand") or "").strip()
        category = (row.get("category") or "other").strip()
        if not name:
            continue
        key = (name.lower(), brand.lower())
        if key not in product_cache:
            new_id = str(uuid.uuid4())
            product_cache[key] = new_id
            new_products.append((new_id, name, brand or None, category, True, now, now))

    if new_products:
        if not args.dry_run:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO products (id, name, brand, category, is_active, created_at, updated_at) VALUES %s",
                new_products,
            )
        print(f"  {'[DRY] Would create' if args.dry_run else 'Created'} {len(new_products)} new products")

    # ------------------------------------------------------------------
    # Listings: per-dispensary load, then batch insert/update
    # ------------------------------------------------------------------
    total_created = 0
    total_updated = 0
    total_skipped = 0

    for slug, dispensary_id in dispensary_map.items():
        cur.execute(
            "SELECT id, sku FROM listings WHERE dispensary_id = %s AND sku IS NOT NULL",
            (dispensary_id,),
        )
        listing_cache: dict[str, str] = {sku: str(lid) for lid, sku in cur.fetchall()}

        disp_rows = [r for r in rows if r.get("dispensary_slug", "").strip() == slug]

        to_insert: list[tuple] = []
        to_update: list[tuple] = []

        for row in disp_rows:
            name = (row.get("name") or "").strip()
            brand = (row.get("brand") or "").strip()
            if not name:
                total_skipped += 1
                continue

            product_id = product_cache.get((name.lower(), brand.lower()))
            if not product_id:
                total_skipped += 1
                continue

            sku        = (row.get("sku") or "").strip() or None
            price      = parse_int(row.get("price_cents"))
            in_stock   = parse_bool(row.get("in_stock", "true"))
            variant    = (row.get("variant") or "").strip() or None
            url        = (row.get("product_url") or "").strip() or None
            scraped_at = (row.get("scraped_at") or "").strip() or None

            existing_id = listing_cache.get(sku) if sku else None

            if existing_id:
                # (price, variant, url, in_stock, scraped_at, updated_at, id)
                to_update.append((price, variant, url, in_stock, scraped_at, now, existing_id))
            else:
                new_id = str(uuid.uuid4())
                to_insert.append((
                    new_id, product_id, dispensary_id,
                    price, variant, sku, url, in_stock, True, scraped_at, now, now,
                ))
                if sku:
                    listing_cache[sku] = new_id

        if to_insert and not args.dry_run:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO listings
                   (id, product_id, dispensary_id, price_cents, variant, sku, url,
                    in_stock, is_active, scraped_at, created_at, updated_at)
                   VALUES %s""",
                to_insert,
            )

        if to_update and not args.dry_run:
            psycopg2.extras.execute_batch(
                cur,
                """UPDATE listings
                   SET price_cents=%s, variant=%s, url=%s, in_stock=%s,
                       scraped_at=%s, updated_at=%s
                   WHERE id=%s""",
                to_update,
            )

        total_created += len(to_insert)
        total_updated += len(to_update)

        print(f"  {slug}: {len(to_insert)} to create, {len(to_update)} to update")

    if not args.dry_run:
        conn.commit()
    conn.close()

    print()
    print("Done.")
    print(f"  Products: {len(new_products)} created, {len(product_cache) - len(new_products)} matched")
    print(f"  Listings: {total_created} created, {total_updated} updated, {total_skipped} skipped")


if __name__ == "__main__":
    main()
