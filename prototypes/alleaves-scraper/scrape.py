"""
scrape.py — Alleaves POS scraper

Two-pass approach:
  1. /api/inventory/item/search  — full product catalog (stable id_item, descriptions, images)
  2. /api/inventory/search        — current inventory to determine in_stock per id_item

Usage:
    python prototypes/alleaves-scraper/scrape.py \\
        --tenant brooklynorganicbuds \\
        --out prototypes/alleaves-scraper/brooklynorganicbuds_listings.csv

    Credentials via env vars (preferred) or flags:
        ALLEAVES_USER / ALLEAVES_PASS
        --username / --password

Output columns (identical to travel_agency_listings.csv):
    dispensary_slug, sku, product_uuid, name, brand, category, variant,
    price_cents, thc_percent, cbd_percent, classification, in_stock,
    product_url, scraped_at
"""

import argparse
import os
import sys
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../scripts"))
from scraper_common import map_category, now_iso, store_slug, write_csv  # noqa: E402

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(1)


BASE_URL = "https://app.alleaves.com"
PAGE_SIZE = 100

_API_HEADERS = {
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
    "accept": "application/json",
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(client: httpx.Client, username: str, password: str) -> None:
    resp = client.post(
        "/api/account/login",
        json={"username": username, "password": password},
    )
    resp.raise_for_status()
    data = resp.json()
    if "redirect_url" not in data:
        raise RuntimeError(f"Login failed: {data}")


# ---------------------------------------------------------------------------
# Pass 1 — item catalog
# ---------------------------------------------------------------------------

def _item_params(skip: int) -> str:
    page = skip // PAGE_SIZE + 1
    return urlencode({
        "take": PAGE_SIZE,
        "skip": skip,
        "page": page,
        "pageSize": PAGE_SIZE,
    })


def fetch_all_items(client: httpx.Client) -> list[dict]:
    """Return all non-deleted catalog items, deduplicated by id_item."""
    records: list[dict] = []
    seen: set[str] = set()
    skip = 0
    total = None

    while True:
        resp = client.post(
            "/api/inventory/item/search",
            content=_item_params(skip),
            headers=_API_HEADERS,
        )
        resp.raise_for_status()
        page: list[dict] = resp.json()
        if not page:
            break

        if total is None:
            total = page[0].get("total_rows", 0)
            print(f"  Total catalog items: {total}")

        for r in page:
            key = str(r.get("id_item", ""))
            if key and key not in seen:
                seen.add(key)
                records.append(r)

        skip += len(page)
        if len(page) < PAGE_SIZE or (total and skip >= total):
            break

        time.sleep(0.3)

    return records


# ---------------------------------------------------------------------------
# Pass 2 — in-stock ids from inventory
# ---------------------------------------------------------------------------

def _inventory_params(skip: int) -> str:
    page = skip // PAGE_SIZE + 1
    params = {
        "take": PAGE_SIZE,
        "skip": skip,
        "page": page,
        "pageSize": PAGE_SIZE,
        "filter[logic]": "and",
        "filter[filters][0][field]": "status",
        "filter[filters][0][value][]": "open",
        "filter[filters][0][operator]": "eq",
        "filter[filters][1][field]": "has_inventory",
        "filter[filters][1][value]": "true",
        "filter[filters][1][operator]": "eq",
        "filter[filters][2][filters][0][field]": "area_type",
        "filter[filters][2][filters][0][value]": "scrap",
        "filter[filters][2][filters][0][operator]": "neq",
        "filter[filters][2][filters][1][field]": "area_type",
        "filter[filters][2][filters][1][value]": "true",
        "filter[filters][2][filters][1][operator]": "isnull",
        "filter[filters][2][logic]": "or",
        "id_location": "",
    }
    return urlencode(params)


def fetch_in_stock_ids(client: httpx.Client) -> set[str]:
    """Return the set of id_item strings that currently have available > 0."""
    in_stock: set[str] = set()
    skip = 0
    total = None

    while True:
        resp = client.post(
            "/api/inventory/search",
            content=_inventory_params(skip),
            headers=_API_HEADERS,
        )
        resp.raise_for_status()
        page: list[dict] = resp.json()
        if not page:
            break

        if total is None:
            total = page[0].get("total_rows", 0)
            print(f"  Total inventory records: {total}")

        for r in page:
            if (r.get("available") or 0) > 0:
                item_id = str(r.get("id_item", ""))
                if item_id:
                    in_stock.add(item_id)

        skip += len(page)
        if len(page) < PAGE_SIZE or (total and skip >= total):
            break

        time.sleep(0.3)

    return in_stock


# ---------------------------------------------------------------------------
# Normalise
# ---------------------------------------------------------------------------

def _product_url(store_url: str, brand: str, name: str) -> str:
    if not store_url:
        return ""
    brand_part = store_slug(brand.strip())
    name_part = store_slug(name)
    slug = f"{brand_part}-{name_part}" if brand_part else name_part
    return f"{store_url}/{slug}"


def derive_variant(weight_useable, uom_weight_useable: str | None) -> str:
    if weight_useable is None:
        return ""
    uom = (uom_weight_useable or "").lower()
    if uom == "grams":
        return f"{float(weight_useable):g}g"
    elif uom == "milligrams":
        mg = float(weight_useable)
        if mg >= 1000:
            return f"{mg / 1000:g}g"
        return f"{int(mg)}mg"
    return ""


def map_classification(strain_type: str | None) -> str:
    if not strain_type:
        return ""
    return strain_type.lower()  # "Hybrid" → "hybrid", "Indica" → "indica", etc.


def normalise(
    r: dict,
    in_stock_ids: set[str],
    dispensary_slug: str,
    scraped_at: str,
    store_url: str = "",
) -> dict | None:
    item_name = (r.get("item") or "").strip()
    if not item_name:
        return None

    if "SAMPLES" in item_name.upper():
        return None

    item_id = str(r.get("id_item", ""))

    price_raw = r.get("price_retail_adult_use") or 0
    price_cents = int(round(float(price_raw) * 100))

    thc = r.get("strain_percent_thc")
    cbd = r.get("strain_percent_cbd")

    return {
        "dispensary_slug": dispensary_slug,
        "sku":             item_id,
        "product_uuid":    item_id,
        "name":            item_name,
        "brand":           (r.get("brand") or "").strip(),
        "category":        map_category(r.get("category")),
        "variant":         derive_variant(r.get("weight_useable"), r.get("uom_weight_useable")),
        "price_cents":     price_cents,
        "thc_percent":     thc if thc else "",
        "cbd_percent":     cbd if cbd else "",
        "classification":  map_classification(r.get("strain_type")),
        "in_stock":        "TRUE" if item_id in in_stock_ids else "FALSE",
        "product_url":     _product_url(store_url, r.get("brand") or "", item_name),
        "scraped_at":      scraped_at,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Scrape Alleaves POS catalog to CSV")
    p.add_argument("--tenant", default="brooklynorganicbuds")
    p.add_argument("--out", default=None)
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--store-url", default="",
                   help="Storefront base URL for product links, e.g. https://brooklynorganicbuds.com/store/product")
    return p.parse_args()


def main():
    args = parse_args()

    username = args.username or os.environ.get("ALLEAVES_USER")
    password = args.password or os.environ.get("ALLEAVES_PASS")
    if not username or not password:
        print("Error: provide --username/--password or set ALLEAVES_USER/ALLEAVES_PASS",
              file=sys.stderr)
        sys.exit(1)

    out_path = args.out or os.path.join(
        os.path.dirname(__file__), f"{args.tenant}_listings.csv"
    )
    dispensary_slug = args.tenant
    scraped_at = now_iso()

    print(f"Logging in as {username} ...")
    with httpx.Client(base_url=BASE_URL, timeout=30, follow_redirects=True) as client:
        login(client, username, password)
        print("  Logged in.")

        print("Pass 1 — fetching item catalog ...")
        items = fetch_all_items(client)
        print(f"  {len(items)} unique items.")

        print("Pass 2 — fetching inventory for in-stock status ...")
        in_stock_ids = fetch_in_stock_ids(client)
        print(f"  {len(in_stock_ids)} items currently in stock.")

    rows = []
    skipped = 0
    for r in items:
        row = normalise(r, in_stock_ids, dispensary_slug, scraped_at, args.store_url)
        if row is None:
            skipped += 1
        else:
            rows.append(row)

    write_csv(rows, out_path)
    print(f"\nWrote {len(rows)} rows to {out_path}  ({skipped} skipped)")


if __name__ == "__main__":
    main()
