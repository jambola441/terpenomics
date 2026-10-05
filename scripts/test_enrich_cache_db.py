"""The enrich cache in Postgres (ENRICH_CACHE=db): through enrich's own load/save, over
DATABASE_URL and over the REST API, against a throwaway database (TEST_DATABASE_URL)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import enrich  # noqa: E402
import enrich_cache_db  # noqa: E402


@pytest.fixture(params=["postgres", "rest"])
def cache_db(request, fresh_db, via_rest, monkeypatch):
    monkeypatch.setenv("ENRICH_CACHE", "db")
    if request.param == "rest":
        via_rest(fresh_db)
        monkeypatch.setenv("DB_VIA_HTTP", "1")
    else:
        monkeypatch.delenv("DB_VIA_HTTP", raising=False)
    monkeypatch.setattr(enrich_cache_db, "_loaded", {})
    return fresh_db.cursor()


def test_round_trip_through_enrich(cache_db):
    assert enrich._load_cache("store-a") == {}
    cache = {"sku1|3.5g": {"category": "flower", "strain": "Blue Dream", "ver": 7},
             "sku2|": {"category": "edible", "ver": 7, "jq": 1}}
    enrich._save_cache(cache, "store-a")
    enrich_cache_db._loaded.clear()                      # a later run, another machine
    assert enrich._load_cache("store-a") == cache
    assert enrich._load_cache("store-b") == {}           # one cache per store


def test_only_new_or_changed_entries_are_written(cache_db):
    cache = enrich._load_cache("s")
    cache.update({"a|": {"v": 1}, "b|": {"v": 1}})
    assert enrich_cache_db.save(cache, "s") == 2
    cache = enrich._load_cache("s")
    cache["b|"] = {"v": 2}
    cache["c|"] = {"v": 1}
    assert enrich_cache_db.save(cache, "s") == 2         # b changed, c new, a untouched
    assert enrich_cache_db.save(cache, "s") == 0
    cache_db.execute("SELECT cache_key, entry FROM enrich_cache WHERE slug = 's' ORDER BY 1")
    assert cache_db.fetchall() == [("a|", {"v": 1}), ("b|", {"v": 2}), ("c|", {"v": 1})]


def test_an_unreachable_cache_never_fails_the_run(monkeypatch, capsys):
    monkeypatch.setenv("ENRICH_CACHE", "db")
    monkeypatch.delenv("DB_VIA_HTTP", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    monkeypatch.setattr(enrich_cache_db, "_loaded", {})
    assert enrich._load_cache("s") == {}
    enrich._save_cache({"a|": {"v": 1}}, "s")            # reported, not raised
    err = capsys.readouterr().err
    assert "unreadable from Postgres" in err and "not saved to Postgres" in err


def test_files_stay_the_default(monkeypatch, tmp_path):
    monkeypatch.delenv("ENRICH_CACHE", raising=False)
    monkeypatch.setattr(enrich, "_CACHE_DIR", tmp_path)
    enrich._save_cache({"a|": {"v": 1}}, "s")
    assert (tmp_path / "s.json").exists() and enrich._load_cache("s") == {"a|": {"v": 1}}
