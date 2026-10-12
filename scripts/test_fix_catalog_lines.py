"""The catalog-lines-only rule (catalog_match.catalog_line), the import gate and the cleanup plan."""

import os
import sys
from types import SimpleNamespace as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_match as cm  # noqa: E402
import fix_catalog_lines  # noqa: E402
import import_listings  # noqa: E402
import rematch_brand  # noqa: E402

CAT = {"brand_name": "MFNY", "entries": [
    {"id": "e1", "category": "pre-rolls", "product_line": "BagelHole Live Resin"},
    {"id": "e2", "category": "pre-rolls", "product_line": "Classics"},
    {"id": "e3", "category": "vapes", "product_line": "Vape Only"},
    {"id": "old", "category": "pre-rolls", "product_line": "Bagel Hole", "is_active": False},
]}
CATS = {"mfny": CAT}


def test_entry_line_then_reading_line_then_none():
    assert cm.catalog_line(CAT, "e1", {"product_line": "Classics"}) == "BagelHole Live Resin"
    assert cm.catalog_line(CAT, None, {"product_line": "classics"}, "pre-rolls") == "Classics"
    assert cm.catalog_line(CAT, None, {"product_line": "Bagel Hole"}, "pre-rolls") is None
    assert cm.catalog_line(CAT, "old", {"product_line": "Mini"}) is None     # retired entry
    assert cm.catalog_line(CAT, None, None) is None


def test_reading_line_is_category_scoped():
    assert cm.catalog_line(CAT, None, {"product_line": "Vape Only"}, "pre-rolls") is None
    assert cm.catalog_line(CAT, None, {"product_line": "Vape Only"}, "vapes") == "Vape Only"


def rec(**kw):
    return {"id": 1, "scraped_brand": "MFNY", "scraped_category": "pre-rolls", "product_line": "Mini",
            "catalog_entry_id": None, "catalog_match_method": "review_missing",
            "reading": {"product_line": "Mini"}, **kw}


def test_plan_touches_untrusted_rows_of_catalog_brands_only():
    rows = [rec(), rec(id=2, scraped_brand="NoCatalog"),
            rec(id=3, catalog_entry_id="e2", catalog_match_method="attributes", product_line="Classics"),
            rec(id=4, catalog_entry_id="e1", catalog_match_method="jev_review"),
            rec(id=5, product_line=None)]
    assert [(r["id"], line) for r, line in fix_catalog_lines.plan(rows, CATS)] == \
        [(1, None), (4, "BagelHole Live Resin")]


def test_import_drops_enrichments_guessed_line_for_catalog_brands():
    records = [rec(), rec(id=2, scraped_brand="NoCatalog"),
               rec(id=3, reading={"product_line": "Classics"})]
    assert import_listings.catalog_lines_only(records, CATS) == 2
    assert [r["product_line"] for r in records] == [None, "Mini", "Classics"]
    assert records[0]["reading"]["product_line"] == "Mini"      # the reading keeps what was read


def test_rematch_gives_an_untrusted_listing_only_a_catalog_line():
    row = {"id": 1, "scraped_name": "MFNY Bagel Hole", "scraped_category": "pre-rolls", "subtype": None,
           "strain": None, "product_line": "Bagel Hole", "variant": "1g", "size": "1g",
           "catalog_entry_id": None, "catalog_match_confidence": None,
           "catalog_match_method": "review_missing", "reading": {}}
    d = D(listing={"id": 1, "reading": {"product_line": "Bagel Hole"}}, method="review_missing",
          entry=None, confidence=0.0)
    assert rematch_brand.patches([row], CAT, [d])["1"]["product_line"] is None
    d = D(listing={"id": 1, "reading": {}}, method="review_unsure", entry=CAT["entries"][0], confidence=0.6)
    assert rematch_brand.patches([row], CAT, [d])["1"]["product_line"] == "BagelHole Live Resin"
