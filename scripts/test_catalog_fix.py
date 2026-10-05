"""The audit's catalog edits: what each plans to write, and what it refuses."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_fix as cf  # noqa: E402


def catalogs(method="listings_bootstrap"):
    def e(id, name, variant, category="preroll", pk=None, terms=(), **kw):
        return {"id": id, "catalog_id": "c1", "name": name, "category": category, "variant": variant,
                "product_key": pk or f"lb:{category}::{name.lower()}", "is_active": True,
                "match_terms": list(terms), "source": method, "external_id": f"x-{id}", **kw}
    return {"stiiizy": {"id": "c1", "brand_name": "STIIIZY", "brand_slug": "stiiizy", "source_method": method,
                        "entries": [
                            e("os1", "40's Orange Sunset", "1g", pk="lb:preroll::40s:orangesunset",
                              product_line="40's", strain="Orange Sunset"),
                            e("bis1", "40's Biscotti", "1g", pk="lb:preroll::40s:biscotti"),
                            e("bis2", "40's Biscotti", "2.5g", pk="lb:preroll::40s:biscotti"),
                            e("rasp", "Raspberry", "10pk 100mg", category="edible",
                              terms=["raspberry sativa enhanced gummies"]),
                            e("boys", "Boysenberry", "10pk 100mg", category="edible",
                              terms=["raspberry sativa enhanced gummies", "boysenberry gummies"]),
                            e("pm", "Pink Lemonade", "100mg", category="edible"),
                        ]}}


def test_a_new_size_takes_the_bootstraps_id_and_the_products_key():
    plan = cf.plan_add_size(catalogs(), "os1", "5 pack 2.5g")
    (op, table, _, row), = plan.writes
    assert (op, table) == ("insert", "brand_catalog_entries")
    assert row["external_id"] == "lb:preroll::40s:orangesunset:2.5g"   # what a rebuild would propose
    assert row["product_key"] == "lb:preroll::40s:orangesunset"         # one product, two sizes
    assert row["variant"] == "2.5g"                 # weights keep the total; the subtype says pack
    assert (row["strain"], row["product_line"], row["match_terms"]) == ("Orange Sunset", "40's", [])
    assert len(plan.changed["entries"]) == len(plan.catalog["entries"]) + 1


def test_a_storefront_size_gets_no_external_id():
    """A re-fetch deactivates every entry whose id the site does not list; none is never listed."""
    (_, _, _, row), = cf.plan_add_size(catalogs("storefront_html"), "os1", "2.5g").writes
    assert row["external_id"] is None


def test_doses_keep_the_pack():
    (_, _, _, changes), = cf.plan_set_size(catalogs(), "pm", "10 pack 100mg").writes
    assert changes == {"variant": "10pk 100mg"}


def test_a_size_the_product_has_is_refused():
    with pytest.raises(cf.Refused, match="already comes in 2.5g"):
        cf.plan_add_size(catalogs(), "bis1", "2.5g")
    with pytest.raises(cf.Refused, match="not a size"):
        cf.plan_add_size(catalogs(), "os1", "large")


def test_dropping_a_name_needs_it_to_stay_on_another_product():
    plan = cf.plan_drop_term(catalogs(), "boys", "raspberry sativa enhanced gummies")
    assert plan.writes == [("update", "brand_catalog_entries", "id=eq.boys",
                            {"match_terms": ["boysenberry gummies"]})]
    assert "it stays on Raspberry" in plan.notes[0]
    with pytest.raises(cf.Refused, match="no other entry holds"):
        cf.plan_drop_term(catalogs(), "boys", "boysenberry gummies")
    assert cf.plan_drop_term(catalogs(), "boys", "boysenberry gummies", force=True).writes


def test_a_name_already_on_an_unrelated_product_is_refused():
    with pytest.raises(cf.Refused, match="cross-wired"):
        cf.plan_add_term(catalogs(), "pm", "STIIIZY | Raspberry Sativa Enhanced Gummies")
    plan = cf.plan_add_term(catalogs(), "pm", "STIIIZY | Pink Lemonade Gummies 10-Piece")
    assert plan.writes[0][3] == {"match_terms": ["pink lemonade gummies 10 piece"]}   # brand-less


def test_deactivating_a_duplicate_moves_its_names():
    plan = cf.plan_deactivate(catalogs(), "boys", into="rasp")
    assert plan.writes == [
        ("update", "brand_catalog_entries", "id=eq.boys", {"is_active": False}),
        ("update", "brand_catalog_entries", "id=eq.rasp",
         {"match_terms": ["boysenberry gummies", "raspberry sativa enhanced gummies"]})]


def test_measuring_counts_only_changes_both_runs_agree_on():
    a, b = ("trusted", "p1", "e1", "1g"), ("trusted", "p1", "e2", "2.5g")
    review = ("jev_review", "p1", "e1", "4.5g")     # the store's own size, until trusted
    old = [{"x": a, "y": review, "z": a}, {"x": a, "y": review, "z": review}]   # z: Jev's noise
    new = [{"x": a, "y": b, "z": a}, {"x": a, "y": b, "z": a}]
    stable, noise = cf.compare(old, new)
    assert stable == {"y": (review, b)} and noise == 1
    assert cf.summarize(stable) == {"trusted gained": 1, "page size changed": 1}


def find_catalogs(method="listings_bootstrap"):
    def e(id, strain, variant, category="flower", subtype="flower", terms=()):
        pk = f"lb:{category}:{subtype or ''}::{strain.lower().replace(' ', '')}"
        return {"id": id, "catalog_id": "c2", "name": strain, "strain": strain, "product_line": None,
                "category": category, "subtype": subtype, "variant": variant, "product_key": pk,
                "external_id": f"{pk}:{variant}", "is_active": True, "match_terms": list(terms),
                "source": "listings_bootstrap"}
    return {"find": {"id": "c2", "brand_name": "Find.", "brand_slug": "find", "source_method": method,
                     "entries": [e("gl35", "Gas Lit", "3.5g"), e("gl28", "Gas Lit", "28g"),
                                 e("ms28", "Mint Snacks", "28g", terms=["mint snacks 28g"]),
                                 e("mz28", "Mint Snackz", "28g"),
                                 e("mz1", "Mint Snackz", "1g", category="preroll", subtype=None),
                                 e("mzz10", "Mintz Snackz", "10g", category="preroll", subtype=None,
                                   terms=["mintz snackz prerolls 10pk 10g"])]}}


def test_a_new_product_takes_the_bootstraps_keys_and_is_curated():
    plan = cf.plan_add_product(find_catalogs(), "Find.", "flower", "Out Of Office", ["3.5g", "28g"],
                               subtype="flower", terms=["Find. | Out Of Office | Hybrid", "Out Of Office - 3.5G Flower"])
    (op, _, _, rows), = plan.writes
    assert op == "insert" and [r["variant"] for r in rows] == ["3.5g", "28g"]
    assert {r["product_key"] for r in rows} == {"lb:flower:flower::outofoffice"}       # one product
    assert [r["external_id"] for r in rows] == ["lb:flower:flower::outofoffice:3.5g",
                                                "lb:flower:flower::outofoffice:28g"]
    assert {r["source"] for r in rows} == {"curated"}       # a --replace rebuild keeps it
    assert rows[0]["match_terms"] == ["out of office 3 5g flower", "out of office hybrid"]   # brand-less
    assert rows[1]["match_terms"] == []


def test_a_storefront_product_gets_no_id_and_its_own_key():
    (_, _, _, rows), = cf.plan_add_product(find_catalogs("storefront_html"), "Find.", "preroll",
                                           "Icy Pine", ["10g"]).writes
    assert rows[0]["external_id"] is None and rows[0]["product_key"] == "cur:preroll:::icypine"


def test_add_product_refuses_a_product_the_catalog_has_and_a_wrong_subtype():
    with pytest.raises(cf.Refused, match="add-size it instead"):
        cf.plan_add_product(find_catalogs(), "Find.", "flower", "gas lit", ["14g"], subtype="flower")
    assert cf.plan_add_product(find_catalogs(), "Find.", "flower", "Gas Lit", ["14g"], subtype="preground").writes
    with pytest.raises(cf.Refused, match="keeps a subtype"):
        cf.plan_add_product(find_catalogs(), "Find.", "flower", "Zangria", ["3.5g"])
    with pytest.raises(cf.Refused, match="keeps no subtype"):
        cf.plan_add_product(find_catalogs(), "Find.", "preroll", "Zangria", ["1g"], subtype="flower")


def test_an_added_size_is_curated_too():
    (_, _, _, row), = cf.plan_add_size(find_catalogs(), "gl35", "70g").writes
    assert row["source"] == "curated" and row["external_id"] == "lb:flower:flower::gaslit:70g"


def test_a_selector_names_one_active_entry():
    cats = find_catalogs()
    assert cf.resolve_entry(cats, "Find.", {"strain": "gas lit", "size": "28g"}) == "gl28"
    assert cf.resolve_entry(cats, "Find.", "gl35") == "gl35"
    with pytest.raises(cf.Refused, match="names 2 active entries"):
        cf.resolve_entry(cats, "Find.", {"strain": "Gas Lit"})
    with pytest.raises(cf.Refused, match="names 0"):
        cf.resolve_entry(cats, "Find.", {"strain": "Gas Lit", "category": "preroll"})


def test_a_plan_applies_its_edits_in_order_and_stops_at_a_refusal():
    doc = {"brand": "Find.", "edits": [
        {"op": "deactivate", "entry": {"strain": "Mint Snacks"}, "into": {"strain": "Mint Snackz", "size": "28g"},
         "why": "one strain"},
        {"op": "add-size", "entry": {"strain": "Mint Snackz", "category": "preroll"}, "size": "10g"},
        {"op": "deactivate", "entry": {"strain": "Mintz Snackz"}, "into": {"strain": "Mint Snackz", "size": "1g"}},
        {"op": "add-product", "category": "preroll", "strain": "Icy Pine", "sizes": ["10g"],
         "terms": ["Pre-Rolls | Find | Icy Pine - 10pk"]}]}
    plan = cf.apply_plan(find_catalogs(), doc)
    assert plan.notes[0].startswith("1. deactivate Mint Snacks") and plan.notes[0].endswith("[one strain]")
    active = {(e["strain"], e["variant"]) for e in plan.changed["entries"] if e["is_active"]}
    assert ("Mint Snacks", "28g") not in active and ("Mintz Snackz", "10g") not in active
    assert {("Mint Snackz", "10g"), ("Icy Pine", "10g")} <= active
    survivor = next(e for e in plan.changed["entries"] if e["id"] == "mz28")
    assert survivor["match_terms"] == ["mint snacks 28g"]                       # names moved over
    assert [w[0] for w in plan.writes] == ["update", "update", "insert", "update", "update", "insert"]
    assert plan.category is None                                                 # flower and preroll
    assert all(e["is_active"] for e in find_catalogs()["find"]["entries"])       # input untouched

    bad = {"brand": "Find.", "edits": [doc["edits"][3], {"op": "add-size", "entry": {"strain": "Icy Pine"},
                                                          "size": "1g"}]}
    with pytest.raises(cf.Refused, match=r"edit 2 \(add-size\).*names 0"):       # new entries: not selectable
        cf.apply_plan(find_catalogs(), bad)


def test_add_product_folds_one_size_written_twice_and_guards_its_store_names():
    (_, _, _, rows), = cf.plan_add_product(find_catalogs(), "Find.", "flower", "Zangria",
                                           ["28g", "1 ounce", "3.5g"], subtype="flower").writes
    assert [(r["variant"], r["external_id"].rsplit(":", 1)[1]) for r in rows] == [("28g", "28g"), ("3.5g", "3.5g")]
    with pytest.raises(cf.Refused, match="cross-wire"):
        cf.plan_add_product(find_catalogs(), "Find.", "flower", "Shock Mints", ["28g"], subtype="flower",
                            terms=["Find. - Mint Snacks 28g"])           # Mint Snacks' own store name
