"""
auto_match_products.py — Auto-link unmatched listings to existing products by score.

For each unmatched listing, scores it against existing products on a
brand+variant+category basis. If the top candidate meets or exceeds --threshold
(default 1.0), the listing is linked to that product. Lower the threshold
to catch near-identical names (e.g. 0.95).

Listings below the threshold are left unmatched for manual review.

Usage:
    python scripts/auto_match_products.py [--threshold 1.0] [--dry-run]
"""

import argparse
import os
import sys
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2-binary required: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)


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
    p = argparse.ArgumentParser(description="Auto-match unmatched listings to existing products")
    p.add_argument("--threshold", type=float, default=1.0,
                   help="Min score to auto-link (default: 1.0 = exact name match)")
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

    cur.execute("SELECT alias, canonical_brand FROM brand_aliases")
    brand_aliases: dict[str, str] = {r["alias"]: r["canonical_brand"] for r in cur.fetchall()}
    print(f"  {len(brand_aliases)} brand aliases loaded")

    cur.execute("SELECT id, name, brand, variant, category FROM products")
    products = cur.fetchall()
    print(f"  {len(products)} existing products loaded")

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

    auto_matched = 0
    skipped_low  = 0
    skipped_no_candidate = 0
    now = utcnow()

    for listing in unmatched:
        scraped_name     = (listing["scraped_name"]     or "").strip()
        scraped_brand    = (listing["scraped_brand"]    or "").strip()
        variant          = (listing["variant"]          or "").strip()
        scraped_category = (listing["scraped_category"] or "").strip()

        if not scraped_name:
            skipped_low += 1
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

        if not candidates:
            skipped_no_candidate += 1
            continue

        top = candidates[0]
        top_score = top["score"]
        top_basis = top["basis"]

        if top_score < args.threshold or top_basis != "brand+variant+category":
            skipped_low += 1
            continue

        product_id = str(top["product"].id)
        print(f"  {'[DRY] ' if args.dry_run else ''}MATCH  {scraped_brand or '?'} — "
              f"{scraped_name} ({variant or '-'})  "
              f"→ score {top_score:.3f} \"{top['product'].name}\"")

        if not args.dry_run:
            cur.execute(
                "UPDATE listings SET product_id = %s, updated_at = %s WHERE id = %s",
                (product_id, now, str(listing["id"])),
            )

        auto_matched += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  Matched : {auto_matched}")
    print(f"  Skipped (score < {args.threshold} or basis != brand+variant+category): {skipped_low}")
    print(f"  Skipped (no brand/variant/category candidate): {skipped_no_candidate}")


if __name__ == "__main__":
    main()
