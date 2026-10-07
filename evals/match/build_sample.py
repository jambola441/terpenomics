#!/usr/bin/env python3
"""
build_sample.py — Draws the matcher test set: 10 live listings from each of 30 brands
with catalogs (15 whose catalog comes from the brand's own site, 15 built from store
listings), spread over how the matcher last decided them (exact, jev, jev_review, none).
Writes cases/sample.json, unlabelled; labels are added by label_sample.py and spot-checked.

    DB_VIA_HTTP=1 python evals/match/build_sample.py
"""

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import catalog_store  # noqa: E402
import db_http  # noqa: E402

BRANDS = [  # brand site
    "Ayrloom", "Jaunty", "MFNY", "Grön", "Florist Farms", "Revert", "Off Hours", "Camino", "Wyld",
    "Dank By Definition", "Nanticoke", "Presidential", "Layup", "PUFF", "Heady Tree",
    # built from store listings
    "STIIIZY", "Ruby Farms", "Cannabals", "Rove", "Jetpacks", "Heavy Hitters", "Hashtag Honey", "PAX",
    "Fernway", "Runtz", "Find.", "Doobie Labs", "BLOOM", "Grassroots", "1906"]
PER_BRAND = 10
QUOTA = [("exact", 2), ("jev", 3), ("jev_review", 2), (None, 3)]   # None: no match recorded
SEED = 20261007


def main() -> None:
    catalogs = catalog_store.load_all("db")
    stores = {str(r["id"]): r["slug"] for r in db_http.select_all("dispensaries", "select=id,slug&order=id")}
    cols = ("id,dispensary_id,scraped_brand,scraped_name,scraped_category,subtype,variant,price_cents,description,url,"
            "catalog_entry_id,catalog_match_method,catalog_match_confidence")
    by_brand = defaultdict(list)
    keys = {catalog_store.brand_key(b): b for b in BRANDS}
    for r in db_http.select_all("listings", f"select={cols}&is_active=eq.true&order=id"):
        k = catalog_store.brand_key(r.get("scraped_brand"))
        if k in keys:
            by_brand[k].append(r)
    rng = random.Random(SEED)
    cases = []
    for k, brand in keys.items():
        assert k in catalogs, brand
        pool = by_brand[k][:]
        rng.shuffle(pool)
        seen, picked = set(), []
        norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()  # noqa: E731
        def take(method, n):
            for r in pool:
                if n <= 0:
                    return
                m = r.get("catalog_match_method")
                if (m if m in ("exact", "jev", "jev_review") else None) != method or norm(r["scraped_name"]) in seen:
                    continue
                seen.add(norm(r["scraped_name"]))
                picked.append(r)
                n -= 1
        for method, n in QUOTA:
            take(method, n)
        for method in ("jev", "jev_review", None, "exact"):      # fill what a stratum lacked
            take(method, PER_BRAND - len(picked))
        for r in picked:
            cases.append({"id": str(r["id"]), "brand": catalogs[k]["brand_name"], "catalog_source": catalogs[k].get("source_method"),
                          "listing": {"brand": r.get("scraped_brand") or "", "name": r.get("scraped_name") or "",
                                      "category": r.get("scraped_category"), "subtype": r.get("subtype"),
                                      "size_field": r.get("variant"),
                                      "price_cents": r.get("price_cents"), "description": r.get("description"),
                                      "url": r.get("url")},
                          "store": stores.get(str(r.get("dispensary_id")), ""),
                          "recorded": {"method": r.get("catalog_match_method"), "p": r.get("catalog_match_confidence"),
                                       "entry_id": r.get("catalog_entry_id")},
                          "label": None})
    out = HERE / "cases" / "sample.json"
    out.write_text(json.dumps({"eval_type": "catalog_match", "seed": SEED, "description":
        "30 brands x 10 live listings (2026-10-07), spread over the matcher's last decision. 'label' is the "
        "catalog entry the listing is (entry_id), or the product with its size missing (product_entry_id), or "
        "none; see README.md.", "cases": cases}, indent=1, ensure_ascii=False))
    from collections import Counter
    print(f"{len(cases)} listings from {len(keys)} brands; recorded methods "
          f"{dict(Counter(c['recorded']['method'] for c in cases))}")


if __name__ == "__main__":
    main()
