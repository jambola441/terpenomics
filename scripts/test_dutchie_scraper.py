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


# ── product links ────────────────────────────────────────────────────────────

def test_product_url_fills_the_slug_into_the_stores_template():
    t = "https://hiinyc.com/stores/hii-williamsburg/product/{cname}"
    assert dutchie.product_url(t, "elements-papers") == "https://hiinyc.com/stores/hii-williamsburg/product/elements-papers"


def test_product_url_is_blank_without_a_template_or_a_slug():
    assert dutchie.product_url("", "elements-papers") == ""
    assert dutchie.product_url("https://x.test/product/{cname}", "") == ""


def test_product_url_escapes_what_a_slug_should_never_hold():
    assert dutchie.product_url("https://x.test/?p={cname}", "a b/c") == "https://x.test/?p=a%20b%2Fc"


def test_rows_carry_the_product_url():
    p = {"_id": "1", "Name": "Pipe", "cName": "pipe", "Options": ["N/A", "1g"], "Prices": [5, 9], "type": "Accessories"}
    rows = dutchie.normalise_gql(p, "store", "now", "https://x.test/product/{cname}")
    assert [r["product_url"] for r in rows] == ["https://x.test/product/pipe"] * 2
    assert dutchie.normalise_gql(p, "store", "now")[0]["product_url"] == ""


def test_every_dutchie_store_template_is_well_formed():
    import json
    stores = json.loads((Path(__file__).resolve().parent.parent / "dispensaries.json").read_text())
    for s in stores:
        t = s.get("product_url_template")
        if t:
            assert s["platform"] == "dutchie_graphql" and t.startswith("https://") and t.count("{cname}") == 1, s["slug"]
