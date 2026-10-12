"""Tests for rematch_brand.patches: what a re-match writes, as an import would."""

import os
import sys
from types import SimpleNamespace as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rematch_brand  # noqa: E402

ENTRY = {"id": "t1", "category": "tinctures", "subtype": "tincture", "product_line": "Live Resin",
         "strain": "Skunk", "variant": "15mL"}
CATALOG = {"entries": [ENTRY]}
READING = {"category": "tinctures", "strain": "Skunk", "size": "15mL", "product_line": "Live Resin"}


def row(**kw):
    return {"id": 1, "scraped_name": "MFNY Skunk Live Resin Tincture | 15mL", "scraped_category": "tinctures",
            "subtype": None, "strain": None, "product_line": None, "variant": "400mg", "size": None,
            "catalog_entry_id": None, "catalog_match_confidence": None,
            "catalog_match_method": "review_missing", "reading": {"strain": None}, **kw}


def decision(method="attributes", entry=ENTRY, conf=0.99):
    return D(listing={"id": 1, "reading": READING}, method=method, entry=entry, confidence=conf)


def test_a_stale_listing_takes_the_new_match_identity_and_size():
    [(lid, cols)] = rematch_brand.patches([row()], CATALOG, [decision()]).items()
    assert lid == "1" and cols["reading"] == READING
    assert (cols["catalog_entry_id"], cols["catalog_match_method"]) == ("t1", "attributes")
    assert (cols["strain"], cols["product_line"], cols["size"]) == ("Skunk", "Live Resin", "15mL")


def test_nothing_is_written_when_nothing_changed():
    done = row(strain="Skunk", product_line="Live Resin", subtype="tincture", size="15mL",
               catalog_entry_id="t1", catalog_match_confidence=0.99, catalog_match_method="attributes",
               reading=READING)
    assert rematch_brand.patches([done], CATALOG, [decision()]) == {}


def test_an_untrusted_listing_shows_the_stores_size_and_a_manual_match_keeps_its_entry():
    cols = rematch_brand.patches([row(size="15mL")], CATALOG, [decision("review_unsure", None, 0.5)])["1"]
    assert cols["size"] == "400mg" and cols["catalog_match_method"] == "review_unsure"
    manual = row(catalog_entry_id="x9", catalog_match_method="manual")
    assert set(rematch_brand.patches([manual], CATALOG, [decision()])["1"]) == {"reading"}
