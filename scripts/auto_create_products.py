"""
auto_create_products.py — Auto-create products for unmatched listings with no good candidate.

For each unmatched listing, scores it against existing products. If the best
candidate is below --threshold (default 0.5), creates a new product from
scraped data and links the listing. Listings with a candidate at or above the
threshold are left unmatched for manual review in the UI.

Usage:
    python scripts/auto_create_products.py [--threshold 0.5] [--dry-run]
"""

import argparse
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper_common import CATEGORY_MAP

# Reverse-map our internal category values to a display label
_CATEGORY_DISPLAY = {v: v for v in set(CATEGORY_MAP.values())}


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


def parse_args():
    p = argparse.ArgumentParser(description="Auto-create products for unmatched listings")
    p.add_argument("--threshold", type=float, default=0.5,
                   help="Max score below which a new product is auto-created (default: 0.5)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print actions without writing to DB")
    return p.parse_args()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env(project_root)

    args = parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ------------------------------------------------------------------
    # Load brand aliases
    # ------------------------------------------------------------------
    cur.execute("SELECT alias, canonical_brand FROM brand_aliases")
    brand_aliases: dict[str, str] = {r["alias"]: r["canonical_brand"] for r in cur.fetchall()}
    print(f"  {len(brand_aliases)} brand aliases loaded")

    # ------------------------------------------------------------------
    # Load all existing products as lightweight dicts
    # ------------------------------------------------------------------
    cur.execute("SELECT id, name, brand, variant, category FROM products")
    products = cur.fetchall()
    print(f"  {len(products)} existing products loaded")

    # ------------------------------------------------------------------
    # Load all unmatched listings
    # ------------------------------------------------------------------
    cur.execute("""
        SELECT l.id, l.scraped_name, l.scraped_brand, l.variant,
               l.scraped_category, l.dispensary_id, d.slug
        FROM listings l
        JOIN dispensaries d ON d.id = l.dispensary_id
        WHERE l.product_id IS NULL
          AND l.scraped_name IS NOT NULL
    """)
    unmatched = cur.fetchall()
    print(f"  {len(unmatched)} unmatched listings\n")

    # ------------------------------------------------------------------
    # Import score_candidates (uses Product-like objects; adapt to dicts)
    # ------------------------------------------------------------------
    sys.path.insert(0, os.path.join(project_root, "services"))
    from matching import score_candidates

    class _Row:
        def __init__(self, r):
            self.id       = r["id"]
            self.name     = r["name"]
            self.brand    = r["brand"]
            self.variant  = r["variant"]
            self.category = r["category"]

    product_objs = [_Row(p) for p in products]

    # ------------------------------------------------------------------
    # Process each unmatched listing
    # ------------------------------------------------------------------
    auto_created  = 0
    skipped_match = 0
    skipped_noname = 0
    now = utcnow()

    for listing in unmatched:
        scraped_name     = (listing["scraped_name"]     or "").strip()
        scraped_brand    = (listing["scraped_brand"]    or "").strip()
        variant          = (listing["variant"]          or "").strip()
        scraped_category = (listing["scraped_category"] or "").strip()

        if not scraped_name:
            skipped_noname += 1
            continue

        candidates = score_candidates(
            scraped_name=scraped_name,
            scraped_brand=scraped_brand,
            scraped_variant=variant,
            scraped_category=scraped_category,
            products=product_objs,
            brand_aliases=brand_aliases,
            top_n=1,
        )

        top_score = candidates[0]["score"] if candidates else 0.0
        top_basis = candidates[0]["basis"] if candidates else ""

        if top_score >= args.threshold and top_basis == "brand+variant+category":
            skipped_match += 1
            top = candidates[0]
            print(f"  SKIP  {scraped_brand} — {scraped_name} ({variant or '-'})  "
                  f"→ score {top_score:.2f} vs \"{top['product'].name}\" [{top_basis}]")
            continue

        # Auto-create a new product
        product_id = str(uuid.uuid4())
        category = scraped_category or "other"

        print(f"  {'[DRY] ' if args.dry_run else ''}CREATE  {scraped_brand or '?'} — "
              f"{scraped_name} ({variant or '-'})")

        if not args.dry_run:
            cur.execute("""
                INSERT INTO products (id, name, brand, variant, category, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
            """, (
                product_id,
                scraped_name,
                scraped_brand or None,
                variant or None,
                category,
                now, now,
            ))
            row = cur.fetchone()
            if row:
                product_id = str(row["id"])
            else:
                # Conflict — fetch the existing product's id
                cur.execute("""
                    SELECT id FROM products
                    WHERE LOWER(name) = LOWER(%s)
                      AND LOWER(COALESCE(brand, '')) = LOWER(COALESCE(%s, ''))
                      AND LOWER(COALESCE(variant, '')) = LOWER(COALESCE(%s, ''))
                """, (scraped_name, scraped_brand or None, variant or None))
                existing = cur.fetchone()
                if existing:
                    product_id = str(existing["id"])
            cur.execute("""
                UPDATE listings SET product_id = %s, updated_at = %s WHERE id = %s
            """, (product_id, now, str(listing["id"])))

        # Always update in-memory list so subsequent listings can match against it
        product_objs.append(_Row({
            "id": product_id, "name": scraped_name,
            "brand": scraped_brand, "variant": variant, "category": category,
        }))

        auto_created += 1

    if not args.dry_run:
        conn.commit()

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  Created : {auto_created}")
    print(f"  Skipped (score >= {args.threshold}): {skipped_match}")
    print(f"  Skipped (no scraped_name): {skipped_noname}")


if __name__ == "__main__":
    main()
