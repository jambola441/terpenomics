"""reenrich_csv.py (scrape.py --import-only's enrichment) and the importer's rail check
on a failed row's stored subtype — offline."""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import import_listings  # noqa: E402
import reenrich_csv  # noqa: E402
from scraper_common import CSV_COLUMNS  # noqa: E402


def test_restore_scraped_undoes_enrichment_outputs():
    row = {"name": "Acme Blue Dream 1/8oz", "brand": "Acme", "raw_category": "Flower",
           "category": "pre-rolls", "variant": "3.5g", "scraped_variant": "1/8oz",
           "subtype": "smalls", "strain": "Blue Dream", "product_line": "Gold",
           "enrich_failed": "True", "description": "d", "price_cents": "4000"}
    reenrich_csv.restore_scraped(row)
    assert row["category"] == "flower" and row["variant"] == "1/8oz"
    for col in ("subtype", "strain", "product_line", "enrich_failed"):
        assert col not in row
    assert row["description"] == "d" and row["price_cents"] == "4000"


def test_restore_scraped_legacy_csv_keeps_what_it_has():
    row = {"name": "X", "raw_category": "", "category": "edibles", "variant": "100mg"}
    reenrich_csv.restore_scraped(row)
    assert row["category"] == "edibles" and row["variant"] == "100mg"


def test_reenrich_rewrites_csv_with_fresh_answers(tmp_path, monkeypatch):
    import enrich
    path = tmp_path / "s_20261011T000000Z.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, restval="")
        w.writeheader()
        w.writerow({"dispensary_slug": "s", "sku": "1", "name": "Acme Cart", "brand": "Acme",
                    "category": "vaporizers", "raw_category": "Vaporizers", "variant": "1g",
                    "scraped_variant": "1 g", "subtype": "battery", "strain": "old"})
    seen = {}

    def fake_enrich(rows, model="haiku", **k):
        seen.update(rows[0], model=model)
        rows[0].update(subtype="cart", strain="")
        return {"failed_rows": 0, "cost_usd": 0.0}
    monkeypatch.setattr(enrich, "enrich", fake_enrich)
    n, usage = reenrich_csv.reenrich(path, model="haiku-or")
    assert n == 1 and seen["variant"] == "1 g" and "subtype" not in seen
    assert seen["model"] == "haiku-or"
    out = list(csv.DictReader(open(path, encoding="utf-8")))
    assert out[0]["subtype"] == "cart" and out[0]["strain"] == ""
    assert path.with_suffix(".usage.json").exists()


def test_failed_row_drops_a_retired_stored_subtype():
    existing = {("1", "1g"): {"is_active": True, "variant": "1g", "scraped_category": "vaporizers",
                             "subtype": "battery", "strain": None, "product_line": None,
                             "reading": {"category": "vaporizers", "subtype": "battery"}},
                ("2", "3.5g"): {"is_active": True, "variant": "3.5g", "scraped_category": "flower",
                               "subtype": "gone", "strain": None, "product_line": None,
                               "reading": None},
                ("3", "3.5g"): {"is_active": True, "variant": "3.5g", "scraped_category": "flower",
                               "subtype": "smalls", "strain": None, "product_line": None,
                               "reading": None}}
    recs = [{"sku": s, "variant": v, "_enrich_failed": True, "_store_category": None,
             "scraped_category": "other", "subtype": "other", "strain": "", "product_line": None}
            for s, v in existing]
    import_listings.record_reading(recs, existing)
    assert import_listings.protect_failed_enrichment(recs, existing) == 3
    assert recs[0]["subtype"] is None and recs[0]["reading"]["subtype"] is None
    assert recs[1]["subtype"] == "flower"   # category default
    assert recs[2]["subtype"] == "smalls"   # still on the rail
