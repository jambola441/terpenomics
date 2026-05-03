"""
import_listings.py — Import scraped listing CSVs into the DB.

Upserts listings keyed on (dispensary_id, sku):
  - INSERT new listings
  - UPDATE existing listings: in_stock, price_cents, image_url, scraped_name,
    scraped_name_raw, scraped_brand, scraped_category, url, scraped_at, updated_at

Product matches (product_id) are preserved on update — matching happens in the
admin UI and is never overwritten by a re-import.

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

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing {len(rows)} rows from {args.csv}")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # Load brand alias map
    cur.execute("SELECT alias, canonical_brand FROM brand_aliases")
    brand_aliases: dict[str, str] = {a: c for a, c in cur.fetchall()}
    print(f"  {len(brand_aliases)} brand aliases loaded")

    def resolve_brand(brand: str) -> str:
        return brand_aliases.get(brand, brand)

    # Resolve dispensary slugs
    slugs = {r["dispensary_slug"].strip() for r in rows if r.get("dispensary_slug")}
    cur.execute("SELECT id, slug FROM dispensaries WHERE slug = ANY(%s)", (list(slugs),))
    dispensary_map: dict[str, str] = {slug: str(did) for did, slug in cur.fetchall()}
    missing = slugs - set(dispensary_map)
    if missing:
        print(f"  [WARN] Dispensaries not found (rows will be skipped): {missing}")

    now = utcnow()
    total_inserted = 0
    total_updated  = 0
    total_skipped  = 0

    for slug, dispensary_id in dispensary_map.items():
        disp_rows = [r for r in rows if r.get("dispensary_slug", "").strip() == slug]

        to_upsert: list[tuple] = []
        no_sku_insert: list[tuple] = []

        for row in disp_rows:
            sku             = (row.get("sku") or "").strip() or None
            scraped_name    = (row.get("name")     or "").strip() or None
            scraped_name_raw = (row.get("name_raw") or "").strip() or None
            scraped_brand   = resolve_brand((row.get("brand") or "").strip()) or None
            scraped_category = (row.get("category") or "").strip() or None
            price_cents     = parse_int(row.get("price_cents"))
            variant         = (row.get("variant") or "").strip() or None
            url             = (row.get("product_url") or "").strip() or None
            image_url       = (row.get("image_url") or "").strip() or None
            in_stock        = parse_bool(row.get("in_stock", "true"))
            scraped_at      = (row.get("scraped_at") or "").strip() or None

            if not scraped_name:
                total_skipped += 1
                continue

            record = (
                str(uuid.uuid4()),  # id (used on INSERT, ignored on UPDATE)
                dispensary_id,
                sku,
                price_cents,
                variant,
                url,
                image_url,
                in_stock,
                True,           # is_active
                scraped_at,
                scraped_name,
                scraped_name_raw,
                scraped_brand,
                scraped_category,
                now,            # created_at
                now,            # updated_at
            )

            if sku:
                to_upsert.append(record)
            else:
                no_sku_insert.append(record)

        # --- Diff summary (runs in both dry-run and live mode) ---
        if to_upsert:
            skus = [r[2] for r in to_upsert]  # index 2 = sku
            cur.execute(
                """
                SELECT sku, in_stock, price_cents, image_url,
                       scraped_name, scraped_brand, scraped_category, url
                FROM listings
                WHERE dispensary_id = %s AND sku = ANY(%s)
                """,
                (dispensary_id, skus),
            )
            existing: dict[str, tuple] = {row[0]: row for row in cur.fetchall()}

            TRACKED = [
                # (label, record_idx, existing_idx)
                ("in_stock",        7, 1),
                ("price_cents",     3, 2),
                ("image_url",       6, 3),
                ("scraped_name",   10, 4),
                ("scraped_brand",  12, 5),
                ("scraped_cat",    13, 6),
                ("url",             5, 7),
            ]

            new_skus, changed, unchanged = [], [], []
            field_change_counts: dict[str, int] = {}

            for rec in to_upsert:
                sku_val = rec[2]
                if sku_val not in existing:
                    new_skus.append(sku_val)
                    continue
                db_row = existing[sku_val]
                diffs = []
                for label, ri, di in TRACKED:
                    nv, ov = rec[ri], db_row[di]
                    if nv != ov:
                        diffs.append(f"{label}: {ov!r} → {nv!r}")
                        field_change_counts[label] = field_change_counts.get(label, 0) + 1
                if diffs:
                    changed.append((rec, diffs))
                else:
                    unchanged.append(sku_val)

            print(f"\n  --- diff: {slug} ---")
            print(f"  new (INSERT): {len(new_skus)}  |  changed (UPDATE): {len(changed)}  |  unchanged: {len(unchanged)}  |  no-SKU inserts: {len(no_sku_insert)}")
            if field_change_counts:
                breakdown = "  field changes: " + ", ".join(
                    f"{k}={v}" for k, v in sorted(field_change_counts.items(), key=lambda x: -x[1])
                )
                print(breakdown)
            if changed:
                print(f"  sample changes (first {min(10, len(changed))}):")
                for rec, diffs in changed[:10]:
                    print(f"    [{rec[2]}] {rec[10] or ''}:  {' | '.join(diffs)}")
            print()

        if not args.dry_run:
            # Upsert rows that have a SKU
            if to_upsert:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO listings
                        (id, dispensary_id, sku, price_cents, variant, url, image_url,
                         in_stock, is_active, scraped_at,
                         scraped_name, scraped_name_raw, scraped_brand, scraped_category,
                         created_at, updated_at)
                    VALUES %s
                    ON CONFLICT (dispensary_id, sku)
                    WHERE sku IS NOT NULL
                    DO UPDATE SET
                        in_stock        = EXCLUDED.in_stock,
                        price_cents     = EXCLUDED.price_cents,
                        image_url       = EXCLUDED.image_url,
                        scraped_name    = EXCLUDED.scraped_name,
                        scraped_name_raw = EXCLUDED.scraped_name_raw,
                        scraped_brand   = EXCLUDED.scraped_brand,
                        scraped_category = EXCLUDED.scraped_category,
                        url             = EXCLUDED.url,
                        scraped_at      = EXCLUDED.scraped_at,
                        updated_at      = EXCLUDED.updated_at
                    """,
                    to_upsert,
                )

            # INSERT-only for rows without a SKU (no natural key to update on)
            if no_sku_insert:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO listings
                       (id, dispensary_id, sku, price_cents, variant, url, image_url,
                        in_stock, is_active, scraped_at,
                        scraped_name, scraped_name_raw, scraped_brand, scraped_category,
                        created_at, updated_at)
                       VALUES %s""",
                    no_sku_insert,
                )

        # Count outcomes (approximate for dry-run)
        total_inserted += len(to_upsert) + len(no_sku_insert)
        total_updated  += 0  # psycopg2 doesn't easily split insert vs update count
        print(f"  {slug}: {len(to_upsert)} upserted (by SKU), {len(no_sku_insert)} inserted (no SKU), {len(disp_rows) - len(to_upsert) - len(no_sku_insert)} skipped")

    if not args.dry_run:
        conn.commit()
    conn.close()

    print()
    print("Done.")
    print(f"  Rows processed: {total_inserted}  skipped (no name): {total_skipped}")


if __name__ == "__main__":
    main()
