#!/usr/bin/env python3
"""
Scraper for The Travel Agency (thetravelagency.co) menu.

The Remix .data endpoint returns a turbo-stream flat array:
  - Objects are encoded as {_N: M} dicts meaning "key=arr[N], value=arr[M]"
  - Arrays contain integer indices into the flat array
  - Primitives are stored as-is

We decode the whole structure, walk to products[], and normalise to CSV.

Endpoint:
  GET /menu.data?page=N&_routes=routes%2F_layout.menu
  (limit= param is ignored server-side; page size is fixed at 20)
  Total items is in the `total` field — we paginate until exhausted.

Output CSV columns
------------------
  dispensary_slug  · sku  · name  · brand  · category  · variant
  price_cents  · thc_percent  · cbd_percent  · classification
  in_stock  · product_url  · scraped_at

Usage
-----
  python scrape.py                  # full scrape (~33 pages, ~651 products)
  python scrape.py --pages 2        # first 40 rows (quick test)
  python scrape.py -o out.csv       # custom output path
"""

import argparse
import math
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../scripts"))
from scraper_common import canonical_brands, map_category, normalize_variant, now_iso, strip_noinfo, write_csv  # noqa: E402

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL        = "https://www.thetravelagency.co"
API_URL         = f"{BASE_URL}/menu.data"
DISPENSARY_SLUG = "travel-agency-ny"
OUTPUT_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "travel_agency_listings.csv")
PAGE_SIZE       = 20   # server-side fixed; limit= param is ignored
DELAY_SECS      = 1.0  # polite delay between requests

API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
    "Referer": f"{BASE_URL}/menu/",
}


# ---------------------------------------------------------------------------
# Turbo-stream decoder
# ---------------------------------------------------------------------------

def decode(arr: list, idx: int):
    """
    Recursively decode value at arr[idx] from the turbo-stream flat array.

    Rules:
      dict  {_N: M, ...}  →  object: key=arr[N], value=decode(arr, M)
      list  [i, j, ...]   →  array:  [decode(arr, i), decode(arr, j), ...]
      other               →  primitive, return as-is
    """
    val = arr[idx]

    if isinstance(val, dict):
        obj = {}
        for ref_key, val_idx in val.items():
            key_idx = int(ref_key[1:])   # "_8" → 8
            key = arr[key_idx]
            obj[key] = decode(arr, val_idx)
        return obj

    elif isinstance(val, list):
        return [decode(arr, i) for i in val]

    else:
        return val   # str, int, float, bool, None


def parse_response(arr: list) -> dict:
    """
    Decode the full turbo-stream array and return the loader data dict.
    Shape: {"routes/_layout.menu": {"data": {"products": [...], "total": N, ...}}}
    """
    return decode(arr, 0)

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_page(page: int, client: httpx.Client) -> tuple[list[dict], int]:
    """
    Returns (products_list, total_count).
    Raises httpx.HTTPError on non-200.
    """
    params = {
        "page":    page,
        "_routes": "routes/_layout.menu",
    }
    resp = client.get(API_URL, params=params, headers=API_HEADERS)
    resp.raise_for_status()

    arr = resp.json()
    data = parse_response(arr)

    route_data = data.get("routes/_layout.menu", {}).get("data", {})
    products   = route_data.get("products") or []
    total      = route_data.get("total") or 0

    return products, int(total)

# ---------------------------------------------------------------------------
# Normalise
# ---------------------------------------------------------------------------

def normalise(p: dict, scraped_at: str) -> dict:
    # price
    raw_price = p.get("price")
    try:
        price_cents = int(float(raw_price) * 100) if raw_price is not None else ""
    except (ValueError, TypeError):
        price_cents = ""

    # variant: prefer "option" (e.g. "2g") over grams fallback
    variant = normalize_variant(str(p.get("option") or p.get("size") or "").strip())
    if not variant and p.get("grams"):
        variant = f"{p['grams']}g"

    # category
    raw_cat  = str(p.get("category") or "").strip()
    category = map_category(raw_cat)

    # THC / CBD
    thc = str(p.get("thc") or "").strip()
    cbd = str(p.get("cbd") or "").strip()

    # stock
    stock_val = p.get("stock")
    if stock_val is None or stock_val == "":
        in_stock = "TRUE"
    elif isinstance(stock_val, bool):
        in_stock = "TRUE" if stock_val else "FALSE"
    elif isinstance(stock_val, (int, float)):
        in_stock = "TRUE" if stock_val > 0 else "FALSE"
    else:
        in_stock = "FALSE" if str(stock_val).lower() in ("0", "out_of_stock", "false") else "TRUE"

    sku      = str(p.get("slug") or p.get("sku") or "").strip()
    batch_id = str(p.get("id") or "").strip()

    return {
        "dispensary_slug": DISPENSARY_SLUG,
        "sku":             sku,
        "batch_id":        batch_id,
        "name":            strip_noinfo(str(p.get("name") or "").strip()),
        "name_raw":        str(p.get("name") or "").strip(),
        "brand":           str(p.get("brand") or "").strip(),
        "category":        category,
        "variant":         variant,
        "price_cents":     price_cents,
        "thc_percent":     thc,
        "cbd_percent":     cbd,
        "classification":  str(p.get("classification") or "").strip().lower(),
        "in_stock":        in_stock,
        "product_url":     f"{BASE_URL}/products/{sku}/" if sku else "",
        "scraped_at":      scraped_at,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape The Travel Agency menu")
    parser.add_argument("--pages", type=int, default=0,
                        help="Max pages to fetch (0 = all, default)")
    parser.add_argument("-o", "--output", default=OUTPUT_FILE)
    args = parser.parse_args()

    scraped_at = now_iso()
    all_rows:  list[dict] = []
    seen_skus: set[str]   = set()
    total_products = None

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        page = 1
        while True:
            print(f"  Page {page}", end="", flush=True)
            if total_products:
                total_pages = math.ceil(total_products / PAGE_SIZE)
                print(f"/{total_pages}", end="", flush=True)
            print(" ...", end=" ", flush=True)

            try:
                products, total = fetch_page(page, client)
            except httpx.HTTPError as exc:
                print(f"\n[!] HTTP error on page {page}: {exc}", file=sys.stderr)
                break

            if total_products is None and total:
                total_products = total
                print(f"({total} total products)  ", end="", flush=True)

            if not products:
                print("empty — done.")
                break

            rows = [normalise(p, scraped_at) for p in products]
            new  = [r for r in rows if r["sku"] not in seen_skus]
            seen_skus.update(r["sku"] for r in new if r["sku"])
            all_rows.extend(new)

            print(f"got {len(products)}, running total {len(all_rows)}")

            if args.pages and page >= args.pages:
                print(f"  Reached --pages {args.pages} limit.")
                break

            if total_products and len(all_rows) >= total_products:
                print("  All products collected.")
                break

            if len(products) < PAGE_SIZE:
                print("  Last page (partial).")
                break

            page += 1
            time.sleep(DELAY_SECS)

    raw_brands = {r["brand"] for r in all_rows if r["brand"]}
    brand_canon = canonical_brands(raw_brands)
    for r in all_rows:
        if r["brand"]:
            r["brand"] = brand_canon.get(r["brand"], r["brand"])

    if not all_rows:
        print(
            "\n[!] No products scraped.\n"
            "    Debug: curl -s '"
            f"{API_URL}?page=1&_routes=routes%%2F_layout.menu' | python3 -m json.tool | head -40",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\nTotal unique products scraped: {len(all_rows)}")
    print("\nSample row:")
    for k, v in all_rows[0].items():
        print(f"  {k:20s} {v}")

    n = write_csv(all_rows, args.output)
    print(f"\n✓  Wrote {n} rows → {args.output}")

    print("\nDB import notes:")
    print("  1. Ensure dispensary exists:")
    print(f"       INSERT INTO dispensaries (name, slug) VALUES ('The Travel Agency NY', '{DISPENSARY_SLUG}')")
    print("       ON CONFLICT (slug) DO NOTHING;")
    print("  2. Upsert products by (name, brand), then insert listings with matched product_id + dispensary_id")


if __name__ == "__main__":
    main()
