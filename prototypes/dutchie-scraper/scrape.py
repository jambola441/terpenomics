#!/usr/bin/env python3
"""
scrape.py — Dutchie / Flowhub menu scraper

Extracts products from the __remixContext embedded in the HTML — no API key needed.
Supports two Dutchie platform variants, both Remix-based:

  Dutchie Plus (custom shop.* domains, e.g. shop.coneyislandcannabis.nyc)
    • Route key: "routes/location.$retailerLocation.shop"
    • Products: resultData.menu.products
    • Pagination: ?offset=N  (20 per page)
    • Prices: dollars → ×100 for cents

  Flowhub eCommerce (dispensary.shop or flowhub custom domains)
    • Route key: "/:store?/:medrec/search"
    • Products: products.products
    • Pagination: ?page=N  (page 1 = offset 0)
    • Prices: already in cents

Usage
-----
  # Single store (auto-detect platform from URL):
  python scrape.py --url https://shop.coneyislandcannabis.nyc/location/coney-island-cannabis/shop \\
                   --dispensary-slug coney-island-cannabis \\
                   --name "Coney Island Cannabis"

  # Batch all stores in stores.json:
  python scrape.py --all [--out-dir ./]

WP-embed stores (dtche iframe pattern) cannot be scraped without a headless browser;
the scraper will print a skip message for these.
"""

import argparse
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../scripts"))
from scraper_common import apply_brand_aliases, canonical_brands, map_category, normalize_variant, now_iso, stamped_path, write_csv  # noqa: E402
from enrich import enrich, write_usage  # noqa: E402

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DELAY_SECS = 1.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
}

HERE        = os.path.dirname(os.path.abspath(__file__))
ROOT        = os.path.abspath(os.path.join(HERE, "../.."))
STORES_JSON = os.path.join(ROOT, "dispensaries.json")

# ---------------------------------------------------------------------------
# Platform detection + HTML extraction
# ---------------------------------------------------------------------------

def _extract_remix_context(html: str) -> dict | None:
    m = re.search(r'window\.__remixContext\s*=\s*', html)
    if not m:
        return None
    start = m.end()
    text = html[start:html.find('</script>', start)].rstrip('; \t\n')
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def detect_platform(html: str) -> str:
    """
    Returns one of:
      "dutchie_plus"   – Dutchie Plus Remix (shop.* custom domains)
      "flowhub"        – Flowhub eCommerce Remix (dispensary.shop)
      "wp_embed"       – WP with dtche iframe (not scrapable here)
      "unknown"
    """
    if re.search(r'dutchie\.com/api/v2/embedded-menu', html):
        return "wp_embed"
    ctx = _extract_remix_context(html)
    if not ctx:
        return "unknown"
    routes = list(ctx.get("state", {}).get("loaderData", {}).keys())
    if any("location" in r for r in routes):
        return "dutchie_plus"
    if any("medrec" in r for r in routes):
        return "flowhub"
    return "unknown"


# ---------------------------------------------------------------------------
# Dutchie Plus extraction
# ---------------------------------------------------------------------------

def _dp_products(html: str) -> tuple[list[dict], int]:
    ctx = _extract_remix_context(html)
    if not ctx:
        return [], 0
    for k, v in ctx["state"]["loaderData"].items():
        if "location" in k and isinstance(v, dict) and "resultData" in v:
            menu = v["resultData"].get("menu", {})
            return menu.get("products", []), menu.get("productsCount", 0)
    return [], 0


def normalise_dp(p: dict, dispensary_slug: str, scraped_at: str) -> list[dict]:
    """Dutchie Plus — one row per variant tier."""
    name     = str(p.get("name") or "").strip()
    brand    = str((p.get("brand") or {}).get("name") or "").strip()
    cat      = map_category(str(p.get("category") or "").strip())
    desc     = str(p.get("description") or "").strip()
    strain   = str(p.get("strainType") or "").strip().lower()
    thc      = str((p.get("potencyThc") or {}).get("formatted") or "").strip()
    cbd      = str((p.get("potencyCbd") or {}).get("formatted") or "").strip()
    sku      = str(p.get("id") or "").strip()
    images   = p.get("images") or []
    image    = str(images[0].get("url") or "") if images else ""

    variants = p.get("variants") or [{}]
    rows = []
    for v in variants:
        price_raw = v.get("priceRec") or v.get("priceMed")
        price_cents = int(round(float(price_raw) * 100)) if price_raw is not None else ""
        option  = str(v.get("option") or "").strip()
        variant = normalize_variant(option)
        rows.append({
            "dispensary_slug": dispensary_slug,
            "sku":             sku,
            "batch_id":        str(v.get("id") or "").strip(),
            "name":            name,
            "brand":           brand,
            "category":        cat,
            "variant":         variant,
            "price_cents":     price_cents,
            "thc_percent":     thc,
            "cbd_percent":     cbd,
            "classification":  strain,
            "in_stock":        "TRUE",
            "product_url":     "",
            "image_url":       image,
            "scraped_at":      scraped_at,
            "description":     desc,
        })
    return rows


def scrape_dutchie_plus(client: httpx.Client, url: str, dispensary_slug: str,
                        dispensary_name: str, out_path: str, parallel: bool = False,
                        no_enrich: bool = False, passes: int = 50, model: str = "haiku") -> int:
    scraped_at = now_iso()
    collected: dict[str, list[dict]] = {}  # product_id → normalised rows

    def _fetch_dp_offset(offset: int, retries: int = 3) -> list[dict]:
        last_exc: Exception = Exception("no attempts made")
        for attempt in range(retries):
            try:
                page_url = url if offset == 0 else f"{url}?offset={offset}"
                r = client.get(page_url, headers=HEADERS)
                r.raise_for_status()
                return _dp_products(r.text)[0]
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"offset {offset} failed after {retries} attempts: {last_exc}") from last_exc

    # Pass 1 offset 0 — learn total
    resp = client.get(url, headers=HEADERS)
    resp.raise_for_status()
    products_0, total = _dp_products(resp.text)
    print(f"  Total products: {total}  Passes: up to {passes}")

    def _run_pass(pass_num: int, first_page: list[dict] | None = None) -> int:
        new_this_pass = 0
        pages: dict[int, list[dict]] = {0: first_page or _fetch_dp_offset(0)}
        _, total_now = _dp_products(client.get(url, headers=HEADERS).text) if first_page is None else (None, total)
        page_size = len(pages[0]) or 20
        remaining_offsets = list(range(page_size, total, 20))

        if parallel and remaining_offsets:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=min(len(remaining_offsets), 6)) as executor:
                futures = {executor.submit(_fetch_dp_offset, off): off for off in remaining_offsets}
                for future in as_completed(futures):
                    off = futures[future]
                    pages[off] = future.result()
                    print(f"  [pass {pass_num}] offset={off:4d}  fetched {len(pages[off])} products")
        else:
            for off in remaining_offsets:
                time.sleep(DELAY_SECS)
                pages[off] = _fetch_dp_offset(off)
                print(f"  [pass {pass_num}] offset={off:4d}  fetched {len(pages[off])} products")

        for off in sorted(pages):
            for p in pages[off]:
                pid = str(p.get("id") or "")
                if pid and pid not in collected:
                    collected[pid] = normalise_dp(p, dispensary_slug, scraped_at)
                    new_this_pass += 1
        return new_this_pass

    new = _run_pass(1, first_page=products_0)
    print(f"  pass 1: {new} new  {len(collected)}/{total}")

    for i in range(2, passes + 1):
        if len(collected) >= total:
            print(f"  collected all {total} products after {i - 1} passes")
            break
        new = _run_pass(i)
        print(f"  pass {i}: {new} new  {len(collected)}/{total}")

    all_rows = [row for rows in collected.values() for row in rows]
    return _finish(all_rows, out_path, no_enrich=no_enrich, model=model)


# ---------------------------------------------------------------------------
# Flowhub extraction
# ---------------------------------------------------------------------------

def _fh_products(html: str) -> tuple[list[dict], int]:
    ctx = _extract_remix_context(html)
    if not ctx:
        return [], 0
    for k, v in ctx["state"]["loaderData"].items():
        if "medrec" in k and isinstance(v, dict) and "products" in v:
            blob = v["products"]
            if isinstance(blob, dict):
                return blob.get("products", []), blob.get("total", 0)
    return [], 0


_UOM_MAP = {
    "FluidOunces": "fl oz", "Grams": "g", "Milligrams": "mg",
    "Each": "", "Pounds": "lb",
}


def normalise_fh(p: dict, dispensary_slug: str, scraped_at: str) -> dict:
    """Flowhub — one row per product (single price point)."""
    name   = str(p.get("name") or "").strip()
    brand  = str(p.get("brand") or "").strip()
    cat    = map_category(str(p.get("category") or p.get("type") or "").strip())
    desc   = " ".join(str(p.get("description") or "").split())
    strain = str(p.get("species") or "").strip().lower()
    image  = str(p.get("image_url") or "").strip()
    sku    = str((p.get("sku") or [""])[0] if isinstance(p.get("sku"), list) else p.get("sku") or "").strip()

    # THC/CBD from potencies array
    thc = cbd = ""
    for pot in (p.get("potencies") or []):
        pname = str(pot.get("name") or "").lower()
        val   = str(pot.get("value") or "").strip()
        if "thc" in pname and "thc-a" not in pname and not thc:
            thc = val
        elif "cbd" in pname and not cbd:
            cbd = val

    # Variant
    wv    = str(p.get("weight_volume") or "").strip()
    uom   = _UOM_MAP.get(str(p.get("weight_volume_uom") or ""), "")
    variant = normalize_variant(f"{wv}{uom}" if wv else "")

    # Price is already in cents
    price_cents = p.get("pre_tax_price") or p.get("post_tax_price") or ""

    return {
        "dispensary_slug": dispensary_slug,
        "sku":             sku,
        "batch_id":        str(p.get("variant_id") or "").strip(),
        "name":            name,
        "brand":           brand,
        "category":        cat,
        "variant":         variant,
        "price_cents":     price_cents,
        "thc_percent":     thc,
        "cbd_percent":     cbd,
        "classification":  strain,
        "in_stock":        "TRUE" if (p.get("quantity") or 0) > 0 else "FALSE",
        "product_url":     "",
        "image_url":       image,
        "scraped_at":      scraped_at,
        "description":     desc,
    }


def scrape_flowhub(client: httpx.Client, url: str, dispensary_slug: str,
                   dispensary_name: str, out_path: str, parallel: bool = False,
                   no_enrich: bool = False, passes: int = 1, model: str = "haiku") -> int:
    scraped_at = now_iso()
    collected: dict[str, dict] = {}  # variant_id → normalised row

    def _fetch_fh_page(pg: int, retries: int = 3) -> list[dict]:
        last_exc: Exception = Exception("no attempts made")
        for attempt in range(retries):
            try:
                page_url = url if pg == 1 else f"{url}?page={pg}"
                r = client.get(page_url, headers=HEADERS)
                r.raise_for_status()
                return _fh_products(r.text)[0]
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"page {pg} failed after {retries} attempts: {last_exc}") from last_exc

    # Page 1 of pass 1 tells us total; subsequent passes reuse it
    resp = client.get(url, headers=HEADERS)
    resp.raise_for_status()
    products_1, total = _fh_products(resp.text)
    total_pages = math.ceil(total / 20) if total else 1
    print(f"  Total products: {total}  Total pages: {total_pages}  Passes: {passes}")

    def _run_pass(pass_num: int, first_page_products: list[dict] | None = None) -> int:
        new_this_pass = 0
        pages_products: dict[int, list[dict]] = {1: first_page_products or _fetch_fh_page(1)}

        if parallel and total_pages > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=min(total_pages - 1, 6)) as executor:
                futures = {executor.submit(_fetch_fh_page, pg): pg for pg in range(2, total_pages + 1)}
                for future in as_completed(futures):
                    pg = futures[future]
                    pages_products[pg] = future.result()
                    print(f"  [pass {pass_num}] page={pg:3d}  fetched {len(pages_products[pg])} products")
        else:
            for pg in range(2, total_pages + 1):
                time.sleep(DELAY_SECS)
                pages_products[pg] = _fetch_fh_page(pg)
                print(f"  [pass {pass_num}] page={pg:3d}  fetched {len(pages_products[pg])} products")

        for pg in sorted(pages_products):
            for p in pages_products[pg]:
                pid = str(p.get("variant_id") or p.get("product_id") or "")
                if pid and pid not in collected:
                    collected[pid] = normalise_fh(p, dispensary_slug, scraped_at)
                    new_this_pass += 1
        return new_this_pass

    new = _run_pass(1, first_page_products=products_1)
    print(f"  pass 1: {new} new  {len(collected)}/{total}")

    for i in range(2, passes + 1):
        if len(collected) >= total:
            print(f"  collected all {total} products after {i - 1} passes")
            break
        new = _run_pass(i)
        print(f"  pass {i}: {new} new  {len(collected)}/{total}")

    return _finish(list(collected.values()), out_path, no_enrich=no_enrich, model=model)


# ---------------------------------------------------------------------------
# Shared finishing step
# ---------------------------------------------------------------------------

def _finish(all_rows: list[dict], out_path: str, no_enrich: bool = False, model: str = "haiku") -> int:
    if not all_rows:
        return 0
    raw_brands  = {r["brand"] for r in all_rows if r["brand"]}
    brand_canon = canonical_brands(raw_brands)
    for r in all_rows:
        if r["brand"]:
            r["brand"] = brand_canon.get(r["brand"], r["brand"])
    apply_brand_aliases(all_rows)
    if not no_enrich:
        print("  Enriching (subtype + strain) ...")
    usage = enrich(all_rows, no_enrich=no_enrich, model=model)
    write_usage(usage, out_path)
    write_csv(all_rows, out_path)
    print(f"  Wrote {len(all_rows)} rows → {out_path}")
    return len(all_rows)


# ---------------------------------------------------------------------------
# Entry point for a single store
# ---------------------------------------------------------------------------

def scrape_store(
    client: httpx.Client,
    menu_url: str,
    dispensary_slug: str,
    dispensary_name: str,
    out_path: str,
    platform: str | None = None,
    parallel: bool = False,
    no_enrich: bool = False,
    passes: int = 1,
    model: str = "haiku",
) -> int:
    print(f"\n{'='*60}")
    print(f"Scraping: {dispensary_name}")
    print(f"  URL:              {menu_url}")

    if not platform:
        print("  Detecting platform ...")
        resp = client.get(menu_url, headers=HEADERS)
        platform = detect_platform(resp.text)

    print(f"  Platform:         {platform}")

    if platform == "wp_embed":
        print("  [SKIP] WP Dutchie embed — requires headless browser to scrape")
        return 0
    if platform == "unknown":
        print("  [SKIP] Unknown platform — inspect page manually")
        return 0
    if platform == "dutchie_plus":
        return scrape_dutchie_plus(client, menu_url, dispensary_slug, dispensary_name, out_path, parallel=parallel, no_enrich=no_enrich, passes=passes, model=model)
    if platform == "flowhub":
        return scrape_flowhub(client, menu_url, dispensary_slug, dispensary_name, out_path, parallel=parallel, no_enrich=no_enrich, passes=passes, model=model)

    print(f"  [SKIP] Unsupported platform: {platform}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Scrape Dutchie / Flowhub-powered dispensary menus")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--url",  help="Menu URL to scrape (auto-detects platform)")
    mode.add_argument("--all",  action="store_true", help="Scrape all stores in stores.json")

    p.add_argument("--dispensary-slug", default=None)
    p.add_argument("--name",    default="", help="Human-readable dispensary name")
    p.add_argument("--platform", default=None, choices=["dutchie_plus", "flowhub"],
                   help="Force platform (skip detection)")
    p.add_argument("--out",     default=None, help="Output CSV path (single-store mode)")
    p.add_argument("--out-dir", default=os.path.join(ROOT, "data/scrapes"),
                   help="Output directory for --all mode")
    p.add_argument("--parallel",  action="store_true", help="Fetch pages concurrently")
    p.add_argument("--no-enrich", action="store_true", help="Skip Haiku enrichment")
    p.add_argument("--model",     default="haiku", help="Enrichment model id (see MODELS in scripts/enrich.py)")
    p.add_argument("--passes",    type=int, default=50, help="Flowhub: max page sweeps until all reported products collected (default 50)")
    return p.parse_args()


def load_stores() -> list[dict]:
    with open(STORES_JSON) as f:
        all_stores = json.load(f)
    stores = [s for s in all_stores if s.get("platform") in ("flowhub", "dutchie_plus")]
    for s in stores:
        s.setdefault("dispensary_slug", s.get("slug", ""))
    return stores


def main():
    args = parse_args()

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        if args.all:
            stores     = load_stores()
            total_rows = 0
            skipped    = 0

            for s in stores:
                menu_url = s.get("menu_url")
                if not menu_url:
                    print(f"\n[!] No menu_url for {s['name']} — skipping")
                    skipped += 1
                    continue

                out_path = os.path.join(args.out_dir, stamped_path(f"{s['dispensary_slug']}_listings.csv"))
                n = scrape_store(
                    client,
                    menu_url,
                    s["dispensary_slug"],
                    s["name"],
                    out_path,
                    s.get("platform"),
                    parallel=args.parallel,
                    no_enrich=args.no_enrich,
                    passes=args.passes,
                    model=args.model,
                )
                total_rows += n
                if n == 0:
                    skipped += 1
                else:
                    time.sleep(DELAY_SECS)

            print(f"\n{'='*60}")
            print(f"Done. Total rows: {total_rows}  Skipped/failed: {skipped}")

        else:
            if not args.url:
                print("Provide --url or --all", file=sys.stderr)
                sys.exit(1)

            disp_slug = args.dispensary_slug or re.sub(r'[^a-z0-9]+', '-', args.name.lower()).strip('-')
            out_path  = args.out or stamped_path(os.path.join(HERE, f"{disp_slug}_listings.csv"))
            scrape_store(
                client,
                args.url,
                disp_slug,
                args.name or args.url,
                out_path,
                args.platform,
                parallel=args.parallel,
                no_enrich=args.no_enrich,
                passes=args.passes,
                model=args.model,
            )


if __name__ == "__main__":
    main()
