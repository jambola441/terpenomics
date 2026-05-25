#!/usr/bin/env python3
"""
migrate.py — Drop all tables and recreate from models.py, then create the products VIEW.

Usage:
    python scripts/migrate.py          # dry-run: shows what would happen
    python scripts/migrate.py --run    # executes the migration
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from database import engine
from models import SQLModel  # noqa: F401 — imports all table metadata via models

# Tables in safe drop order (children before parents)
DROP_ORDER = [
    "listing_terpenes",
    "listing_cannabinoids",
    "product_terpenes",       # old — may not exist
    "product_cannabinoids",   # old — may not exist
    "lab_reports",
    "purchase_items",
    "purchases",
    "listings",
    "products",               # old — may not exist
    "terpenes",
    "cannabinoids",
    "dispensaries",
    "customers",
]

PRODUCTS_VIEW = """
CREATE VIEW products AS
SELECT
    scraped_brand                                               AS brand,
    scraped_category                                            AS category,
    subtype,
    product_line,
    strain,
    variant,
    COUNT(*)                                                    AS listing_count,
    COUNT(DISTINCT dispensary_id)                               AS dispensary_count,
    MIN(price_cents) FILTER (WHERE in_stock = true)             AS min_price_cents,
    MAX(price_cents) FILTER (WHERE in_stock = true)             AS max_price_cents,
    BOOL_OR(in_stock)                                           AS any_in_stock
FROM listings
WHERE is_active = true
GROUP BY scraped_brand, scraped_category, subtype, product_line, strain, variant;
"""


def run(execute: bool) -> None:
    from sqlalchemy import text

    with engine.connect() as conn:
        with conn.begin():
            print("Dropping tables ...")
            for table in DROP_ORDER:
                sql = f'DROP TABLE IF EXISTS "{table}" CASCADE'
                print(f"  {sql}")
                if execute:
                    conn.execute(text(sql))

            print("\nDropping old products view if exists ...")
            sql = 'DROP VIEW IF EXISTS products CASCADE'
            print(f"  {sql}")
            if execute:
                conn.execute(text(sql))

    if execute:
        print("\nCreating tables from models ...")
        SQLModel.metadata.create_all(engine)
        print("  done.")

        print("\nCreating products VIEW ...")
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text(PRODUCTS_VIEW))
        print("  done.")
    else:
        print("\n[dry-run] Pass --run to execute.")
        print("\nWould then create tables:")
        for t in SQLModel.metadata.sorted_tables:
            print(f"  {t.name}")
        print("\nWould then create VIEW: products")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Execute the migration (default is dry-run)")
    args = parser.parse_args()
    run(execute=args.run)
