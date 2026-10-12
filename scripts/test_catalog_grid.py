"""Tests for catalog_grid.py — every brand catalog is a full grid. Offline."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_grid as grid  # noqa: E402
import catalog_match as cm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def e(pk, name, line, variant, category="vaporizers", subtype="pod", **kw):
    return {"id": f"{pk}:{variant}", "product_key": pk, "name": name, "product_line": line, "strain": name,
            "category": category, "subtype": subtype, "variant": variant, "is_active": True,
            "source": "listings_bootstrap", "external_id": f"{pk}:{variant}", **kw}


def inferred(pk, name, line, variant, active=True, **kw):
    return {**e(pk, name, line, variant, **kw), "id": f"x-{pk}-{variant}", "source": "inferred",
            "external_id": f"inferred:{pk}:{variant}", "is_active": active}


def cells(rows):
    return sorted((r["product_key"], r["variant"]) for r in rows)


def written(catalog):
    """The catalog after its plan is applied, as the database would hold it."""
    p = grid.plan(catalog)
    revive, retire = set(p.revive), set(p.retire)
    patch = dict(p.patch)
    out = []
    for x in catalog["entries"]:
        x = {**x, **patch.get(x["id"], {})}
        if x["id"] in revive:
            x["is_active"] = True
        if x["id"] in retire:
            x["is_active"] = False
        out.append(x)
    out += [{**r, "id": r["external_id"], "is_active": True} for r in p.inserts]
    return {**catalog, "entries": out}


CATALOG = {"id": "c1", "brand_name": "STIIIZY", "brand_slug": "stiiizy", "entries": [
    e("og", "Original OG", "Original", "1g"), e("og", "Original OG", "Original", "0.5g"),
    e("jack", "Original Jack", "Original", "1g"),
    e("gelato", "Gelato", None, "1g", subtype="all-in-one"),
    e("burst", "Blue Burst", None, "0.5g", subtype="all-in-one"),
    e("ld", "Liquid Diamonds Tahoe", "Liquid Diamonds", "1g"),
]}


def test_every_strain_gets_every_size_of_its_group_line_less_groups_too():
    want = grid.wanted(CATALOG)
    assert cells(want.values()) == [("burst", "1g"), ("gelato", "0.5g"), ("jack", "0.5g")]
    assert want["inferred:jack:0.5g"]["attributes"] == {"inferred_from": ["Original OG"]}
    assert all(r["source"] == "inferred" for r in want.values())


def test_groups_do_not_cross_category_subtype_or_line():
    cat = {"id": "c", "brand_name": "B", "entries": [
        e("a", "A", "L", "1g"), e("b", "B", "L", "2g", subtype="cart"),
        e("c", "C", "M", "0.5g"), e("d", "D", "L", "10pk 100mg", category="edible", subtype="gummy")]}
    assert grid.wanted(cat) == {}


def test_no_category_is_skipped_tinctures_and_topicals_fill_too():
    balm = {"id": "c2", "brand_name": "Papa & Barkley", "entries": [
        e("tr", "Releaf 1:3", "Releaf", "90mg", "topical", "balm"),
        e("tr", "Releaf 1:3", "Releaf", "300mg", "topical", "balm"),
        e("cr", "Releaf 3:1", "Releaf", "45mg", "topical", "balm")]}
    assert cells(grid.wanted(balm).values()) == [("cr", "300mg"), ("cr", "90mg"), ("tr", "45mg")]


def test_lines_once_curated_sizes_by_product_fill_like_any_other():
    drops = {"id": "c3", "brand_name": "1906", "entries": [
        e("bliss", "Drops Bliss", "Drops", "20pk 100mg", category="edible", subtype="tablet"),
        e("genius", "Drops Genius", "Drops", "30pk 75mg", category="edible", subtype="tablet")]}
    assert cells(grid.wanted(drops).values()) == [("bliss", "30pk 75mg"), ("genius", "20pk 100mg")]


def test_the_exceptions_are_gone_from_the_data():
    lines = (ROOT / "data" / "product_lines.json").read_text()
    assert "sizes_by_product" not in lines
    assert not (ROOT / "data" / "line_fill.json").exists()
    for brand in ("Grön", "Off Hours", "Cannabals", "1906", "Heady Tree"):
        assert brand in json.loads(lines)


def test_sync_is_idempotent():
    once = written({**CATALOG, "entries": CATALOG["entries"] + [
        inferred("jack", "Original Jack", "Original", "0.5g", active=False),
        inferred("og", "Original OG", "Original", "2g")]})
    assert not grid.plan(once)
    assert not grid.plan(written(once))
    assert grid.gaps({**once, "entries": [x for x in once["entries"] if x["is_active"]]}) == {}


def test_previously_inferred_cells_come_back_by_id():
    cat = {**CATALOG, "entries": CATALOG["entries"] + [
        inferred("jack", "Original Jack", "Original", "0.5g", active=False)]}
    p = grid.plan(cat)
    assert p.revive == ["x-jack-0.5g"] and "inferred:jack:0.5g" not in {r["external_id"] for r in p.inserts}


def test_a_size_retires_only_when_no_stated_entry_in_the_group_has_it():
    # og states 2g: jack's inferred 2g stays. Then og's 2g is retired: jack's 2g goes.
    base = [e("og", "OG", "Original", "1g"), e("og", "OG", "Original", "2g"), e("jack", "Jack", "Original", "1g"),
            inferred("jack", "Jack", "Original", "2g")]
    assert not grid.plan({"id": "c", "brand_name": "B", "entries": base}).retire
    gone = [{**x, "is_active": False} if x["id"] == "og:2g" else x for x in base]
    assert grid.plan({"id": "c", "brand_name": "B", "entries": gone}).retire == ["x-jack-2g"]


def test_an_inferred_size_held_up_by_an_inferred_one_does_not_count():
    cat = {"id": "c", "brand_name": "B", "entries": [
        e("og", "OG", "Original", "1g"), e("jack", "Jack", "Original", "1g"),
        inferred("jack", "Jack", "Original", "2g"), inferred("og", "OG", "Original", "2g")]}
    assert sorted(grid.plan(cat).retire) == ["x-jack-2g", "x-og-2g"]


def test_a_strain_with_no_stated_entry_loses_its_inferred_cells():
    cat = {"id": "c", "brand_name": "B", "entries": [
        e("og", "OG", "Original", "1g"), e("og", "OG", "Original", "2g"),
        {**e("jack", "Jack", "Original", "1g"), "is_active": False},
        inferred("jack", "Jack", "Original", "2g")]}
    assert grid.plan(cat).retire == ["x-jack-2g"]


def test_a_cell_the_product_now_states_is_not_kept_twice():
    cat = {"id": "c", "brand_name": "B", "entries": [
        e("og", "OG", "Original", "2g"), e("jack", "Jack", "Original", "2g"),
        inferred("jack", "Jack", "Original", "2g")]}
    assert grid.plan(cat).retire == ["x-jack-2g"]


def test_stated_entries_are_never_touched():
    cat = {**CATALOG, "entries": CATALOG["entries"] + [
        inferred("og", "Original OG", "Original", "2g"),
        {**e("old", "Old", "Original", "3g"), "is_active": False}]}
    p = grid.plan(cat)
    touched = set(p.revive) | set(p.retire) | {i for i, _ in p.patch}
    assert all(x.startswith("x-") for x in touched)


def test_a_relined_product_moves_its_inferred_cells():
    cat = {"id": "c", "brand_name": "B", "entries": [
        e("og", "OG", "Original", "1g"), e("og", "OG", "Original", "2g"), e("jack", "Jack", "Original", "1g"),
        inferred("jack", "Jack", "Old Line", "2g")]}
    assert grid.plan(cat).patch == [("x-jack-2g", {"product_line": "Original"})]


def test_the_same_size_written_two_ways_is_one_size():
    cat = {"id": "c", "brand_name": "B", "entries": [
        e("a", "A", "L", "1g"), e("b", "B", "L", "1.0g"), e("b", "B", "L", "0.5 g")]}
    assert cells(grid.wanted(cat).values()) == [("a", "0.5g")]


def test_gaps_counts_missing_and_unwanted_cells_by_group():
    cat = {**CATALOG, "entries": CATALOG["entries"] + [inferred("og", "Original OG", "Original", "2g")]}
    assert grid.gaps(cat) == {("vaporizers", "pod", "original"): (1, 1), ("vaporizers", "all-in-one", ""): (2, 0)}


def test_an_inferred_size_counts_as_the_products_size():
    catalog = {**CATALOG, "entries": CATALOG["entries"] + list(grid.wanted(CATALOG).values())}
    idx = cm.CatalogIndex(catalog)
    assert sorted(s.label() for s in idx.products["jack"].sizes) == ["0.5g", "1g"]
    assert idx.pick_entry("jack", "0.5g", "vaporizers")["variant"] == "0.5g"


def test_sync_brand_writes_the_plan(monkeypatch):
    applied = []
    monkeypatch.setattr(grid, "load", lambda brand: [CATALOG])
    monkeypatch.setattr(grid, "apply", applied.append)
    grid.sync_brand("STIIIZY")
    assert cells(applied[0].inserts) == [("burst", "1g"), ("gelato", "0.5g"), ("jack", "0.5g")]


def test_line_fill_is_the_grid():
    import line_fill
    assert line_fill.sync_brand is grid.sync_brand and line_fill.main is grid.main


def test_every_push_ends_with_the_grid_sync_and_never_retires_inferred(monkeypatch):
    import brand_catalog
    synced = []
    monkeypatch.setattr(brand_catalog, "_push_http", lambda *a: {
        "inserted": 0, "refreshed": 0, "listed_again_but_inactive": 0, "deactivated": 0})
    monkeypatch.setattr(brand_catalog, "_grid_sync", synced.append)
    brand_catalog.push({"brand_name": "X"}, via_http=True)
    brand_catalog.push({"brand_name": "Y"}, via_http=True, dry_run=True)
    assert synced == ["X"]
    src = (ROOT / "scripts" / "brand_catalog.py").read_text()
    assert 'r.get("source") != "inferred"' in src and "IS DISTINCT FROM 'inferred'" in src


def test_catalog_writes_call_the_grid():
    for name in ("catalog_fix.py", "run_scrape_cron.py"):
        assert "catalog_grid" in (ROOT / "scripts" / name).read_text(), name


def test_data_health_reports_grid_gaps():
    import data_health as dh
    from datetime import datetime, timezone
    data = dh.Data([], {"stiiizy": CATALOG}, {}, {}, datetime.now(timezone.utc))
    found = dh.grid_gaps(data)
    assert sorted(f.evidence for f in found) == [1, 2] and all(f.kind == "grid-gap" for f in found)
    full = {**CATALOG, "entries": CATALOG["entries"] + list(grid.wanted(CATALOG).values())}
    assert dh.grid_gaps(dh.Data([], {"stiiizy": full}, {}, {}, datetime.now(timezone.utc))) == []
