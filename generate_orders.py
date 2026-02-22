#!/usr/bin/env python3
"""
Generate:
  - /tmp/purchases.csv
  - /tmp/purchase_items.csv

Inputs:
  - /tmp/customers.csv (must have column: id)
  - /tmp/products.csv  (must have column: id)

Rules:
  - 5 to 15 purchases per customer
  - 1 to 3 items per purchase
  - Each item line_amount_cents corresponds to $30-$150 (inclusive)
  - Purchase total_amount_cents = sum of item line_amount_cents
  - quantity is 1 (kept simple for MVP)
  - purchased_at randomized in last 180 days
  - source = "manual"

Schema aligns to SQLModel:
  purchases: id, customer_id, purchased_at, total_amount_cents, source, notes, created_at, updated_at
  purchase_items: id, purchase_id, product_id, quantity, line_amount_cents
"""

import csv
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

CUSTOMERS_CSV = Path("/tmp/customers.csv")
PRODUCTS_CSV = Path("/tmp/products.csv")
OUT_PURCHASES = Path("/tmp/purchases.csv")
OUT_ITEMS = Path("/tmp/purchase_items.csv")

MIN_PURCHASES_PER_CUSTOMER = 5
MAX_PURCHASES_PER_CUSTOMER = 15

MIN_ITEMS_PER_PURCHASE = 1
MAX_ITEMS_PER_PURCHASE = 3

MIN_PRICE_CENTS = 30_00
MAX_PRICE_CENTS = 150_00

LOOKBACK_DAYS = 180
SOURCE = "manual"

SEED = os.getenv("SEED")
if SEED is not None:
    random.seed(int(SEED))


def iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_ids(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "id" not in reader.fieldnames:
            raise ValueError(f"{path} must have a header row including an 'id' column")
        ids = [(row.get("id") or "").strip() for row in reader]
    ids = [x for x in ids if x]
    if not ids:
        raise ValueError(f"No ids found in {path}")
    return ids


def random_datetime_within(days: int) -> datetime:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    # random seconds between start and now
    delta = int((now - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, delta))


def main() -> None:
    customer_ids = read_ids(CUSTOMERS_CSV)
    product_ids = read_ids(PRODUCTS_CSV)

    purchases_rows: list[dict[str, str]] = []
    items_rows: list[dict[str, str]] = []

    for cid in customer_ids:
        n_purchases = random.randint(MIN_PURCHASES_PER_CUSTOMER, MAX_PURCHASES_PER_CUSTOMER)

        # generate purchases in chronological-ish order per customer
        dts = sorted(random_datetime_within(LOOKBACK_DAYS) for _ in range(n_purchases))

        for purchased_at in dts:
            purchase_id = str(uuid4())
            created_at = purchased_at
            updated_at = purchased_at

            n_items = random.randint(MIN_ITEMS_PER_PURCHASE, min(MAX_ITEMS_PER_PURCHASE, len(product_ids)))
            chosen_products = random.sample(product_ids, n_items)

            total_cents = 0
            for pid in chosen_products:
                item_id = str(uuid4())
                line_cents = random.randint(MIN_PRICE_CENTS, MAX_PRICE_CENTS)
                total_cents += line_cents

                items_rows.append(
                    {
                        "id": item_id,
                        "purchase_id": purchase_id,
                        "product_id": pid,
                        "quantity": "1",
                        "line_amount_cents": str(line_cents),
                    }
                )

            purchases_rows.append(
                {
                    "id": purchase_id,
                    "customer_id": cid,
                    "purchased_at": iso_z(purchased_at),
                    "total_amount_cents": str(total_cents),
                    "source": SOURCE,
                    "notes": "",
                    "created_at": iso_z(created_at),
                    "updated_at": iso_z(updated_at),
                }
            )

    with OUT_PURCHASES.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "customer_id",
                "purchased_at",
                "total_amount_cents",
                "source",
                "notes",
                "created_at",
                "updated_at",
            ],
        )
        writer.writeheader()
        writer.writerows(purchases_rows)

    with OUT_ITEMS.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "purchase_id", "product_id", "quantity", "line_amount_cents"],
        )
        writer.writeheader()
        writer.writerows(items_rows)

    print(f"Wrote purchases: {len(purchases_rows)} rows -> {OUT_PURCHASES}")
    print(f"Wrote purchase_items: {len(items_rows)} rows -> {OUT_ITEMS}")
    print("Tip: set SEED=123 for deterministic output.")


if __name__ == "__main__":
    main()
