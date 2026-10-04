"""Tests for catalog_bootstrap.py — unit tests offline; the push round-trip needs
TEST_DATABASE_URL (a throwaway database, schema recreated per test)."""

import os
import sys
import uuid
from pathlib import Path

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
    assert e["variant"] == "5pk 3g" and e["support"] == 2


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


# --- push round trip -------------------------------------------------------

TEST_DB = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")
def test_push_then_load_groups_by_product_key(monkeypatch):
    psycopg2 = pytest.importorskip("psycopg2")
    import brand_catalog
    import catalog_store
    import db_migrate

    root = Path(__file__).resolve().parent.parent
    conn = psycopg2.connect(TEST_DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    cur.execute((root / "db" / "schema" / "pipeline.sql").read_text())
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    assert db_migrate.main(["--run"]) == 0

    doc = cb.propose("Jetpacks", JETPACKS)["catalog"]
    brand_catalog.push(doc)
    brand_catalog.push(doc)                  # idempotent: updates in place
    cur.execute("SELECT count(*), count(DISTINCT product_key), min(source), max(support) "
                "FROM brand_catalog_entries")
    n, products, source, support = cur.fetchone()
    assert n == len(doc["entries"]) and source == "listings_bootstrap" and support == 4
    cats = catalog_store.load_from_cursor(cur)
    cat = catalog_store.for_brand(cats, "Jetpacks")
    assert cat["source_method"] == "listings_bootstrap"
    assert len({e["product_key"] for e in cat["entries"]}) == products
    conn.close()



@pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")
def test_push_is_additive_and_keeps_curation(monkeypatch):
    """A re-fetch must not undo the admin's edits or resurrect what they took out."""
    psycopg2 = pytest.importorskip("psycopg2")
    import brand_catalog
    import db_migrate

    root = Path(__file__).resolve().parent.parent
    conn = psycopg2.connect(TEST_DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    cur.execute((root / "db" / "schema" / "pipeline.sql").read_text())
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    assert db_migrate.main(["--run"]) == 0

    def entry(ext, name, variant):
        return {"external_id": ext, "product_external_id": "p-" + name, "name": name,
                "product_line": None, "category": "edible", "subtype": "gummy",
                "strain": name.title(), "variant": variant, "attributes": None,
                "match_terms": [name]}

    doc = {"brand_slug": "acme", "brand_name": "Acme", "source_url": "https://acme/products.json",
           "source_method": "shopify_products_json", "fetched_at": "2026-10-04T00:00:00Z",
           "entries": [entry("1", "island time", "10mg / 10 pack"),
                       entry("2", "hemp d9 thing", "5mg D9 / 12 pack"),
                       entry("3", "old flavour", "10mg")]}
    brand_catalog.push(doc)
    # The admin curates: a size edited, an online-only product taken out.
    cur.execute("UPDATE brand_catalog_entries SET variant = '100mg' WHERE external_id = '1'")
    cur.execute("UPDATE brand_catalog_entries SET is_active = FALSE WHERE external_id = '2'")
    # The source re-lists the hemp product, drops "old flavour", adds a new one.
    doc["entries"] = [entry("1", "island time", "10mg / 10 pack"),
                      entry("2", "hemp d9 thing", "5mg D9 / 12 pack"),
                      entry("4", "new flavour", "10mg")]
    doc["entries"][0]["match_terms"] = ["island time gummies"]
    counts = brand_catalog.push(doc)
    assert counts == {"inserted": 1, "refreshed": 2, "listed_again_but_inactive": 1,
                      "deactivated": 1}
    cur.execute("SELECT external_id, variant, is_active, match_terms, product_key "
                "FROM brand_catalog_entries ORDER BY external_id")
    got = {r[0]: r[1:] for r in cur.fetchall()}
    assert got["1"][0] == "100mg"                          # curated size kept
    assert sorted(got["1"][2]) == ["island time", "island time gummies"]   # terms merged
    assert got["1"][3] == "p-island time"                  # product_key backfilled
    assert got["2"][1] is False                            # not resurrected
    assert got["3"][1] is False and got["4"][1] is True    # vanished retired, new added

    # A bootstrap catalog never retires entries just because one week lacked them.
    cur.execute("UPDATE brand_catalogs SET source_method = 'listings_bootstrap'")
    doc["source_method"] = "listings_bootstrap"
    doc["entries"] = [entry("4", "new flavour", "10mg")]
    assert brand_catalog.push(doc)["deactivated"] == 0
    conn.close()
