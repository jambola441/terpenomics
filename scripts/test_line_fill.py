"""Tests for line_fill.py — offline."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_match as cm  # noqa: E402
import line_fill  # noqa: E402


def e(pk, name, line, variant, category="vaporizers", subtype="pod", **kw):
    return {"id": f"{pk}:{variant}", "product_key": pk, "name": name, "product_line": line, "strain": name,
            "category": category, "subtype": subtype, "variant": variant, "is_active": True,
            "source": "listings_bootstrap", "external_id": f"{pk}:{variant}", **kw}


CATALOG = {"id": "c1", "brand_name": "STIIIZY", "entries": [
    e("og", "Original OG", "Original", "1g"), e("og", "Original OG", "Original", "0.5g"),
    e("jack", "Original Jack", "Original", "1g"),
    e("gelato", "Gelato", None, "1g", subtype="all-in-one"),
    e("burst", "Blue Burst", None, "0.5g", subtype="all-in-one"),
    e("ld", "Liquid Diamonds Tahoe", "Liquid Diamonds", "1g"),
]}


def test_a_named_line_fills_and_a_nameless_one_does_not():
    want = line_fill.wanted(CATALOG)
    assert [(r["product_key"], r["variant"], r["source"]) for r in want.values()] == [("jack", "0.5g", "inferred")]
    assert want["inferred:jack:0.5g"]["attributes"] == {"inferred_from": ["Original OG"]}


def test_sync_adds_brings_back_and_takes_back():
    catalog = {**CATALOG, "entries": CATALOG["entries"] + [
        # retired by a push, still implied: brought back
        {**e("jack", "Original Jack", "Original", "0.5g"), "id": "x1", "source": "inferred",
         "external_id": "inferred:jack:0.5g", "is_active": False},
        # no longer implied: taken back
        {**e("og", "Original OG", "Original", "2g"), "id": "x2", "source": "inferred",
         "external_id": "inferred:og:2g"}]}
    inserts, revive, retire = line_fill.plan(catalog)
    assert (inserts, revive, retire) == ([], ["x1"], ["x2"])


def test_an_inferred_size_counts_as_the_products_size():
    # The owner's rule (2026-10-09): a line's sizes are the rule, for the shortlist too.
    catalog = {**CATALOG, "entries": CATALOG["entries"] + list(line_fill.wanted(CATALOG).values())}
    idx = cm.CatalogIndex(catalog)
    jack = idx.products["jack"]
    assert sorted(s.label() for s in jack.sizes) == ["0.5g", "1g"]
    assert "0.5g" in jack.describe()
    assert idx.pick_entry("jack", "0.5g", "vaporizers")["variant"] == "0.5g"


def test_a_push_syncs_only_a_brand_line_fill_was_turned_on_for(monkeypatch):
    synced = []
    monkeypatch.setattr(line_fill, "sync", lambda catalog, write=False: synced.append(catalog["id"]) or (0, 0, 0))
    monkeypatch.setattr(line_fill, "load", lambda brand: [CATALOG])
    line_fill.sync_brand("STIIIZY")
    assert synced == []                                   # never filled: a push does not start it
    filled = {**CATALOG, "entries": CATALOG["entries"] + [
        {**e("jack", "Original Jack", "Original", "0.5g"), "source": "inferred", "is_active": False}]}
    monkeypatch.setattr(line_fill, "load", lambda brand: [filled])
    line_fill.sync_brand("STIIIZY")
    assert synced == ["c1"]


def test_tinctures_and_topicals_are_not_filled():
    balm = {"id": "c2", "brand_name": "Papa & Barkley", "entries": [
        e("tr", "Releaf 1:3 THC Rich", "Releaf", "90mg", "topical", "balm"),
        e("tr", "Releaf 1:3 THC Rich", "Releaf", "300mg", "topical", "balm"),
        e("cr", "Releaf 3:1 CBD Rich", "Releaf", "45mg", "topical", "balm"),
        e("sl", "Releaf Sleep", "Releaf", "500mg", "tinctures", None),
        e("t1", "Releaf THC1000", "Releaf", "1000mg", "tinctures", None)]}
    assert line_fill.wanted(balm) == {}


def test_a_line_whose_products_come_in_their_own_sizes_is_not_filled():
    # data/product_lines.json: 1906's Drops are curated sizes_by_product (each effect's
    # tin and pouch counts follow its dose).
    drops = {"id": "c2", "brand_name": "1906", "entries": [
        e("bliss", "Drops Bliss", "Drops", "20pk 100mg", category="edible", subtype="tablet"),
        e("bliss", "Drops Bliss", "Drops", "2pk 10mg", category="edible", subtype="tablet"),
        e("genius", "Drops Genius", "Drops", "30pk 75mg", category="edible", subtype="tablet"),
        e("boost", "Drops Boost", "Drops", "3pk 90mg", category="edible", subtype="tablet")]}
    assert line_fill.sizes_by_product("1906", "Drops") and not line_fill.sizes_by_product("STIIIZY", "Original")
    assert line_fill.wanted(drops) == {}
    assert line_fill.wanted({**drops, "brand_name": "Another Brand"})        # the switch is per brand
