"""
Analyze products with listing_count > 3 for grouping quality.
Flags: COLLAPSED (same dispensary twice), DIVERGENT (different items merged),
       UNENRICHED (NULL strain for enrichable category).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine

ENRICHABLE = {"flower", "vaporizers", "concentrate", "preroll"}
THRESHOLD = 3


def token_overlap(a: str, b: str) -> float:
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def analyze():
    with engine.connect() as conn:
        products = conn.execute(text("""
            SELECT brand, category, subtype, strain, variant, listing_count, dispensary_count
            FROM products
            WHERE listing_count > :threshold
            ORDER BY listing_count DESC
        """), {"threshold": THRESHOLD}).mappings().all()

        if not products:
            print(f"No products with listing_count > {THRESHOLD} found.")
            return

        print(f"{'='*70}")
        print(f"Products with listing_count > {THRESHOLD}: {len(products)} found")
        print(f"{'='*70}\n")

        total_ok = 0
        total_collapsed = 0
        total_divergent = 0
        total_unenriched = 0

        for p in products:
            brand    = p["brand"]
            category = p["category"]
            subtype  = p["subtype"]
            strain   = p["strain"]
            variant  = p["variant"]
            count    = p["listing_count"]
            stores   = p["dispensary_count"]

            # Fetch constituent listings
            rows = conn.execute(text("""
                SELECT l.scraped_name, l.sku, l.price_cents, l.strain, l.subtype, d.name AS dispensary_name
                FROM listings l
                JOIN dispensaries d ON d.id = l.dispensary_id
                WHERE l.is_active = true
                  AND (l.scraped_brand = :brand OR (:brand IS NULL AND l.scraped_brand IS NULL))
                  AND (l.scraped_category = :category OR (:category IS NULL AND l.scraped_category IS NULL))
                  AND (l.subtype = :subtype OR (:subtype IS NULL AND l.subtype IS NULL))
                  AND (l.strain = :strain OR (:strain IS NULL AND l.strain IS NULL))
                  AND (l.variant = :variant OR (:variant IS NULL AND l.variant IS NULL))
                ORDER BY d.name, l.scraped_name
            """), {"brand": brand, "category": category, "subtype": subtype,
                   "strain": strain, "variant": variant}).mappings().all()

            flags = []

            # UNENRICHED: NULL strain for enrichable category
            if category in ENRICHABLE and strain is None:
                flags.append("UNENRICHED")

            # COLLAPSED: same dispensary more than once
            dispensary_counts: dict[str, int] = {}
            for r in rows:
                dispensary_counts[r["dispensary_name"]] = dispensary_counts.get(r["dispensary_name"], 0) + 1
            dupes = {k: v for k, v in dispensary_counts.items() if v > 1}
            if dupes:
                flags.append(f"COLLAPSED ({', '.join(f'{k}:{v}x' for k, v in dupes.items())})")

            # DIVERGENT: scraped_names have low pairwise overlap
            names = [r["scraped_name"] for r in rows if r["scraped_name"]]
            if len(names) >= 2:
                min_overlap = 1.0
                worst_pair = ("", "")
                for i in range(len(names)):
                    for j in range(i + 1, len(names)):
                        ov = token_overlap(names[i], names[j])
                        if ov < min_overlap:
                            min_overlap = ov
                            worst_pair = (names[i], names[j])
                if min_overlap < 0.4:
                    flags.append(f"DIVERGENT (overlap={min_overlap:.0%}, e.g. '{worst_pair[0]}' vs '{worst_pair[1]}')")

            status = "OK" if not flags else " | ".join(flags)

            if not flags:
                total_ok += 1
            else:
                if any(f.startswith("COLLAPSED") for f in flags):
                    total_collapsed += 1
                if any(f.startswith("DIVERGENT") for f in flags):
                    total_divergent += 1
                if "UNENRICHED" in flags:
                    total_unenriched += 1

            # Print product
            tuple_str = f"{brand or 'NULL'} / {category or 'NULL'} / {subtype or 'NULL'} / {strain or 'NULL'} / {variant or 'NULL'}"
            print(f"[{count} listings, {stores} store(s)]  {tuple_str}")
            print(f"  Status: {status}")

            # Print listing detail
            for r in rows:
                price = f"${r['price_cents']/100:.2f}" if r["price_cents"] else "—"
                print(f"    {r['dispensary_name']:30s}  {(r['scraped_name'] or '—')[:50]:50s}  {price}")
            print()

        print(f"{'='*70}")
        print(f"Summary: {len(products)} products — {total_ok} OK, "
              f"{total_collapsed} collapsed, {total_divergent} divergent, {total_unenriched} unenriched")
        print(f"{'='*70}")


if __name__ == "__main__":
    analyze()
