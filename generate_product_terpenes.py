#!/usr/bin/env python3
"""
Generate /tmp/product_terpenes.csv from:
  - /tmp/products.csv   (must contain column: id)
  - /tmp/terpenes.csv   (must contain column: id)

Output columns match SQLModel join table:
  product_id,terpene_id,percent

Rules:
  - 1 to 4 terpenes per product
  - unique terpenes per product
  - percent values are random floats (2 decimals)
  - total terpene % per product is random in a plausible range (0.6% to 3.0%)
"""

import csv
import os
import random
from pathlib import Path
from typing import List, Dict


PRODUCTS_CSV = Path("/tmp/products.csv")
TERPENES_CSV = Path("/tmp/terpenes.csv")
OUT_CSV = Path("/tmp/product_terpenes.csv")

MIN_TERPS = 1
MAX_TERPS = 4
TOTAL_PERCENT_MIN = 1.00
TOTAL_PERCENT_MAX = 1.00

SEED = os.getenv("SEED")
if SEED is not None:
    random.seed(int(SEED))


def read_ids(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "id" not in reader.fieldnames:
            raise ValueError(f"{path} must have a header row including an 'id' column")
        ids = []
        for row in reader:
            _id = (row.get("id") or "").strip()
            if _id:
                ids.append(_id)
        if not ids:
            raise ValueError(f"No ids found in {path}")
        return ids


def gen_percentages(k: int) -> List[float]:
    """
    Generate k percentages (2 decimals) that sum to a random total in [TOTAL_PERCENT_MIN, TOTAL_PERCENT_MAX].
    """
    total = random.uniform(TOTAL_PERCENT_MIN, TOTAL_PERCENT_MAX)
    # random weights -> normalize to total
    weights = [random.random() for _ in range(k)]
    s = sum(weights)
    raw = [total * (w / s) for w in weights]

    # round to 2 decimals while preserving sum (as close as possible)
    rounded = [round(x, 2) for x in raw]
    diff = round(total - sum(rounded), 2)

    # push rounding diff into the largest element to keep sum consistent
    if diff != 0:
        idx = max(range(k), key=lambda i: rounded[i])
        rounded[idx] = round(rounded[idx] + diff, 2)

    # ensure non-negative after adjustment
    for i in range(k):
        if rounded[i] < 0:
            rounded[i] = 0.00

    return rounded


def main():
    product_ids = read_ids(PRODUCTS_CSV)
    terpene_ids = read_ids(TERPENES_CSV)

    if len(terpene_ids) < MIN_TERPS:
        raise ValueError("Need at least 1 terpene in terpenes.csv")

    rows: List[Dict[str, str]] = []

    for pid in product_ids:
        k = random.randint(MIN_TERPS, min(MAX_TERPS, len(terpene_ids)))
        chosen = random.sample(terpene_ids, k)
        percents = gen_percentages(k)

        # optionally sort by percent desc for nicer output
        combined = sorted(zip(chosen, percents), key=lambda x: x[1], reverse=True)

        for tid, pct in combined:
            rows.append(
                {
                    "product_id": pid,
                    "terpene_id": tid,
                    "percent": f"{pct:.2f}",
                }
            )

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["product_id", "terpene_id", "percent"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT_CSV}")
    print("Tip: set SEED=123 for deterministic output.")


if __name__ == "__main__":
    main()
