"""Tests for catalog_bootstrap.py — unit tests offline; the push round-trip needs
TEST_DATABASE_URL (a throwaway database, schema recreated per test)."""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_bootstrap as cb  # noqa: E402


def L(store, name, strain, line=None, variant="0.6g", category="preroll", subtype="infused"):
    return {"id": str(uuid.uuid4()), "dispensary_id": store, "name": name, "brand": "Jetpacks",
            "category": category, "subtype": subtype, "strain": strain, "product_line": line,
            "variant": variant}


JETPACKS = [
    L("s1", "Afghani FJ-Mini Infused Pre-roll | 0.6G", "Afghani"),
    L("s2", "Jetpacks - FJ Mini Afghani Infused Preroll - .6g", "Afghani", "FJ Mini"),
    L("s3", "Infused Pre-Rolls | Jetpacks - FJ Mini | Afghani", "Afghani", "FJ-Mini"),
    L("s4", "Jetpacks FJ-Mini (0.6g) Infused PreRoll - Afghani", "Afghani", "FJ-Mini"),
    L("s1", "Jetpacks FJ-3 Afghani 5pk - 3g", "Afghani", "FJ-3", "3g"),
    L("s2", "Jetpacks | FJ-3 | Afghani | .6g | 5 Pack | 3g", "Afghani", "FJ-3", "3g"),
    L("s3", "Jetpacks | Powdered Donuts | Birthday Cake | 3.5g", "Birthday Cake", "Powdered Donuts",
      "3.5g", "flower", "infused"),
    L("s4", "Jetpacks | Infused Flower | Powdered Donuts | Birthday Cake", "Birthday Cake",
      "Powdered Donuts", "3.5g", "flower", "infused"),
    L("s1", "Jetpacks | Championship Cake Powdered Donuts", "Championship Cake Powdered Donuts",
      None, "3.5g", "flower", "infused"),
    L("s2", "Championship Cake - 3.5g Powdered Donuts", "Championship Cake", "Powdered Donuts",
      "3.5g", "flower", "infused"),
    L("s9", "Jetpacks One Store Only Kush 1g", "One Store Kush", None, "1g"),
    L("s5", "Jetpacks Grinder", "", None, "", "merch", "grinder"),
]


def by_name(doc):
    return {e["name"]: e for e in doc["catalog"]["entries"]}


def test_line_spellings_converge_and_line_less_rows_fold_in():
    out = cb.propose("Jetpacks", JETPACKS)
    e = by_name(out)["FJ-Mini Afghani"]
    assert e["support"] == 4 and e["product_line"] == "FJ-Mini" and e["variant"] == "0.6g"
    assert out["report"]["line_splits_folded"] >= 1


def test_pack_sizes_are_their_own_product():
    e = by_name(cb.propose("Jetpacks", JETPACKS))["FJ-3 Afghani"]
    # A weight's variant is the package total; "5pk" is the subtype's business.
    assert e["variant"] == "3g" and e["support"] == 2


def test_a_counted_preroll_is_a_pack_not_a_single():
    rows = [L("s1", "Doobies Blue Dream 2pk 1g", "Blue Dream", "Doobies", "2pk 1g", subtype="pack"),
            L("s2", "Doobies | Blue Dream | 2pk", "Blue Dream", "Doobies", "2pk 1g", subtype="pack"),
            L("s3", "x doobies blue dream 2 count net 1g", "Blue Dream", "Doobies", "2pk 1g",
              subtype="single")]
    out = cb.propose("Ruby Farms", rows)
    assert [(e["subtype"], e["variant"], e["support"]) for e in out["catalog"]["entries"]] == \
        [("pack", "1g", 3)]
    assert out["report"]["packs_relabeled"] == 1


def test_totals_that_are_one_size_are_one_product():
    # 7 x 0.7g is 4.9g; stores print the same tin as 5g.
    rows = [L(s, "Classics Trop Cherry 7pk 5g", "Trop Cherry", "Classics", "7pk 5g", subtype="pack")
            for s in ("s1", "s2", "s3")]
    rows += [L(s, "Trop Cherry Classics Tin", "Trop Cherry", "Classics", "4.9g", subtype="pack")
             for s in ("s4", "s5")]
    out = cb.propose("Ruby Farms", rows)
    assert [(e["variant"], e["support"]) for e in out["catalog"]["entries"]] == [("5g", 5)]
    assert out["report"]["sizes_merged"] == 1


def test_strain_spellings_with_doubled_letters_are_one_strain():
    rows = [L("s1", "GDP 7pk", "Grand Daddy Purple", None, "7pk 3.5g", subtype="pack"),
            L("s2", "GDP 7pk", "Granddaddy Purple", None, "7pk 3.5g", subtype="pack"),
            L("s3", "GDP 7pk", "Granddaddy Purple", None, "7pk 3.5g", subtype="pack"),
            L("s4", "GDP 7pk", "Grandaddy Purple", None, "7pk 3.5g", subtype="pack"),
            L("s1", "RS11 7pk", "RS11", None, "7pk 3.5g", subtype="pack"),
            L("s2", "RS11 7pk", "RS11", None, "7pk 3.5g", subtype="pack"),
            L("s3", "RS1 7pk", "RS1", None, "7pk 3.5g", subtype="pack"),
            L("s4", "RS1 7pk", "RS1", None, "7pk 3.5g", subtype="pack")]
    entries = cb.propose("Ruby Farms", rows)["catalog"]["entries"]
    assert sorted((e["strain"], e["support"]) for e in entries) == \
        [("Granddaddy Purple", 4), ("RS1", 2), ("RS11", 2)]     # digits are not collapsed


def test_a_one_store_line_spelling_does_not_block_the_line_fold():
    rows = [L("s1", "Doobies Sour Tangie 7pk", "Sour Tangie", "Doobies", "7pk 3.5g", subtype="pack"),
            L("s2", "Doobies Sour Tangie 7pk", "Sour Tangie", "Doobies", "7pk 3.5g", subtype="pack"),
            L("s3", "Ruby Doobies Sour Tangie", "Sour Tangie", "Ruby Doobies", "7pk 3.5g",
              subtype="pack"),
            L("s4", "Sour Tangie Pre Rolls 7pk", "Sour Tangie", None, "7pk 3.5g", subtype="pack"),
            L("s5", "Sour Tangie 7pk", "Sour Tangie", None, "7pk 3.5g", subtype="pack")]
    entries = cb.propose("Ruby Farms", rows)["catalog"]["entries"]
    assert [(e["name"], e["support"]) for e in entries] == [("Doobies Sour Tangie", 4)]


def test_dosed_categories_keep_their_pack():
    rows = [L(s, "Electric Love Mandarin Rose 20pk 100mg", "Mandarin Rose", "Electric Love",
              "20pk 100mg", "edible", "gummy") for s in ("s1", "s2")]
    assert cb.propose("Ruby Farms", rows)["catalog"]["entries"][0]["variant"] == "20pk 100mg"


def test_consensus_line_is_stripped_from_a_strain():
    entries = by_name(cb.propose("Jetpacks", JETPACKS))
    e = entries["Powdered Donuts Championship Cake"]
    assert (e["strain"], e["product_line"], e["support"]) == ("Championship Cake", "Powdered Donuts", 2)


def test_single_store_products_and_merch_are_left_out():
    names = set(by_name(cb.propose("Jetpacks", JETPACKS)))
    assert not any("One Store" in n for n in names)
    assert not any("Grinder" in n for n in names)
    assert set(by_name(cb.propose("Jetpacks", JETPACKS, min_stores=1))) >= {"One Store Kush"}


def test_entries_are_stable_and_carry_store_names():
    a = cb.propose("Jetpacks", JETPACKS)["catalog"]["entries"]
    b = cb.propose("Jetpacks", list(reversed(JETPACKS)))["catalog"]["entries"]
    assert [e["external_id"] for e in a] == [e["external_id"] for e in b]
    e = by_name({"catalog": {"entries": a}})["FJ-Mini Afghani"]
    assert "fj mini afghani infused preroll 6g" in e["match_terms"]
    assert all("jetpacks" not in t for t in e["match_terms"])


def test_a_strains_cart_pod_and_aio_are_separate_products():
    vapes = [L(s, f"Jetpacks Afghani {fmt}", "Afghani", None, "1g", "vaporizers", sub)
             for s, fmt, sub in (("s1", "Cart", "cart"), ("s2", "510 Cart", "cart"),
                                 ("s3", "Pod", "pod"), ("s4", "Pod", "pod"),
                                 # the model said pod; the name says Cart, and the name wins
                                 ("s5", "Cart", "pod"))]
    entries = cb.propose("Jetpacks", vapes)["catalog"]["entries"]
    got = sorted((e["subtype"], e["support"]) for e in entries)
    assert got == [("cart", 3), ("pod", 2)]
    assert len({e["product_key"] for e in entries}) == 2


def test_input_rows_are_not_mutated():
    rows = [dict(r) for r in JETPACKS]
    cb.propose("Jetpacks", rows)
    assert rows == JETPACKS


def test_a_line_that_is_only_the_brand_is_no_line():
    runtz = [dict(L(s, "Runtz Lemon Candy Runtz 2pk", "Lemon Candy Runtz", line, "2pk 1.5g",
                    "preroll", "pack"), brand="Runtz")
             for s, line in (("s1", "Runtz"), ("s2", "RUNTZ"), ("s3", None))]
    entries = cb.propose("Runtz", runtz)["catalog"]["entries"]
    assert [(e["name"], e["product_line"], e["support"]) for e in entries] == \
        [("Lemon Candy Runtz", None, 3)]
    # A line that only contains the brand's name is a real line.
    pax = [dict(L(s, "PAX ERA Blue Dream Pod 1g", "Blue Dream", "PAX ERA", "1g", "vaporizers",
                  "pod"), brand="PAX") for s in ("s1", "s2")]
    assert cb.propose("PAX", pax)["catalog"]["entries"][0]["product_line"] == "PAX ERA"


def test_push_skips_an_empty_catalog_and_passes_via_http(monkeypatch, tmp_path):
    import brand_catalog
    import catalog_store

    papers = [dict(L(s, "Rolling Papers", "", None, "", "merch", "papers"), brand="RAW")
              for s in ("s1", "s2")]
    monkeypatch.setattr(cb, "fetch_listings", lambda: JETPACKS + papers)
    monkeypatch.setattr(catalog_store, "load_all", lambda *a, **k: {})
    monkeypatch.setattr(brand_catalog, "save", lambda cat: tmp_path / f"{cat['brand_slug']}.json")
    monkeypatch.setattr(brand_catalog, "ROOT", tmp_path)
    pushed = []
    monkeypatch.setattr(brand_catalog, "push", lambda cat, **kw: pushed.append((cat["brand_name"], kw)))
    monkeypatch.setattr(sys, "argv", ["catalog_bootstrap.py", "--top", "5", "--push", "--via-http"])
    cb.main()
    assert pushed == [("Jetpacks", {"via_http": True, "replace": False})]   # RAW: nothing to write


# --- push round trip -------------------------------------------------------
#
# Every push test runs twice: over DATABASE_URL, and over Supabase's REST API
# (brand_catalog.push(via_http=True)), with the REST calls answered from the same
# test database (conftest.RestOverPostgres). The same assertions must hold for both.

@pytest.fixture(params=["postgres", "http"])
def push(request, fresh_db, via_rest):
    import brand_catalog

    via_http = request.param == "http"
    if via_http:
        via_rest(fresh_db)
    return lambda doc, **kw: brand_catalog.push(doc, via_http=via_http, **kw)


def test_push_then_load_groups_by_product_key(push, fresh_db):
    import catalog_store

    cur = fresh_db.cursor()
    doc = cb.propose("Jetpacks", JETPACKS)["catalog"]
    push(doc)
    push(doc)                                # idempotent: updates in place
    cur.execute("SELECT count(*), count(DISTINCT product_key), min(source), max(support) "
                "FROM brand_catalog_entries")
    n, products, source, support = cur.fetchone()
    assert n == len(doc["entries"]) and source == "listings_bootstrap" and support == 4
    cats = catalog_store.load_from_cursor(cur)
    cat = catalog_store.for_brand(cats, "Jetpacks")
    assert cat["source_method"] == "listings_bootstrap"
    assert len({e["product_key"] for e in cat["entries"]}) == products


def test_push_is_additive_and_keeps_curation(push, fresh_db):
    """A re-fetch must not undo the admin's edits or resurrect what they took out."""
    cur = fresh_db.cursor()

    def entry(ext, name, variant):
        return {"external_id": ext, "product_external_id": "p-" + name, "name": name,
                "product_line": None, "category": "edible", "subtype": "gummy",
                "strain": name.title(), "variant": variant, "attributes": None,
                "match_terms": [name]}

    def snapshot():
        cur.execute("SELECT external_id, name, variant, is_active, match_terms, product_key, "
                    "source, support, last_seen_at FROM brand_catalog_entries ORDER BY external_id")
        entries = cur.fetchall()
        cur.execute("SELECT brand_slug, source_url, source_method, fetched_at, updated_at "
                    "FROM brand_catalogs")
        return entries, cur.fetchall()

    doc = {"brand_slug": "acme", "brand_name": "Acme", "source_url": "https://acme/products.json",
           "source_method": "shopify_products_json", "fetched_at": "2026-10-04T00:00:00Z",
           "entries": [entry("1", "island time", "10mg / 10 pack"),
                       entry("2", "hemp d9 thing", "5mg D9 / 12 pack"),
                       entry("3", "old flavour", "10mg")]}
    push(doc)
    # The admin curates: a size edited, an online-only product taken out.
    cur.execute("UPDATE brand_catalog_entries SET variant = '100mg' WHERE external_id = '1'")
    cur.execute("UPDATE brand_catalog_entries SET is_active = FALSE WHERE external_id = '2'")
    # The source re-lists the hemp product, drops "old flavour", adds a new one.
    doc["entries"] = [entry("1", "island time", "10mg / 10 pack"),
                      entry("2", "hemp d9 thing", "5mg D9 / 12 pack"),
                      entry("4", "new flavour", "10mg")]
    doc["entries"][0]["match_terms"] = ["island time gummies"]
    expected = {"inserted": 1, "refreshed": 2, "listed_again_but_inactive": 1, "deactivated": 1}
    before = snapshot()
    assert push(doc, dry_run=True) == expected             # a dry run counts the same...
    assert snapshot() == before                            # ...and writes nothing
    assert push(doc) == expected
    cur.execute("SELECT external_id, variant, is_active, match_terms, product_key "
                "FROM brand_catalog_entries ORDER BY external_id")
    got = {r[0]: r[1:] for r in cur.fetchall()}
    assert got["1"][0] == "100mg"                          # curated size kept
    assert sorted(got["1"][2]) == ["island time", "island time gummies"]   # terms merged
    assert got["1"][3] == "p-island time"                  # product_key backfilled
    assert got["2"][1] is False                            # not resurrected
    assert got["3"][1] is False and got["4"][1] is True    # vanished retired, new added

    # A bootstrap catalog never retires entries just because one week lacked them, and
    # a push without a source_url keeps the stored one.
    cur.execute("UPDATE brand_catalogs SET source_method = 'listings_bootstrap'")
    doc["source_method"] = "listings_bootstrap"
    doc["source_url"] = None
    doc["entries"] = [entry("4", "new flavour", "10mg")]
    assert push(doc)["deactivated"] == 0
    cur.execute("SELECT source_url FROM brand_catalogs")
    assert cur.fetchone()[0] == "https://acme/products.json"


def test_push_before_migration_0003_skips_its_columns(push, fresh_db, capsys):
    fresh_db.cursor().execute("ALTER TABLE brand_catalog_entries "
                              "DROP COLUMN product_key, DROP COLUMN source, DROP COLUMN support")
    doc = cb.propose("Jetpacks", JETPACKS)["catalog"]
    assert push(doc)["inserted"] == len(doc["entries"])
    assert push(doc)["refreshed"] == len(doc["entries"])
    assert "lacks product_key/source/support" in capsys.readouterr().out


def test_replace_retires_bootstrap_entries_the_new_proposal_drops(push, fresh_db):
    cur = fresh_db.cursor()
    doc = cb.propose("Jetpacks", JETPACKS)["catalog"]
    push(doc)
    first, second = doc["entries"][0]["external_id"], doc["entries"][1]["external_id"]
    cur.execute("UPDATE brand_catalog_entries SET verified_fields = '{\"strain\": \"Afghani\"}' "
                "WHERE external_id = %s", (first,))
    doc["entries"] = doc["entries"][2:]                  # the next proposal drops both

    assert push(doc)["deactivated"] == 0                 # additive unless asked
    cur.execute("SELECT count(*) FROM brand_catalog_entries WHERE is_active")
    before = cur.fetchone()[0]
    assert push(doc, replace=True, dry_run=True)["deactivated"] == 1
    cur.execute("SELECT count(*) FROM brand_catalog_entries WHERE is_active")
    assert cur.fetchone()[0] == before                   # a dry run writes nothing
    assert push(doc, replace=True)["deactivated"] == 1   # the verified one stays
    cur.execute("SELECT external_id, is_active FROM brand_catalog_entries")
    active = dict(cur.fetchall())
    assert active[first] is True and active[second] is False


def test_rebuild_reproposes_only_bootstrap_catalogs(monkeypatch, tmp_path):
    import brand_catalog
    import catalog_store

    monkeypatch.setattr(cb, "fetch_listings", lambda: JETPACKS)
    monkeypatch.setattr(catalog_store, "load_all", lambda *a, **k: {
        "jetpacks": {"brand_name": "Jetpacks", "source_method": "listings_bootstrap"},
        "ayrloom": {"brand_name": "Ayrloom", "source_method": "shopify_products_json"}})
    saved, pushed = [], []
    monkeypatch.setattr(brand_catalog, "save", lambda cat: saved.append(cat))
    monkeypatch.setattr(brand_catalog, "push", lambda cat, **kw: pushed.append((cat["brand_name"], kw)))
    monkeypatch.setattr(sys, "argv", ["catalog_bootstrap.py", "--rebuild", "--push", "--replace",
                                      "--dry-run"])
    cb.main()
    assert pushed == [("Jetpacks", {"dry_run": True, "via_http": False, "replace": True})]
    assert saved == []                                   # a dry run writes no file either
