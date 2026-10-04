"""db_http.count: a HEAD request that reads a row total and never a row."""

import io
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_http  # noqa: E402


class _Response:
    def __init__(self, content_range):
        self.headers = {"Content-Range": content_range}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")


def _capture(monkeypatch, content_range="*/7"):
    sent = []

    def fake_urlopen(req, timeout):
        sent.append(req)
        return _Response(content_range)

    monkeypatch.setattr(db_http.urllib.request, "urlopen", fake_urlopen)
    return sent


def test_count_is_a_head_request_with_the_service_key(env, monkeypatch):
    sent = _capture(monkeypatch, "*/7")
    assert db_http.count("customers") == 7
    req = sent[0]
    assert req.get_method() == "HEAD"
    assert req.full_url == "https://ref.supabase.co/rest/v1/customers?select=*"
    assert req.get_header("Prefer") == "count=exact"
    assert req.get_header("Apikey") == "service-key"


def test_count_as_anon_uses_the_public_key_and_a_filter(env, monkeypatch):
    sent = _capture(monkeypatch, "*/0")
    assert db_http.count("listings", "is_active=is.true", as_anon=True) == 0
    req = sent[0]
    assert req.full_url == "https://ref.supabase.co/rest/v1/listings?select=*&is_active=is.true"
    assert req.get_header("Apikey") == "anon-key"
    assert req.get_header("Authorization") == "Bearer anon-key"


def test_count_without_a_total_is_none(env, monkeypatch):
    _capture(monkeypatch, "")
    assert db_http.count("customers") is None


def test_count_reports_the_status_of_a_refused_request(env, monkeypatch):
    def refuse(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

    monkeypatch.setattr(db_http.urllib.request, "urlopen", refuse)
    with pytest.raises(db_http.DbHttpError, match="401"):
        db_http.count("customers", as_anon=True)


def test_count_as_anon_needs_the_anon_key(env, monkeypatch):
    monkeypatch.delenv("SUPABASE_ANON_KEY")
    with pytest.raises(db_http.DbHttpError, match="SUPABASE_ANON_KEY"):
        db_http.count("customers", as_anon=True)
