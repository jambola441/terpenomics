#!/usr/bin/env python3
"""
Generate /tmp/product_cannabinoids.csv from:
  - /tmp/products.csv      (must contain column: id)
  - /tmp/cannabinoids.csv  (must contain columns: id, family)

Output columns match SQLModel join table:
  product_id,cannabinoid_id,percent

Rules:
  - 1 primary THC cannabinoid per product  (e.g. Delta-9 THC or THCA)
  - 1 primary CBD cannabinoid per product  (e.g. CBD or CBDA)
  - 0 to 2 additional minor cannabinoids per product
  - percent values are random floats (2 decimals)
  - THC total: random in [15.0, 30.0]%
  - CBD total: random in [0.1,  1.0]%
  - each minor cannabinoid: random in [0.1, 1.0]%
"""

import csv
import os
import random
from pathlib import Path
from typing import List, Dict

PRODUCTS_CSV = Path("/tmp/products.csv")
CANNABINOIDS_CSV = Path("/tmp/cannabinoids.csv")
OUT_CSV = Path("/tmp/product_cannabinoids.csv")

THC_PERCENT_MIN = 15.0
THC_PERCENT_MAX = 30.0
CBD_PERCENT_MIN = 0.1
CBD_PERCENT_MAX = 1.0
MINOR_PERCENT_MIN = 0.1
MINOR_PERCENT_MAX = 1.0
MAX_MINOR = 2

SEED = os.getenv("SEED")
if SEED is not None:
    random.seed(int(SEED))


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader]
    if not rows:
        raise ValueError(f"No rows found in {path}")
    return rows


def main():
    product_rows = read_csv(PRODUCTS_CSV)
    cannabinoid_rows = read_csv(CANNABINOIDS_CSV)

    if "id" not in cannabinoid_rows[0]:
        raise ValueError("cannabinoids.csv must have an 'id' column")
    if "family" not in cannabinoid_rows[0]:
        raise ValueError("cannabinoids.csv must have a 'family' column")

    thc_ids = [r["id"].strip() for r in cannabinoid_rows if r.get("family", "").strip() == "thc"]
    cbd_ids = [r["id"].strip() for r in cannabinoid_rows if r.get("family", "").strip() == "cbd"]
    all_ids = [r["id"].strip() for r in cannabinoid_rows]

    if not thc_ids:
        raise ValueError("No THC cannabinoids found in cannabinoids.csv")
    if not cbd_ids:
        raise ValueError("No CBD cannabinoids found in cannabinoids.csv")

    product_ids = [r["id"].strip() for r in product_rows if r.get("id", "").strip()]

    out_rows: List[Dict[str, str]] = []

    for pid in product_ids:
        used: set = set()

        primary_thc = random.choice(thc_ids)
        primary_cbd = random.choice(cbd_ids)
        used.add(primary_thc)
        used.add(primary_cbd)

        minor_pool = [cid for cid in all_ids if cid not in used]
        k = random.randint(0, min(MAX_MINOR, len(minor_pool)))
        minors = random.sample(minor_pool, k)

        entries = [
            (primary_thc, round(random.uniform(THC_PERCENT_MIN, THC_PERCENT_MAX), 2)),
            (primary_cbd, round(random.uniform(CBD_PERCENT_MIN, CBD_PERCENT_MAX), 2)),
        ] + [
            (cid, round(random.uniform(MINOR_PERCENT_MIN, MINOR_PERCENT_MAX), 2))
            for cid in minors
        ]

        # sort by percent desc
        entries.sort(key=lambda x: x[1], reverse=True)

        for cid, pct in entries:
            out_rows.append(
                {
                    "product_id": pid,
                    "cannabinoid_id": cid,
                    "percent": f"{pct:.2f}",
                }
            )

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["product_id", "cannabinoid_id", "percent"])
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {len(out_rows)} rows to {OUT_CSV}")
    print("Tip: set SEED=123 for deterministic output.")


if __name__ == "__main__":
    main()
