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
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../scripts"))
from scraper_common import canonical_brands, map_category, normalize_variant, now_iso, stamped_path, write_csv  # noqa: E402
from enrich import enrich, write_usage  # noqa: E402

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

def fetch_page(page: int, client: httpx.Client, retries: int = 3) -> tuple[list[dict], int]:
    """Returns (products_list, total_count). Retries on transient errors."""
    last_exc: Exception = Exception("no attempts made")
    for attempt in range(retries):
        try:
            params = {"page": page, "_routes": "routes/_layout.menu"}
            resp = client.get(API_URL, params=params, headers=API_HEADERS)
            resp.raise_for_status()
            arr  = resp.json()
            data = parse_response(arr)
            route_data = data.get("routes/_layout.menu", {}).get("data", {})
            return route_data.get("products") or [], int(route_data.get("total") or 0)
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"page {page} failed after {retries} attempts: {last_exc}") from last_exc

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
    raw_option = str(p.get("option") or p.get("size") or "").strip()
    thc_raw    = str(p.get("thc") or "").strip()
    thc_unit   = str(p.get("thcUnit") or "").strip().lower()
    raw_cat    = str(p.get("category") or "").strip()

    # For edibles where the option is a per-piece value rather than total package
    # THC, compute total from per-piece × pack count from the name.
    #
    # Case 1: option is a gram weight → option is physical weight, not potency
    #   "Galactic Guava | Live Rosin | 10pk": option=1g, thc=10mg → 100mg
    # Case 2: option is mg-per-piece (option_value == thc_value, thcUnit==mg)
    #   "Juicy Mango | Live Rosin | 10pk": option=10mg, thc=10mg → 100mg
    #   Distinguisher: if option_mg != thc (e.g. Camino option=100mg, thc=5mg)
    #   the option is already showing total package THC — leave it alone.
    if "edible" in map_category(raw_cat) and thc_raw and thc_unit in ("mg", "mg/g"):
        gram_m   = re.match(r'^\d+(?:\.\d+)?g$', raw_option)
        option_m = re.match(r'^(\d+(?:\.\d+)?)mg$', raw_option, re.I)
        try:
            per_piece = float(thc_raw)
            is_gram_option    = bool(gram_m)
            is_perpiece_mg    = bool(option_m) and abs(float(option_m.group(1)) - per_piece) < 0.01
            if is_gram_option or is_perpiece_mg:
                pack_m = re.search(r'\b(\d+)\s*pk\b', str(p.get("name") or ""), re.I)
                count  = int(pack_m.group(1)) if pack_m else 1
                raw_option = f"{round(per_piece * count):g}mg"
        except (ValueError, TypeError):
            pass

    variant = normalize_variant(raw_option)
    if not variant and p.get("grams"):
        variant = f"{p['grams']}g"

    # category (raw_cat already computed above for variant logic)
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
    # p["id"] is the platform's product id, not a batch — batch_id is reserved
    # for real batch/lot IDs (METRC lookups), so it stays empty here.
    batch_id = ""

    image_url = str(
        p.get("image") or p.get("imageUrl") or p.get("image_url") or
        p.get("thumbnail") or p.get("photo") or ""
    ).strip()

    return {
        "dispensary_slug": DISPENSARY_SLUG,
        "sku":             sku,
        "batch_id":        batch_id,
        "name":            str(p.get("name") or "").strip(),
        "brand":           str(p.get("brand") or "").strip(),
        "category":        category,
        "raw_category":    str(raw_cat or "").strip(),
        "variant":         variant,
        "price_cents":     price_cents,
        "thc_percent":     thc,
        "cbd_percent":     cbd,
        "classification":  str(p.get("classification") or "").strip().lower(),
        "in_stock":        in_stock,
        "product_url":     f"{BASE_URL}/products/{sku}/" if sku else "",
        "image_url":       image_url,
        "scraped_at":      scraped_at,
        "description":     " ".join(str(p.get("product_description") or "").split()),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape The Travel Agency menu")
    parser.add_argument("--pages", type=int, default=0,
                        help="Max pages to fetch (0 = all, default)")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--parallel",  action="store_true", help="Fetch pages 2..N concurrently")
    parser.add_argument("--no-enrich", action="store_true", help="Skip Haiku enrichment")
    parser.add_argument("--model", default="haiku", help="Enrichment model id (see MODELS in scripts/enrich.py)")
    args = parser.parse_args()
    args.output = args.output or stamped_path(OUTPUT_FILE)

    scraped_at = now_iso()
    all_rows:  list[dict] = []
    seen_skus: set[str]   = set()

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        # Page 1 — always fetch first to learn total
        print("  Page 1 ...", end=" ", flush=True)
        try:
            products_1, total = fetch_page(1, client)
        except httpx.HTTPError as exc:
            print(f"\n[!] HTTP error on page 1: {exc}", file=sys.stderr)
            products_1, total = [], 0

        total_pages = math.ceil(total / PAGE_SIZE) if total else 1
        print(f"({total} total products, {total_pages} pages)")

        rows_1 = [normalise(p, scraped_at) for p in products_1]
        new_1  = [r for r in rows_1 if r["sku"] not in seen_skus]
        seen_skus.update(r["sku"] for r in new_1 if r["sku"])
        all_rows.extend(new_1)

        max_page  = min(args.pages, total_pages) if args.pages else total_pages
        remaining = list(range(2, max_page + 1))

        if remaining and args.parallel:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            pages_data: dict[int, list[dict]] = {}
            with ThreadPoolExecutor(max_workers=min(len(remaining), 8)) as executor:
                futures = {executor.submit(fetch_page, p, client): p for p in remaining}
                for future in as_completed(futures):
                    pg = futures[future]
                    prods, _ = future.result()  # raises → exits executor, fails scrape
                    pages_data[pg] = prods
                    print(f"  Page {pg}/{total_pages} done ({len(prods)} products)")
            for pg in sorted(pages_data):
                rows = [normalise(p, scraped_at) for p in pages_data[pg]]
                new  = [r for r in rows if r["sku"] not in seen_skus]
                seen_skus.update(r["sku"] for r in new if r["sku"])
                all_rows.extend(new)
        else:
            for page in remaining:
                time.sleep(DELAY_SECS)
                print(f"  Page {page}/{total_pages} ...", end=" ", flush=True)
                try:
                    products, _ = fetch_page(page, client)
                except httpx.HTTPError as exc:
                    print(f"\n[!] HTTP error on page {page}: {exc}", file=sys.stderr)
                    break
                if not products:
                    print("empty — done.")
                    break
                rows = [normalise(p, scraped_at) for p in products]
                new  = [r for r in rows if r["sku"] not in seen_skus]
                seen_skus.update(r["sku"] for r in new if r["sku"])
                all_rows.extend(new)
                print(f"got {len(products)}, running total {len(all_rows)}")
                if len(products) < PAGE_SIZE:
                    print("  Last page (partial).")
                    break

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

    if not args.no_enrich:
        print("\nEnriching listings (subtype + strain) ...")
    usage = enrich(all_rows, no_enrich=args.no_enrich, model=args.model)
    write_usage(usage, args.output)

    n = write_csv(all_rows, args.output)
    print(f"\n✓  Wrote {n} rows → {args.output}")

    print("\nDB import notes:")
    print("  1. Ensure dispensary exists:")
    print(f"       INSERT INTO dispensaries (name, slug) VALUES ('The Travel Agency NY', '{DISPENSARY_SLUG}')")
    print("       ON CONFLICT (slug) DO NOTHING;")
    print("  2. Upsert products by (name, brand), then insert listings with matched product_id + dispensary_id")


if __name__ == "__main__":
    main()
