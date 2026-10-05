"""Tests for scrape.py's per-store verdicts — offline: the scraper and importer are stubbed."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scrape  # noqa: E402

STORE = {"slug": "grow-together-bk", "name": "Grow Together", "platform": "flowhub"}


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    """A scrape that writes a CSV, an import that succeeds, and a settable scrape meta."""
    out = tmp_path / "scrape.csv"
    out.write_text("name\nA\n")
    meta = {}
    monkeypatch.setattr(scrape, "OUT_DIR", tmp_path)
    monkeypatch.setattr(scrape, "csv_path", lambda slug, stamp=None: out)
    monkeypatch.setattr(scrape, "build_scraper_cmd", lambda *a, **k: ["true"])
    monkeypatch.setattr(scrape, "run_bounded", lambda cmd, timeout: 0)
    monkeypatch.setattr(scrape, "read_usage", lambda path: {})
    monkeypatch.setattr(scrape, "count_rows", lambda path: 810)
    monkeypatch.setattr(scrape, "run_import", lambda path, dry_run: (True, "imported"))
    monkeypatch.setattr(scrape, "read_scrape_meta", lambda path: meta)
    return meta


def test_a_partial_scrape_is_a_warning_not_a_failure(stubbed):
    stubbed.update(partial=True, collected=810, reported_total=861)
    res = scrape.run_one(STORE, dry_run=False)
    assert res["ok"] and res["stage"] == "import" and res["detail"] == "imported"
    assert res["warning"] == "partial scrape 810/861 products (nothing retired)"


def test_a_full_scrape_has_no_warning(stubbed):
    res = scrape.run_one(STORE, dry_run=False)
    assert res["ok"] and res["warning"] is None


def test_a_failed_import_still_fails(stubbed, monkeypatch):
    stubbed.update(partial=True, collected=810, reported_total=861)
    monkeypatch.setattr(scrape, "run_import", lambda path, dry_run: (False, "import exited 1"))
    res = scrape.run_one(STORE, dry_run=False)
    assert not res["ok"] and res["detail"] == "import exited 1" and res["warning"]


def test_scrape_only_partial_is_a_warning(stubbed):
    stubbed.update(partial=True, collected=810, reported_total=861)
    res = scrape.run_one(STORE, dry_run=False, scrape_only=True)
    assert res["ok"] and res["detail"] == "scraped" and res["warning"].startswith("partial scrape")
