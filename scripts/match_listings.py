"""
match_listings.py — Score scraped listings against existing DB products.

For each row in the CSV whose brand already exists in the DB, finds the
closest-matching product by string distance on name, filtered first by
brand + variant + category, then relaxed to brand + variant, then brand only.

Usage:
  python scripts/match_listings.py --csv prototypes/travel-agency-scraper/travel_agency_listings.csv
  python scripts/match_listings.py --csv ... --min-score 0.65
  python scripts/match_listings.py --csv ... --brand "Off Hours"
  python scripts/match_listings.py --csv ... --out matches.csv

Output columns:
  score, csv_brand, csv_name, csv_variant, csv_category,
  db_product_id, db_name, db_variant, db_category, match_basis
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

try:
    import psycopg2
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


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def norm_brand(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def parse_args():
    p = argparse.ArgumentParser(description="Score CSV listings against DB products by string distance")
    p.add_argument("--csv", required=True, help="Scraper CSV to compare against DB")
    p.add_argument("--min-score", type=float, default=0.0, help="Only show rows at or above this score (0–1)")
    p.add_argument("--brand", default=None, help="Filter to a single brand (raw string, matched after alias resolution)")
    p.add_argument("--out", default=None, help="Write results to CSV instead of stdout")
    return p.parse_args()


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
        csv_rows = list(csv.DictReader(f))

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    cur.execute("SELECT alias, canonical_brand FROM brand_aliases")
    aliases: dict[str, str] = {a: c for a, c in cur.fetchall()}

    cur.execute("SELECT id, name, brand, variant, category FROM products")
    db_products = cur.fetchall()
    conn.close()

    def resolve(b: str) -> str:
        return aliases.get(b, b)

    # Index DB products by normalised brand
    db_by_brand: dict[str, list] = defaultdict(list)
    for pid, name, brand, variant, cat in db_products:
        db_by_brand[norm_brand(brand or "")].append({
            "id":       str(pid),
            "name":     name,
            "variant":  (variant or "").lower(),
            "category": (cat or "").lower(),
        })

    results = []

    for row in csv_rows:
        brand = resolve(row.get("brand", "").strip())
        if not brand:
            continue

        if args.brand and brand.lower() != args.brand.lower():
            continue

        nb = norm_brand(brand)
        candidates = db_by_brand.get(nb)
        if not candidates:
            continue

        csv_variant  = row.get("variant", "").strip().lower()
        csv_category = row.get("category", "").strip().lower()
        csv_name     = row.get("name", "").strip()

        # Match basis: tightest filter that yields at least one candidate
        by_var_cat = [c for c in candidates if c["variant"] == csv_variant and c["category"] == csv_category]
        by_var     = [c for c in candidates if c["variant"] == csv_variant]
        by_cat     = [c for c in candidates if c["category"] == csv_category]

        if by_var_cat:
            pool, basis = by_var_cat, "brand+variant+category"
        elif by_var:
            pool, basis = by_var, "brand+variant"
        elif by_cat:
            pool, basis = by_cat, "brand+category"
        else:
            pool, basis = candidates, "brand"

        best  = max(pool, key=lambda c: similarity(csv_name, c["name"]))
        score = similarity(csv_name, best["name"])

        if score < args.min_score:
            continue

        results.append({
            "score":        f"{score:.3f}",
            "csv_brand":    brand,
            "csv_name":     csv_name,
            "csv_variant":  row.get("variant", "").strip(),
            "csv_category": csv_category,
            "db_product_id": best["id"],
            "db_name":      best["name"],
            "db_variant":   best["variant"],
            "db_category":  best["category"],
            "match_basis":  basis,
        })

    results.sort(key=lambda r: float(r["score"]), reverse=True)

    columns = [
        "score", "csv_brand", "csv_name", "csv_variant", "csv_category",
        "db_product_id", "db_name", "db_variant", "db_category", "match_basis",
    ]

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(results)
        print(f"Wrote {len(results)} rows to {args.out}")
    else:
        # Pretty-print to stdout
        print(f"{'score':>5}  {'brand':<18}  {'CSV name':<45} {'var':<7}  DB name  [var]  (basis)")
        print("-" * 150)
        for r in results:
            flag = "  ***" if float(r["score"]) >= 0.65 else ""
            print(
                f"  {r['score']:>5}  {r['csv_brand']:<18}  {r['csv_name']:<45}"
                f" [{r['csv_variant']:<5}]  {r['db_name']}  [{r['db_variant']}]"
                f"  ({r['match_basis']}){flag}"
            )
        print(f"\n{len(results)} rows  |  above 0.65: {sum(1 for r in results if float(r['score']) >= 0.65)}")


if __name__ == "__main__":
    main()
