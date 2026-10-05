"""Tests for the Dutchie scraper's first-page refusal handling — offline, fake sessions."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
pytest.importorskip("curl_cffi")

_PATH = Path(__file__).resolve().parent.parent / "prototypes" / "dutchie-scraper" / "scrape_graphql.py"
_spec = importlib.util.spec_from_file_location("scrape_graphql", _PATH)
dutchie = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dutchie)

PAGE = {"data": {"filteredProducts": {"products": [], "queryInfo": {"totalCount": 0}}}}


class Resp:
    def __init__(self, status, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers, self.text = status, body, headers or {}, text

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(headers)
        return self.responses.pop(0)


CF_403 = Resp(403, headers={"server": "cloudflare", "cf-ray": "abc-SEA", "cf-mitigated": "challenge"},
              text="<html>Just a moment...</html>")


@pytest.fixture
def fallback(monkeypatch):
    """The session the retry opens, under the other fingerprint."""
    made = {}

    def session(impersonate):
        made["impersonate"] = impersonate
        return made["session"]
    monkeypatch.setattr(dutchie.cffi_req, "Session", session)
    monkeypatch.setattr(dutchie.time, "sleep", lambda s: None)
    return made


def test_first_page_needs_no_retry_when_it_answers():
    assert dutchie._first_page(Session(Resp(200, PAGE)), "id1") == PAGE


def test_a_refused_first_page_is_retried_under_another_fingerprint(fallback):
    fallback["session"] = Session(Resp(200, PAGE))
    assert dutchie._first_page(Session(CF_403), "id1") == PAGE
    assert fallback["impersonate"] == dutchie.FALLBACK_IMPERSONATE
    assert "User-Agent" not in fallback["session"].calls[0]


def test_refused_twice_says_who_refused(fallback):
    fallback["session"] = Session(Resp(403, headers={"server": "nginx"}, text='{"error":"forbidden"}'))
    with pytest.raises(RuntimeError) as err:
        dutchie._first_page(Session(CF_403), "id1")
    msg = str(err.value)
    assert "server=cloudflare cf-ray=abc-SEA cf-mitigated=challenge" in msg
    assert "server=nginx" in msg and "forbidden" in msg
