"""
Tests for the PR-preview database guard in database.py.

The guard is what stops a Render preview of an un-reviewed PR branch from
reading and writing the production database. See PREVIEWS.md.

Run: pytest tests/test_preview_db.py -v
"""

import importlib
import sys

import pytest

PROD_URL = "postgresql://prod:secret@prod.example.com:5432/postgres"
PREVIEW_URL = "postgresql://preview:secret@preview.example.com:5432/postgres"

# Env vars the guard reads, cleared before each case so the developer's own
# shell (or a .env file) can't leak into the result.
MANAGED = (
    "IS_PULL_REQUEST",
    "DATABASE_URL",
    "PREVIEW_DATABASE_URL",
    "PREVIEW_ALLOW_PROD_DB",
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_USER",
    "SUPABASE_DB_PASSWORD",
)


@pytest.fixture
def db(monkeypatch):
    """Import database.py fresh with a controlled environment.

    database.py builds a SQLAlchemy engine at import time. It never connects,
    but create_engine does resolve a driver — so we import against sqlite to
    keep this test free of a postgres driver, then set the postgres URLs the
    cases actually assert on.
    """
    for key in MANAGED:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    sys.modules.pop("database", None)
    module = importlib.import_module("database")

    # The import runs _load_dotenv(), so a developer's local .env could have
    # repopulated these. Clear them again so cases start from a known state.
    for key in ("IS_PULL_REQUEST", "PREVIEW_DATABASE_URL", "PREVIEW_ALLOW_PROD_DB"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_URL", PROD_URL)
    yield module
    sys.modules.pop("database", None)


def test_production_uses_database_url(db, monkeypatch):
    monkeypatch.delenv("IS_PULL_REQUEST", raising=False)
    assert db._build_database_url() == PROD_URL


def test_is_pull_request_false_is_production(db, monkeypatch):
    monkeypatch.setenv("IS_PULL_REQUEST", "false")
    assert not db.is_pr_preview()
    assert db._build_database_url() == PROD_URL


def test_preview_prefers_preview_database_url(db, monkeypatch):
    monkeypatch.setenv("IS_PULL_REQUEST", "true")
    monkeypatch.setenv("PREVIEW_DATABASE_URL", PREVIEW_URL)
    assert db.is_pr_preview()
    assert db._build_database_url() == PREVIEW_URL


def test_preview_without_preview_url_refuses_to_start(db, monkeypatch):
    monkeypatch.setenv("IS_PULL_REQUEST", "true")
    with pytest.raises(RuntimeError) as excinfo:
        db._build_database_url()
    assert "PREVIEW_DATABASE_URL" in str(excinfo.value)
    # The production URL must never appear in the failure path.
    assert PROD_URL not in str(excinfo.value)


def test_preview_escape_hatch_falls_back_to_production(db, monkeypatch):
    monkeypatch.setenv("IS_PULL_REQUEST", "true")
    monkeypatch.setenv("PREVIEW_ALLOW_PROD_DB", "true")
    assert db._build_database_url() == PROD_URL


def test_preview_flag_is_case_insensitive(db, monkeypatch):
    monkeypatch.setenv("IS_PULL_REQUEST", "TRUE")
    monkeypatch.setenv("PREVIEW_DATABASE_URL", PREVIEW_URL)
    assert db._build_database_url() == PREVIEW_URL


def test_blank_preview_url_is_treated_as_unset(db, monkeypatch):
    monkeypatch.setenv("IS_PULL_REQUEST", "true")
    monkeypatch.setenv("PREVIEW_DATABASE_URL", "   ")
    with pytest.raises(RuntimeError):
        db._build_database_url()
