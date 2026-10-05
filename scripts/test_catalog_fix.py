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
