"""Tests for review_tools.py: the review agent's read-only tools, offline."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import review_tools as rt  # noqa: E402
import size_choice  # noqa: E402

CATALOGS = {"grön": {"brand_name": "Grön", "source_method": "storefront", "entries": [
    {"id": "e1", "catalog_id": "c1", "product_key": "k1", "name": "Baja Blaze Mega", "category": "edible",
     "subtype": "gummy", "strain": "Baja Blaze", "product_line": "Mega", "variant": "100mg"},
    {"id": "e2", "catalog_id": "c1", "product_key": "k2", "name": "Pearls Lychee Limeade", "category": "edible",
     "subtype": "gummy", "strain": "Lychee Limeade", "product_line": "Pearls", "variant": "10pk 100mg"},
]}}
QUEUED = {"id": "q1", "brand": "Grön", "name": "Grön - Baja Blaze Mega", "category": "edible",
          "size_field": "", "price_cents": 1800, "description": "100mg THC per gummy", "url": "https://x/p",
          "store": "s1"}
OTHERS = [{"id": "o1", "brand": "GRÖN", "name": "Baja Blaze MEGA 100mg Gummy", "category": "edible",
           "size_field": "100mg", "price_cents": 1700, "strain": "Baja Blaze", "product_line": "Mega",
           "store": "s2", "catalog_match_method": "exact"},
          {"id": "o2", "brand": "Grön", "name": "Pearls Tangelo", "category": "edible", "size_field": "100mg",
           "price_cents": 2200, "strain": "Tangelo", "product_line": "Pearls", "store": "s3"}]


def ctx(**kw):
    prices = size_choice.PriceBook(product={"c1|k1|100": {"median": 1750, "n": 4}})
    return rt.ReviewContext(catalogs=CATALOGS, listings=OTHERS + [QUEUED], prices=prices,
                            queue={"q1": QUEUED}, **kw)


def test_catalog_search_ranks_by_the_query_and_shows_typical_prices():
    out = rt.search_catalog(ctx(), "Grön", "baja blaze")
    assert out["has_catalog"] and out["entries"][0]["strain"] == "Baja Blaze"
    assert out["entries"][0]["typical_price"] == "$17.50"
    assert rt.search_catalog(ctx(), "Nobody", "x") == {"brand": "Nobody", "has_catalog": False, "entries": []}


def test_other_stores_exclude_the_listing_under_review():
    names = [l["name"] for l in rt.other_store_listings(ctx(), "Grön", "baja blaze mega")["listings"]]
    assert names == ["Baja Blaze MEGA 100mg Gummy"]


def test_the_page_tool_fetches_only_the_listings_own_url():
    seen = []
    c = ctx(fetch_page=lambda url: seen.append(url) or "<p>Twenty pieces, <b>5mg</b> each</p><script>x()</script>")
    assert rt.listing_page(c, "q1")["text"] == "Twenty pieces, 5mg each"
    assert seen == ["https://x/p"]
    assert "error" in rt.listing_page(c, "o1")                  # not under review: not fetched
    assert rt.listing_page(ctx(), "q1")["text"] is None         # fetching off


def test_size_readings_list_the_options_with_prices():
    out = rt.size_readings(ctx(), "q1")
    assert out["unit"] == "mg" and out["listing_price"] == "$18.00"
    assert any(r["size"] == "100mg" for r in out["readings"])


def test_submitted_labels_are_checked_against_the_taxonomy():
    c = ctx()
    assert not rt.submit_labels(c, "q1", "gummies", "Baja Blaze", "Mega", "100mg", "sure", "x")["accepted"]
    bad = rt.submit_labels(c, "q1", "edible", "Baja Blaze", "Mega", "100 pieces", "very", "x")
    assert not bad["accepted"] and len(bad["errors"]) == 2      # the size and the confidence
    ok = rt.submit_labels(c, "q1", "edible", "Baja Blaze", "Mega", "100mg", "sure",
                          "Catalog entry and another store agree.", subtype="gummy")
    assert ok == {"accepted": True} and c.answers["q1"]["product_line"] == "Mega"
    assert not rt.submit_labels(c, "o1", "edible", None, None, None, "sure", "x")["accepted"]


def test_a_catalog_fix_is_only_proposed():
    c = ctx()
    rt.propose_catalog_fix(c, "Grön", "add Baja Blaze Mega 10pk", "two stores sell it")
    assert c.proposals[0]["change"] == "add Baja Blaze Mega 10pk"


def test_tools_have_schemas_and_bad_calls_come_back_as_errors():
    assert {t["name"] for t in rt.TOOLS} == set(rt.FUNCTIONS)
    assert "error" in json.loads(rt.run_tool(ctx(), "search_catalog", {"nope": 1}))
    assert "error" in json.loads(rt.run_tool(ctx(), "rm_rf", {}))


def test_other_stores_leave_out_the_store_under_review():
    """The same product at the listing's own store carries that store's earlier answer."""
    same_store = {**OTHERS[0], "id": "o3", "store": "s1", "name": "Baja Blaze Mega Gummy"}
    c = rt.ReviewContext(catalogs=CATALOGS, listings=OTHERS + [same_store, QUEUED], queue={"q1": QUEUED},
                         stores={"s2": "the-plug"})
    out = rt.other_store_listings(c, "Grön", "baja blaze mega")["listings"]
    assert [(l["store"], l["name"]) for l in out] == [("the-plug", "Baja Blaze MEGA 100mg Gummy")]


def test_a_submitted_size_is_written_as_the_package_total():
    c = ctx()
    assert rt.submit_labels(c, "q1", "edible", "Baja Blaze", "Mega", "20pk 100 mg", "likely", "x")["accepted"]
    assert c.answers["q1"]["size"] == "100mg"
    assert rt.submit_labels(c, "q1", "vaporizers", "Baja Blaze", None, "1000mg", "likely", "x")["accepted"]
    assert c.answers["q1"]["size"] == "1g"


def test_size_readings_can_read_as_another_category():
    out = rt.size_readings(ctx(), "q1", category="flower")
    assert out["unit"] == "g"
    assert "error" in rt.size_readings(ctx(), "q1", category="gummies")


def test_a_match_answer_names_an_entry_of_the_listings_brand():
    c = ctx()
    assert not rt.submit_match(c, "q1", "nope", None, "sure", "x")["accepted"]
    assert not rt.submit_match(c, "q1", "e1", "e2", "sure", "x")["accepted"]          # one or the other
    assert rt.submit_match(c, "q1", None, "e1", "likely", "The 10pk isn't in the catalog.") == {"accepted": True}
    assert c.answers["q1"]["product_key"] == "k1" and c.answers["q1"]["entry_id"] is None
    assert rt.submit_match(c, "q1", None, None, "sure", "Not in the catalog.")["accepted"]
    assert c.answers["q1"]["product_key"] is None


def test_labelling_a_matcher_test_set_hides_what_the_matcher_recorded():
    c = ctx(blind_matches=True)
    row = rt.other_store_listings(c, "Grön", "baja blaze mega")["listings"][0]
    assert set(row) == {"store", "name", "size_field", "price"}
    assert rt.search_catalog(c, "Grön", "baja")["entries"][0]["product"] == "k1"
