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


def with_an_inactive_entry():
    cats = find_catalogs()
    cats["find"]["entries"].append({"id": "old70", "catalog_id": "c2", "name": "Gas Lit", "strain": "Gas Lit",
                                    "product_line": None, "category": "flower", "subtype": "flower",
                                    "variant": "70g", "product_key": "lb:flower:flower::gaslit",
                                    "external_id": "lb:flower:flower::gaslit:70g", "is_active": False,
                                    "match_terms": [], "source": "listings_bootstrap"})
    return cats


def test_an_inactive_entrys_id_is_taken_and_reactivate_brings_it_back():
    """catalog_store.load_all reads active entries only; catalog_fix adds the inactive
    ones (with_inactive) so a plan cannot insert an id the database already holds."""
    with pytest.raises(cf.Refused, match="reactivate that one instead"):
        cf.plan_add_size(with_an_inactive_entry(), "gl35", "70g")
    plan = cf.apply_plan(with_an_inactive_entry(), {"brand": "Find.", "edits": [
        {"op": "reactivate", "entry": "old70", "why": "sold again"}]})
    assert plan.writes == [("update", "brand_catalog_entries", "id=eq.old70", {"is_active": True})]
    with pytest.raises(cf.Refused, match="is active"):
        cf.plan_reactivate(find_catalogs(), "gl35")


def test_preflight_stops_a_plan_before_its_first_write(fresh_db, via_rest):
    via_rest(fresh_db)
    import db_http
    catalog = db_http.insert("brand_catalogs", {"brand_slug": "find", "brand_name": "Find.",
                                                "source_method": "listings_bootstrap"})[0]
    db_http.insert("brand_catalog_entries", {"catalog_id": catalog["id"], "name": "Gas Lit",
                                             "external_id": "lb:flower:flower::gaslit:70g", "is_active": False})
    row = {"catalog_id": catalog["id"], "external_id": "lb:flower:flower::gaslit:70g", "name": "Gas Lit"}
    held = cf.Plan({}, {}, writes=[("update", "brand_catalog_entries", "id=eq.x", {"is_active": False}),
                                   ("insert", "brand_catalog_entries", None, [row])])
    with pytest.raises(cf.Refused, match="held by entry .* \\(inactive: reactivate.*Nothing was written"):
        cf.apply(held)
    fresh = cf.Plan({}, {}, writes=[("insert", "brand_catalog_entries", None,
                                     [{**row, "external_id": "lb:flower:flower::gaslit:14g"}])])
    cf.preflight(fresh)                                       # a new id passes
    twice = cf.Plan({}, {}, writes=[("insert", "brand_catalog_entries", None, [fresh.writes[0][3][0]] * 2)])
    with pytest.raises(cf.Refused, match="twice"):
        cf.preflight(twice)


def herb_catalogs(method="listings_bootstrap"):
    def e(id, strain, variant, line=None, category="preroll", subtype=None, terms=(), active=True, ext=None):
        squash = lambda s: "".join(c for c in (s or "").lower() if c.isalnum())   # noqa: E731
        pk = f"lb:{category}:{subtype or ''}:{squash(line)}:{squash(strain)}"
        return {"id": id, "catalog_id": "c3", "name": " ".join(x for x in (line, strain) if x),
                "product_line": line, "strain": strain, "category": category, "subtype": subtype,
                "variant": variant, "product_key": pk, "external_id": ext or f"{pk}:{variant}",
                "is_active": active, "match_terms": list(terms), "source": "listings_bootstrap"}
    return {"herb": {"id": "c3", "brand_name": "Herb", "brand_slug": "herb", "source_method": method,
                     "entries": [
                         e("gg1", "Garlic Gravy", "1g", terms=["garlic gravy infused 1g"]),
                         e("gg25", "Garlic Gravy", "2.5g", terms=["garlic gravy 5pk"]),
                         e("hgg1", "Garlic Gravy", "1g", line="Hash Infused", terms=["hash infused garlic gravy"]),
                         e("lc1", "Lemon Cherry", "1g", terms=["lemon cherry 1g"]),
                         e("old", "Lemon Cherry", "1g", line="Hash Infused", active=False),
                         e("pf35", "Passionfruit", "3.5g", category="flower", subtype="flower"),
                         e("ac35", "Alien Cookies", "3.5g", category="flower", subtype="flower"),
                         e("ac1", "Alien Cookies", "1g", category="flower", subtype="flower",
                           terms=["alien cookies smalls 1g"]),
                         e("ge1", "Gelato", "1g", terms=["gelato 1g"]),
                         e("gt1", "Gelatto", "1g", terms=["gelatto 1g"])]}}


def test_a_rekey_moves_the_sizes_to_new_rows_and_keeps_the_old_ones_for_their_ids():
    """The key and the external ids carry line, strain and subtype. The old rows are
    deactivated, not edited: holding their ids, they stop a rebuild that still proposes
    the old product from adding it back (push never reactivates)."""
    plan = cf.plan_rekey(herb_catalogs(), "gt1", line="Ice Packs", strain="Gelato")
    (op, _, _, rows), deactivate = plan.writes
    assert op == "insert" and deactivate == ("update", "brand_catalog_entries", "id=eq.gt1", {"is_active": False})
    row, = rows
    assert (row["product_key"], row["external_id"]) == ("lb:preroll::icepacks:gelato", "lb:preroll::icepacks:gelato:1g")
    assert (row["name"], row["product_line"], row["strain"]) == ("Ice Packs Gelato", "Ice Packs", "Gelato")
    assert row["match_terms"] == ["gelatto 1g"] and row["source"] == "curated"
    new_id = plan.moved["gt1"]
    assert next(e for e in plan.changed["entries"] if e["id"] == new_id)["is_active"]


def test_a_rekey_joins_the_product_that_exists():
    plan = cf.plan_rekey(herb_catalogs(), "gg1", line="Hash Infused")
    inserted = [w for w in plan.writes if w[0] == "insert"]
    updates = {w[2]: w[3] for w in plan.writes if w[0] == "update"}
    assert updates["id=eq.hgg1"] == {"match_terms": ["garlic gravy infused 1g", "hash infused garlic gravy"]}
    assert [r["external_id"] for r in inserted[0][3]] == ["lb:preroll::hashinfused:garlicgravy:2.5g"]
    assert updates["id=eq.gg1"] == updates["id=eq.gg25"] == {"is_active": False}
    assert [w[0] for w in plan.writes] == ["insert", "update", "update", "update"]   # deactivations last
    assert plan.moved["gg1"] == "hgg1" and plan.moved["gg25"].startswith("new-")


def test_a_rekey_reactivates_the_row_that_holds_the_new_id():
    plan = cf.plan_rekey(herb_catalogs(), "lc1", line="Hash Infused")
    assert plan.writes[0] == ("update", "brand_catalog_entries", "id=eq.old",
                              {"is_active": True, "source": "curated", "match_terms": ["lemon cherry 1g"]})
    assert plan.moved == {"lc1": "old"} and not [w for w in plan.writes if w[0] == "insert"]


def test_a_spelling_the_key_does_not_see_is_a_rename_in_place():
    plan = cf.plan_rekey(herb_catalogs(), "pf35", strain="Passion Fruit")
    assert plan.writes == [("update", "brand_catalog_entries", "id=eq.pf35",
                            {"name": "Passion Fruit", "strain": "Passion Fruit"})]
    assert plan.moved == {}


def test_only_moves_one_size_and_two_spellings_fold_into_one_row():
    plan = cf.plan_rekey(herb_catalogs(), "ac1", subtype="smalls", only=True)
    (_, _, _, (row,)), _ = plan.writes
    assert row["external_id"] == "lb:flower:smalls::aliencookies:1g" and row["subtype"] == "smalls"
    assert next(e for e in plan.changed["entries"] if e["id"] == "ac35")["is_active"]   # its 3.5g stays

    plan = cf.plan_rekey(herb_catalogs(), ["ge1", "gt1"], line="Ice Packs", strain="Gelato")
    (_, _, _, (row,)), *deactivations = plan.writes
    assert row["match_terms"] == ["gelato 1g", "gelatto 1g"] and len(deactivations) == 2
    assert plan.moved["ge1"] == plan.moved["gt1"]


def test_rekey_refusals():
    cats = herb_catalogs()
    for args, kw, why in [
            ("lc1", {"line": ""}, "nothing changes"),
            ("ac35", {"subtype": "badder"}, "not a flower subtype"),
            ("lc1", {"subtype": "infused"}, "keeps no subtype"),
            (["lc1", "ac35"], {"line": "Hash Infused"}, "different categories"),
            (["ge1", "gt1"], {"line": "Ice Packs"}, "differ in strain"),
            ("ac1", {"strain": "alien cookies", "only": True}, "some sizes of the product"),
            ("old", {"line": ""}, "is inactive")]:
        with pytest.raises(cf.Refused, match=why):
            cf.plan_rekey(cats, args, **kw)
    with pytest.raises(cf.Refused, match="storefront catalog"):
        cf.plan_rekey(herb_catalogs("storefront_html"), "lc1", line="Hash Infused")


def test_a_plan_rekeys_follow_each_other_and_refuse_rows_the_plan_adds():
    doc = {"brand": "Herb", "edits": [
        {"op": "rekey", "entry": {"strain": "Lemon Cherry"}, "line": "Hash Infused"},
        {"op": "rekey", "entries": ["ge1", "gt1"], "line": "Ice Packs", "strain": "Gelato", "why": "one strain"}]}
    plan = cf.apply_plan(herb_catalogs(), doc)
    assert plan.moved["lc1"] == "old" and plan.moved["ge1"] == plan.moved["gt1"]
    assert "2. re-key Gelato (preroll), Gelatto (preroll) as Ice Packs Gelato (preroll): " \
           "lb:preroll::icepacks:gelato  [one strain]" in plan.notes

    chain = cf.apply_plan(herb_catalogs(), {"brand": "Herb", "edits": [
        {"op": "rekey", "entry": "lc1", "line": "Hash Infused"},          # into the reactivated row
        {"op": "rekey", "entry": "old", "line": "Classics"}]})            # which moves on
    assert chain.moved["lc1"] == chain.moved["old"] and chain.moved["lc1"].startswith("new-")

    added = {"brand": "Herb", "edits": [{"op": "add-size", "entry": "lc1", "size": "2.5g"},
                                         {"op": "rekey", "entry": "lc1", "line": "Hash Infused"}]}
    with pytest.raises(cf.Refused, match=r"edit 2 \(rekey\).*sizes this plan adds"):
        cf.apply_plan(herb_catalogs(), added)


def test_measuring_a_rekey_counts_a_listing_that_follows_its_entry_as_staying():
    plan = cf.plan_rekey(herb_catalogs(), "gt1", line="Ice Packs", strain="Gelato")
    new_id = plan.moved["gt1"]
    before = {"l1": ("trusted", "lb:preroll:::gelatto", "gt1", "1g"),
              "l2": ("trusted", "lb:preroll:::gelatto", "gt1", "1g")}
    after = {"l1": ("trusted", "lb:preroll::icepacks:gelato", new_id, "1g"),
             "l2": ("trusted", "lb:preroll:::gelato", "ge1", "1g")}        # went elsewhere: a real move
    stable, noise = cf.compare([cf.carried(plan, before)], [after])
    assert list(stable) == ["l2"] and noise == 0
