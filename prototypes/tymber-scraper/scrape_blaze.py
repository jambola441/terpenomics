#!/usr/bin/env python3
"""
scrape_blaze.py — Tymber/BLAZE ecom-api menu scraper

Scrapes any store with a `blaze_id` (UUID) in stores.json by calling
ecom-api.blaze.me/api/v1/products/.  No auth token needed — X-Store header
with the store UUID is sufficient for unauthenticated menu access.

Usage
-----
  # Batch all stores in stores.json:
  python scrape_blaze.py --all [--out-dir ./]

  # Single store:
  python scrape_blaze.py --blaze-id <uuid> --dispensary-slug <slug> --name <name>
"""

import argparse
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../scripts"))
from scraper_common import apply_brand_aliases, canonical_brands, map_category, normalize_variant, now_iso, write_csv  # noqa: E402
from enrich import enrich, write_usage  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DELAY_SECS   = 1.0
PAGE_SIZE     = 100
ECOM_BASE     = "https://ecom-api.blaze.me/api/v1/products/"

HERE        = os.path.dirname(os.path.abspath(__file__))
ROOT        = os.path.abspath(os.path.join(HERE, "../.."))
STORES_JSON = os.path.join(ROOT, "dispensaries.json")

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _build_included_map(included: list) -> dict:
    """Return {(type, id): attributes} for fast relationship lookup."""
    result = {}
    for item in included or []:
        result[(item.get("type"), item.get("id"))] = item.get("attributes") or {}
    return result


def _variant_for_tier(tier: dict, size_display: str | None) -> str:
    label = (tier.get("display_name") or "").strip()
    if label.lower() in ("1 each", "each", "1"):
        return normalize_variant(size_display or "")
    return normalize_variant(label)


def normalise_blaze(p: dict, included_map: dict, dispensary_slug: str, scraped_at: str) -> list[dict]:
    """Return one CSV row per price tier (unit_prices or weight_prices)."""
    attrs  = p.get("attributes") or {}
    rels   = p.get("relationships") or {}

    sku    = attrs.get("sku") or str(p.get("id") or "")
    name   = str(attrs.get("name") or "").strip()
    desc   = " ".join(str(attrs.get("description") or "").split())
    image  = str(attrs.get("main_image") or "").strip()
    url    = str(attrs.get("store_url") or "").strip()

    # classification
    flower_type = str(attrs.get("flower_type") or "").strip().lower()
    if flower_type in ("n/a", ""):
        flower_type = ""

    # strain
    strain = str(attrs.get("strain") or "").strip()

    # potency
    thc_obj = attrs.get("thc") or {}
    cbd_obj = attrs.get("cbd") or {}
    thc_pct = str(thc_obj.get("amount") or "").strip()
    cbd_pct = str(cbd_obj.get("amount") or "").strip()
    if thc_pct == "0.0" or thc_pct == "0":
        thc_pct = ""
    if cbd_pct == "0.0" or cbd_pct == "0":
        cbd_pct = ""

    in_stock = "TRUE" if attrs.get("in_stock") else "FALSE"

    # category via relationship
    cat_rel  = (rels.get("category") or {}).get("data") or {}
    cat_attrs = included_map.get(("product_categories", cat_rel.get("id"))) or {}
    cat_raw  = str(cat_attrs.get("name") or "").strip()
    category = map_category(cat_raw)

    # brand via relationship
    brand_rel  = (rels.get("brand") or {}).get("data") or {}
    brand_attrs = included_map.get(("product_brands", brand_rel.get("id"))) or {}
    brand = str(brand_attrs.get("name") or "").strip()

    size_obj   = attrs.get("size") or {}
    size_display = str(size_obj.get("display_text") or "").strip() or None

    # price tiers: prefer weight_prices if present, else unit_prices
    weight_prices = attrs.get("weight_prices") or []
    unit_prices   = attrs.get("unit_prices") or []
    tiers = weight_prices if weight_prices else unit_prices

    if not tiers:
        price_raw = (attrs.get("unit_price") or {}).get("amount")
        tiers = [{"display_name": size_display or "", "price": {"amount": price_raw}}]

    rows = []
    for i, tier in enumerate(tiers):
        price_raw   = (tier.get("price") or {}).get("amount")
        price_cents = int(price_raw) if price_raw is not None else ""
        variant     = _variant_for_tier(tier, size_display)
        batch_id    = f"{sku}-{i}" if len(tiers) > 1 else sku
        rows.append({
            "dispensary_slug": dispensary_slug,
            "sku":             sku,
            "batch_id":        batch_id,
            "name":            name,
            "brand":           brand,
            "category":        category,
            "variant":         variant,
            "price_cents":     price_cents,
            "thc_percent":     thc_pct,
            "cbd_percent":     cbd_pct,
            "classification":  flower_type,
            "in_stock":        in_stock,
            "product_url":     url,
            "image_url":       image,
            "scraped_at":      scraped_at,
            "description":     desc,
            "strain":          strain,
        })
    return rows


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def _fetch_blaze_offset(blaze_id: str, offset: int, retries: int = 3) -> tuple[list[dict], list[dict]]:
    """Fetch one page in an independent session (thread-safe). Returns (products, included)."""
    last_exc: Exception = Exception("no attempts made")
    for attempt in range(retries):
        try:
            s = requests.Session()
            s.headers.update({"Accept": "application/json"})
            resp = s.get(ECOM_BASE, headers={"X-Store": blaze_id},
                         params={"limit": PAGE_SIZE, "offset": offset}, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            return body.get("data") or [], body.get("included") or []
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"offset {offset} failed after {retries} attempts: {last_exc}") from last_exc


def scrape_store(blaze_id: str, dispensary_slug: str, dispensary_name: str, out_path: str, parallel: bool = False, no_enrich: bool = False) -> int:
    print(f"\n{'='*60}")
    print(f"Scraping: {dispensary_name}")
    print(f"  blaze_id: {blaze_id}")

    scraped_at    = now_iso()
    all_rows:  list[dict] = []
    seen_ids:  set        = set()

    # Offset 0 — always fetch first to learn total
    resp = SESSION.get(ECOM_BASE, headers={"X-Store": blaze_id},
                       params={"limit": PAGE_SIZE, "offset": 0}, timeout=30)
    resp.raise_for_status()
    body_0       = resp.json()
    products_0   = body_0.get("data") or []
    total        = (body_0.get("meta") or {}).get("total_count") or 0
    all_included = list(body_0.get("included") or [])

    print(f"  Total products: {total}")
    if not products_0:
        return 0

    remaining_offsets = list(range(PAGE_SIZE, total, PAGE_SIZE))

    if remaining_offsets and parallel:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        pages_data: dict[int, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=min(len(remaining_offsets), 6)) as executor:
            futures = {executor.submit(_fetch_blaze_offset, blaze_id, off): off for off in remaining_offsets}
            for future in as_completed(futures):
                off = futures[future]
                prods, inc = future.result()  # raises → exits executor, fails scrape
                pages_data[off] = prods
                all_included.extend(inc)
                print(f"  offset={off:4d}  fetched {len(prods)} products")
        # Unified brand/category map built from all pages' included resources
        inc_map      = _build_included_map(all_included)
        all_products = products_0 + [p for off in sorted(pages_data) for p in pages_data[off]]
    elif remaining_offsets:
        offset = PAGE_SIZE
        while offset < total:
            time.sleep(DELAY_SECS)
            prods, inc = _fetch_blaze_offset(blaze_id, offset)
            all_included.extend(inc)
            products_0 = products_0 + prods
            print(f"  offset={offset:4d}  page_size={len(prods):3d}")
            offset += len(prods) if prods else PAGE_SIZE
            if not prods:
                break
        inc_map      = _build_included_map(all_included)
        all_products = products_0
    else:
        inc_map      = _build_included_map(all_included)
        all_products = products_0

    new_count = 0
    for p in all_products:
        pid = p.get("id")
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        new_count += 1
        all_rows.extend(normalise_blaze(p, inc_map, dispensary_slug, scraped_at))
    print(f"  {len(seen_ids)} unique products ({new_count} rows normalised)")

    if not all_rows:
        print("  [WARN] No rows collected")
        return 0

    raw_brands  = {r["brand"] for r in all_rows if r["brand"]}
    brand_canon = canonical_brands(raw_brands)
    for r in all_rows:
        if r["brand"]:
            r["brand"] = brand_canon.get(r["brand"], r["brand"])
    apply_brand_aliases(all_rows)

    if not no_enrich:
        print("  Enriching (subtype + strain) ...")
    usage = enrich(all_rows, no_enrich=no_enrich)
    write_usage(usage, out_path)

    write_csv(all_rows, out_path)
    print(f"  Wrote {len(all_rows)} rows → {out_path}")
    return len(all_rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Scrape Tymber/BLAZE dispensary menus")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--all",      action="store_true",
                      help="Scrape all stores in stores.json")
    mode.add_argument("--blaze-id", default=None,
                      help="Store UUID from REACT_APP_TYMBER_ECOMMERCE_ID")
    p.add_argument("--dispensary-slug", default=None)
    p.add_argument("--name",    default="", help="Human-readable dispensary name")
    p.add_argument("--out",     default=None, help="Output CSV (single-store mode)")
    p.add_argument("--out-dir", default=os.path.join(ROOT, "data/scrapes"),
                      help="Output directory for --all mode")
    p.add_argument("--parallel",  action="store_true", help="Fetch pages concurrently")
    p.add_argument("--no-enrich", action="store_true", help="Skip Haiku enrichment")
    return p.parse_args()


def load_stores() -> list[dict]:
    with open(STORES_JSON) as f:
        all_stores = json.load(f)
    stores = [s for s in all_stores if s.get("platform") == "tymber"]
    for s in stores:
        s.setdefault("dispensary_slug", s.get("slug", ""))
    return stores


def main():
    args = parse_args()

    if args.all:
        stores     = load_stores()
        total_rows = 0
        skipped    = 0

        for s in stores:
            blaze_id = s.get("blaze_id")
            if not blaze_id:
                print(f"\n[SKIP] {s['name']} — no blaze_id")
                skipped += 1
                continue

            out_path = os.path.join(args.out_dir, f"{s['dispensary_slug']}_listings.csv")
            n = scrape_store(blaze_id, s["dispensary_slug"], s["name"], out_path, parallel=args.parallel, no_enrich=args.no_enrich)
            total_rows += n
            if n == 0:
                skipped += 1
            else:
                time.sleep(DELAY_SECS)

        print(f"\n{'='*60}")
        print(f"Done. Total rows: {total_rows}  Skipped/failed: {skipped}")

    else:
        if not args.blaze_id:
            print("Provide --blaze-id or --all", file=sys.stderr)
            sys.exit(1)

        disp_slug = (
            args.dispensary_slug
            or re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
            or args.blaze_id
        )
        out_path = args.out or os.path.join(HERE, f"{disp_slug}_listings.csv")
        scrape_store(args.blaze_id, disp_slug, args.name or args.blaze_id, out_path, parallel=args.parallel, no_enrich=args.no_enrich)


if __name__ == "__main__":
    main()
