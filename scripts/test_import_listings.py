"""
Integration tests for import_listings.py against a real Postgres.

Skipped unless TEST_DATABASE_URL points at a throwaway database — every test drops
and recreates the public schema from db/schema/pipeline.sql. Never point it at
anything you care about. Jev is always faked here; nothing touches the network.

Every test runs twice: over DATABASE_URL, and over Supabase's REST API (--via-http),
with the REST calls answered from the same database (conftest.RestOverPostgres).

    TEST_DATABASE_URL=postgresql://postgres@localhost:5432/terp_test \\
        python -m pytest scripts/test_import_listings.py -q
"""

import csv
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")

psycopg2 = pytest.importorskip("psycopg2")

import catalog_match  # noqa: E402
import import_listings  # noqa: E402
import jev  # noqa: E402
from scraper_common import CSV_COLUMNS  # noqa: E402

SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema" / "pipeline.sql"
STORE = "test-store"


@pytest.fixture(params=["postgres", "rest"])
def db(request, monkeypatch, tmp_path, via_rest):
    conn = psycopg2.connect(TEST_DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    cur.execute(SCHEMA.read_text())
    cur.execute(
        "INSERT INTO dispensaries (id, name, slug, pos_type, created_at, updated_at) "
        "VALUES (%s, 'Test Store', %s, 'none', now(), now())", (str(uuid.uuid4()), STORE))
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    if request.param == "rest":
        via_rest(conn)
        monkeypatch.setenv("DB_VIA_HTTP", "1")

        def no_postgres(url):
            raise AssertionError("the REST run opened a Postgres connection")
        monkeypatch.setattr(import_listings, "PostgresStore", no_postgres)
    else:
        monkeypatch.delenv("DB_VIA_HTTP", raising=False)
    monkeypatch.setattr(catalog_match, "CACHE_DIR", tmp_path / "match_cache")
    # No real Jev: a test that wants it installs a fake.
    monkeypatch.setattr(jev, "available", lambda: False)
    yield cur
    conn.close()


def write_csv(tmp_path, rows, name="scrape.csv"):
    path = tmp_path / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow({"dispensary_slug": STORE, "in_stock": "TRUE", **r})
    return str(path)


def run(tmp_path, rows, *extra, name="scrape.csv"):
    return import_listings.main(["--csv", write_csv(tmp_path, rows, name), *extra])


def listings(cur, active_only=True):
    cur.execute(f"""SELECT sku, variant, scraped_brand, scraped_category, subtype, strain,
                           product_line, catalog_entry_id, catalog_match_method,
                           catalog_match_confidence, is_active, price_cents
                    FROM listings {'WHERE is_active' if active_only else ''} ORDER BY sku, variant""")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def row(sku, name, **kw):
    base = {"sku": sku, "name": name, "brand": "Acme", "category": "flower",
            "variant": "3.5g", "price_cents": "4000", "subtype": "flower", "strain": ""}
    base.update(kw)
    return base


def add_catalog(cur, entries, brand="Acme"):
    cur.execute("INSERT INTO brand_catalogs (brand_slug, brand_name, source_method) "
                "VALUES (%s, %s, 'manual') RETURNING id", (brand.lower(), brand))
    cid = cur.fetchone()[0]
    ids = []
    for e in entries:
        cur.execute("""INSERT INTO brand_catalog_entries
                       (catalog_id, external_id, name, product_line, category, subtype, strain, variant)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (cid, e.get("external_id"), e["name"], e.get("product_line"), e.get("category"),
                     e.get("subtype"), e.get("strain"), e.get("variant")))
        ids.append(str(cur.fetchone()[0]))
    return ids


# ---------------------------------------------------------------------------

def test_insert_then_update(db, tmp_path):
    assert run(tmp_path, [row("A", "Acme Blue Dream", strain="Blue Dream"),
                          row("B", "Acme OG Kush", strain="OG Kush")]) == 0
    assert run(tmp_path, [row("A", "Acme Blue Dream", strain="Blue Dream", price_cents="3500"),
                          row("B", "Acme OG Kush", strain="OG Kush")], name="2.csv") == 0
    got = {r["sku"]: r for r in listings(db)}
    assert got["A"]["price_cents"] == 3500 and got["B"]["strain"] == "OG Kush"


def test_failed_enrichment_keeps_stored_identity(db, tmp_path):
    run(tmp_path, [row("A", "Acme Blue Dream", strain="Blue Dream", product_line="Gold")])
    run(tmp_path, [row("A", "Acme Blue Dream", strain="", subtype="other", product_line="",
                       enrich_failed="True")], name="2.csv")
    [r] = listings(db)
    assert (r["strain"], r["subtype"], r["product_line"]) == ("Blue Dream", "flower", "Gold")


def test_failed_enrichment_adopts_the_stored_variant(db, tmp_path):
    """The model normalised '1/8oz' to '3.5g'; a run where it failed arrives raw and
    must update the same listing rather than insert a twin and retire the original."""
    run(tmp_path, [row("A", "Acme Blue Dream", strain="Blue Dream", variant="3.5g")])
    run(tmp_path, [row("A", "Acme Blue Dream", variant="1/8oz", enrich_failed="True")],
        name="2.csv")
    all_rows = listings(db, active_only=False)
    assert len(all_rows) == 1 and all_rows[0]["is_active"] and all_rows[0]["variant"] == "3.5g"


def test_unenriched_new_listing_still_imports(db, tmp_path):
    run(tmp_path, [row("N", "Acme New Thing", strain="", subtype="other", enrich_failed="True")])
    [r] = listings(db)
    assert r["subtype"] == "other"


def test_stale_marking_retires_absent_rows_and_leaves_inactive_ones_alone(db, tmp_path):
    run(tmp_path, [row(s, f"Acme {s}") for s in "ABCD"])
    run(tmp_path, [row(s, f"Acme {s}") for s in "ABC"], name="2.csv")
    assert {r["sku"] for r in listings(db)} == {"A", "B", "C"}
    db.execute("SELECT updated_at FROM listings WHERE sku='D'")
    before = db.fetchone()[0]
    run(tmp_path, [row(s, f"Acme {s}") for s in "ABC"], name="3.csv")
    db.execute("SELECT updated_at FROM listings WHERE sku='D'")
    assert db.fetchone()[0] == before   # an inactive row is not re-touched every day


def test_partial_scrape_guard(db, tmp_path):
    run(tmp_path, [row(f"S{i}", f"Acme {i}") for i in range(10)])
    run(tmp_path, [row(f"S{i}", f"Acme {i}") for i in range(4)], name="2.csv")
    assert len(listings(db)) == 10      # 4 < 0.5 x 10: looks partial, nothing retired


def test_full_sku_change_retires_the_old_menu(db, tmp_path):
    """A platform migration replaces every SKU. The guard used to count active rows
    after the upsert, so the new SKUs inflated the denominator and the old menu was
    never retired."""
    run(tmp_path, [row(f"OLD{i}", f"Acme {i}") for i in range(10)])
    run(tmp_path, [row(f"NEW{i}", f"Acme {i}") for i in range(6)], name="2.csv")
    assert {r["sku"][:3] for r in listings(db)} == {"NEW"}


def test_rows_without_sku_are_upserted_not_duplicated(db, tmp_path):
    run(tmp_path, [row("", "Acme Mystery Item")])
    run(tmp_path, [row("", "Acme Mystery Item")], name="2.csv")
    assert len(listings(db, active_only=False)) == 1


def test_brand_aliases_applied_at_import(db, tmp_path):
    run(tmp_path, [row("A", "Stiiizy Pod", brand="Stiiizy")])
    assert listings(db)[0]["scraped_brand"] == "STIIIZY"


def test_empty_csv_and_unknown_store_are_failures(db, tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text(",".join(CSV_COLUMNS) + "\n")
    assert import_listings.main(["--csv", str(path)]) == 3
    p = write_csv(tmp_path, [row("A", "x")], "unknown.csv").replace(STORE, "nope")
    Path(p).write_text(Path(p).read_text().replace(STORE, "nope"))
    assert import_listings.main(["--csv", p]) == 2


# --- catalogs ---------------------------------------------------------------

def test_exact_catalog_match_overlays_identity(db, tmp_path):
    [eid] = add_catalog(db, [{"name": "acme blue dream", "category": "flower",
                              "strain": "Blue Dream", "product_line": "Gold", "variant": "3.5g"}])
    run(tmp_path, [row("A", "Acme Blue Dream", strain="Blue Dreem", product_line="")])
    [r] = listings(db)
    assert r["catalog_match_method"] == "exact" and str(r["catalog_entry_id"]) == eid
    assert (r["strain"], r["product_line"]) == ("Blue Dream", "Gold")


def test_a_mistyped_dose_is_stored_with_its_catalog_size(db, tmp_path):
    """`variant` stays as the store typed it (it is part of the row's key); `size`,
    which product pages group on, takes the catalog's when the store's is a typo."""
    add_catalog(db, [{"name": "balance yuzu lemon", "category": "edible", "subtype": "gummy",
                      "strain": "Balance Yuzu Lemon", "product_line": "Gummies",
                      "variant": "20pk 100mg"}], brand="Camino")
    gummy = {"brand": "Camino", "category": "edible", "subtype": "gummy"}
    run(tmp_path, [row("A", "Balance Yuzu Lemon", variant="50mg",
                       description="5mg THC : 5mg CBD per piece - 100mg THC per package", **gummy),
                   row("B", "Balance Yuzu Lemon", variant="100mg", **gummy),
                   row("C", "Acme Blue Dream", strain="Blue Dream")])
    db.execute("SELECT sku, variant, size FROM listings ORDER BY sku")
    assert db.fetchall() == [("A", "50mg", "100mg"), ("B", "100mg", "100mg"), ("C", "3.5g", "3.5g")]


def test_only_a_trusted_match_corrects_a_size():
    entry = {"id": "e1", "category": "edible", "variant": "20pk 100mg", "product_key": "k1",
             "is_active": True}
    catalogs = {"camino": {"brand_name": "Camino", "entries": [entry]}}
    typo = {"variant": "50mg", "scraped_name": "Balance | Yuzu Lemon | 20pk", "catalog_entry_id": "e1",
            "description": "100mg THC : 100mg CBD per package"}
    recs = [{**typo, "catalog_match_method": "exact"},
            {**typo, "catalog_match_method": "jev_review"},
            {"variant": "3.5g", "scraped_name": "Kush", "catalog_entry_id": None, "catalog_match_method": None}]
    assert import_listings.assign_sizes(recs, catalogs) == 1
    assert [r["size"] for r in recs] == ["100mg", "50mg", "3.5g"]
    assert import_listings.assign_sizes([dict(recs[0])], {}) == 0      # --no-catalog: the store's size


def test_substring_without_jev_is_recorded_but_not_overlaid(db, tmp_path):
    add_catalog(db, [{"name": "blue dream", "category": "flower", "strain": "Blue Dream",
                      "product_line": "Gold"}])
    run(tmp_path, [row("A", "Acme | Blue Dream | 3.5g", strain="Blue Dreem")])
    [r] = listings(db)
    assert r["catalog_match_method"] == "substring"
    assert (r["strain"], r["product_line"]) == ("Blue Dreem", None)


def _fake_jev(monkeypatch, probability):
    """Jev answers the first product option with `probability`, the rest to none."""
    def ask_many(jobs, workers=8, usage=None, model=None, on_error=None):
        out = []
        for state, questions in jobs:
            options = list(questions["product"].criteria)
            pick = options[1]
            out.append(jev.Result(
                answers={"product": {"type": "choice", "choice": pick,
                                     "probabilities": {pick: probability, "none": 1 - probability}}},
                model="fake", input_tokens=10, cost_usd=0.0, latency_s=0.0))
        return out
    monkeypatch.setattr(jev, "available", lambda: True)
    monkeypatch.setattr(jev, "ask_many", ask_many)


def test_confident_jev_match_overlays(db, tmp_path, monkeypatch):
    _fake_jev(monkeypatch, 0.95)
    add_catalog(db, [{"name": "blue dream", "category": "flower", "strain": "Blue Dream",
                      "product_line": "Gold", "subtype": "smalls"}])
    run(tmp_path, [row("A", "Acme | Blue Dream Smalls | 3.5g", strain="Blue Dream Smalls")])
    [r] = listings(db)
    assert r["catalog_match_method"] == "jev" and r["catalog_match_confidence"] == pytest.approx(0.95)
    assert (r["strain"], r["product_line"], r["subtype"]) == ("Blue Dream", "Gold", "smalls")


def test_unsure_jev_match_goes_to_review_without_overlay(db, tmp_path, monkeypatch):
    _fake_jev(monkeypatch, 0.6)
    add_catalog(db, [{"name": "blue dream", "category": "flower", "strain": "Blue Dream",
                      "product_line": "Gold"}])
    run(tmp_path, [row("A", "Acme | Blue Dream | 3.5g", strain="Blue Dreem")])
    [r] = listings(db)
    assert r["catalog_match_method"] == "jev_review" and r["catalog_entry_id"] is not None
    assert (r["strain"], r["product_line"]) == ("Blue Dreem", None)


def test_a_format_word_in_the_name_beats_the_entrys_subtype(db, tmp_path):
    """A bootstrap merged a strain's cart and pod; the listing that says Cart stays a cart."""
    add_catalog(db, [{"name": "acme blue dream cart", "category": "vaporizers",
                      "subtype": "pod", "strain": "Blue Dream", "variant": "1g"}])
    run(tmp_path, [row("A", "Acme Blue Dream Cart", category="vaporizers", subtype="pod",
                       variant="1g", strain="Blue Dream")])
    [r] = listings(db)
    assert r["catalog_match_method"] == "exact" and r["subtype"] == "cart"


def test_a_preroll_keeps_no_subtype(db, tmp_path):
    """Pass A still answers one, and an entry or a person may have given one before the
    rule; none of them is written."""
    import verification
    add_catalog(db, [{"name": "acme blue dream 2pk", "category": "preroll", "subtype": "pack",
                      "strain": "Blue Dream", "variant": "1g"}])
    rows = [row("A", "Acme Blue Dream 2pk", category="preroll", subtype="infused", variant="1g",
                strain="Blue Dream"),
            row("B", "Acme OG Kush Infused", category="preroll", subtype="infused", variant="1g",
                strain="OG Kush"),
            row("C", "Acme OG Kush", strain="OG Kush")]
    run(tmp_path, rows)
    got = {r["sku"]: r for r in listings(db)}
    assert got["A"]["catalog_match_method"] == "exact"
    assert [got[k]["subtype"] for k in "ABC"] == [None, None, "flower"]
    claim = verification.claim({"subtype": "infused"}, "Acme OG Kush Infused", "tester")
    db.execute("UPDATE listings SET verified_fields=%s WHERE sku='B'", (psycopg2.extras.Json(claim),))
    run(tmp_path, rows, name="2.csv")
    assert {r["sku"]: r["subtype"] for r in listings(db)}["B"] is None


def test_migration_0007_clears_stored_preroll_subtypes(db, tmp_path):
    add_catalog(db, [{"name": "acme blue dream 2pk", "category": "preroll", "subtype": "pack"},
                     {"name": "acme blue dream cart", "category": "vaporizers", "subtype": "cart"}])
    run(tmp_path, [row("A", "Acme OG Kush Infused", category="preroll", variant="1g"),
                   row("C", "Acme OG Kush")])
    db.execute("UPDATE listings SET subtype = 'infused' WHERE sku = 'A'")   # stored before the rule
    migration = Path(__file__).resolve().parent.parent / "db/migrations/0007_preroll_no_subtype.sql"
    db.execute(migration.read_text())
    db.execute(migration.read_text())                                       # idempotent
    assert {r["sku"]: r["subtype"] for r in listings(db)} == {"A": None, "C": "flower"}
    db.execute("SELECT category, subtype FROM brand_catalog_entries ORDER BY 1")
    assert db.fetchall() == [("preroll", None), ("vaporizers", "cart")]


def test_catalogs_load_over_database_url_when_rest_is_not_configured(db, monkeypatch):
    """The scrape worker has DATABASE_URL and no Supabase REST credentials."""
    import catalog_store
    add_catalog(db, [{"name": "acme blue dream", "category": "flower", "strain": "Blue Dream"}])
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    cats = catalog_store.load_all("db")
    assert [e["name"] for e in catalog_store.for_brand(cats, "Acme")["entries"]] == ["acme blue dream"]


def test_masked_catalog_strain_is_not_copied(db, tmp_path):
    add_catalog(db, [{"name": "acme alaskan thunder fu*k", "category": "flower",
                      "strain": "Alaskan Thunder Fu*K"}])
    run(tmp_path, [row("A", "Acme Alaskan Thunder Fu*k", strain="Alaskan Thunder Fuck")])
    [r] = listings(db)
    assert r["catalog_match_method"] == "exact" and r["strain"] == "Alaskan Thunder Fuck"


def test_manual_match_survives_reimport(db, tmp_path):
    eid, other = add_catalog(db, [
        {"name": "manual pick", "category": "flower", "strain": "Picked", "product_line": "Hand"},
        {"name": "acme blue dream", "category": "flower", "strain": "Blue Dream"}])
    run(tmp_path, [row("A", "Acme Blue Dream")])
    db.execute("UPDATE listings SET catalog_entry_id=%s, catalog_match_method='manual'", (eid,))
    run(tmp_path, [row("A", "Acme Blue Dream")], name="2.csv")
    [r] = listings(db)
    assert r["catalog_match_method"] == "manual" and str(r["catalog_entry_id"]) == eid
    assert (r["strain"], r["product_line"]) == ("Picked", "Hand")


def test_human_claim_beats_the_catalog(db, tmp_path):
    import verification
    add_catalog(db, [{"name": "acme blue dream", "category": "flower", "strain": "Blue Dream"}])
    run(tmp_path, [row("A", "Acme Blue Dream")])
    claim = verification.claim({"strain": "Blue Dream #4"}, "Acme Blue Dream", "tester")
    db.execute("UPDATE listings SET verified_fields=%s", (psycopg2.extras.Json(claim),))
    run(tmp_path, [row("A", "Acme Blue Dream")], name="2.csv")
    assert listings(db)[0]["strain"] == "Blue Dream #4"


def test_no_catalog_flag_leaves_match_columns_alone(db, tmp_path):
    [eid] = add_catalog(db, [{"name": "acme blue dream", "category": "flower"}])
    run(tmp_path, [row("A", "Acme Blue Dream")])
    run(tmp_path, [row("A", "Acme Blue Dream")], "--no-catalog", name="2.csv")
    assert str(listings(db)[0]["catalog_entry_id"]) == eid


def test_partial_scrape_meta_refreshes_but_retires_nothing(db, tmp_path):
    import json
    run(tmp_path, [row(s, f"Acme {s}") for s in "ABCDEF"])
    path = write_csv(tmp_path, [row(s, f"Acme {s}", price_cents="1") for s in "ABCD"], "partial.csv")
    Path(path).with_suffix(".meta.json").write_text(
        json.dumps({"reported_total": 6, "collected": 4, "partial": True}))
    assert import_listings.main(["--csv", path]) == 0
    got = {r["sku"]: r for r in listings(db)}
    assert set(got) == set("ABCDEF")            # nothing retired
    assert got["A"]["price_cents"] == 1         # what arrived was refreshed


def test_column_widths_match_the_schema():
    """COLUMN_WIDTHS mirrors the listings table; a widened column must widen it too."""
    table = SCHEMA.read_text().split("CREATE TABLE IF NOT EXISTS listings (")[1].split(");")[0]
    widths = {m.group(1): int(m.group(2))
              for m in re.finditer(r"^\s*(\w+) character varying\((\d+)\)", table, re.M)}
    assert widths == import_listings.COLUMN_WIDTHS


def test_overlong_values_are_cut_to_fit():
    promo = ("Get ready for a hauntingly delicious experience " * 8).strip()   # 383 chars
    rec = import_listings.build_record(
        {"name": promo, "sku": "S1", "variant": "10pk", "brand": "Camino"}, "d1",
        import_listings.utcnow())
    cuts = import_listings.fit_columns([rec])
    assert len(rec["scraped_name"]) <= 300 and rec["scraped_name"] == promo[:300].rstrip()
    assert cuts == ["S1: scraped_name was 383 chars"]
    assert import_listings.fit_columns([rec]) == []                     # idempotent


def test_an_overlong_name_no_longer_fails_the_store(db, tmp_path):
    # Hii NYC, 2026-10-05: one promo paragraph in a name failed both stores' imports.
    promo = "Get ready for a hauntingly delicious experience with Camino Sours " * 6
    assert run(tmp_path, [row("A", promo, category="edible", variant="100mg"),
                          row("B", "Acme OG Kush", strain="OG Kush")]) == 0
    db.execute("SELECT sku, length(scraped_name) FROM listings ORDER BY sku")
    assert db.fetchall() == [("A", 300), ("B", len("Acme OG Kush"))]
