"""Tests for product_urls — offline, fake sessions."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import product_urls  # noqa: E402


class Resp:
    def __init__(self, body=None, text=""):
        self._body, self.text = body, text

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class Session:
    def __init__(self, *responses):
        self.responses, self.posts = list(responses), []

    def get(self, url, timeout=None):
        return self.responses.pop(0)

    def post(self, url, headers=None, timeout=None, json=None):
        self.posts.append(json)
        return self.responses.pop(0)


def fake(monkeypatch, *responses):
    session = Session(*responses)
    monkeypatch.setattr(product_urls, "_session", lambda: session)
    return session


SITEMAP = {"sitemap": "https://s.test/sitemap.xml",
           "template": "https://s.test/product/{brand_slug}-{name_slug}-for-sale"}
XML = ("<urlset><url><loc>https://s.test/product/acme-blue-dream-1g-for-sale</loc></url>"
       "<url><loc>https://s.test/product/-lighter-for-sale</loc></url></urlset>")


def test_slugify():
    assert product_urls.slugify('Blue Dream | 1 1/4" ') == "blue-dream-1-1-4"


def test_sitemap_resolver_keeps_only_urls_the_site_lists(monkeypatch):
    fake(monkeypatch, Resp(text=XML))
    resolve = product_urls.sitemap_resolver(SITEMAP)
    assert resolve({"Name": "Blue Dream | 1g", "brand": {"name": "Acme"}}) == "https://s.test/product/acme-blue-dream-1g-for-sale"
    assert resolve({"Name": "Blue Dream | 2g", "brand": {"name": "Acme"}}) == ""


def test_sitemap_resolver_keeps_the_slot_of_an_unbranded_product(monkeypatch):
    fake(monkeypatch, Resp(text=XML))
    resolve = product_urls.sitemap_resolver(SITEMAP)
    assert resolve({"Name": "Lighter", "brand": None}) == "https://s.test/product/-lighter-for-sale"


def test_joint_resolver_pairs_pos_ids_across_pages(monkeypatch):
    page = lambda ids: Resp({"hits": {"hits": [{"_source": {"posId": f"pos{i}", "jointId": f"uuid{i}"}} for i in ids]}})
    monkeypatch.setattr(product_urls, "JOINT_PAGE", 2)
    session = fake(monkeypatch, page([1, 2]), page([3]))
    resolve = product_urls.joint_resolver({"site": "https://d.test/", "business_id": 6163})
    assert resolve({"_id": "pos3"}) == "https://d.test/products/?product_page=uuid3"
    assert resolve({"_id": "unknown"}) == ""
    assert [q["from"] for q in session.posts] == [0, 2]
    assert session.posts[0]["query"]["bool"]["filter"][0] == {"bool": {"should": [{"term": {"businessId": "6163"}}]}}


def test_build_prefers_a_source_and_falls_back_to_the_template():
    assert product_urls.build({"product_url_template": "https://x/{cname}"}) == "https://x/{cname}"
    assert product_urls.build({}) == ""


def test_build_survives_a_failed_lookup(monkeypatch, capsys):
    class Down:
        def get(self, *a, **k):
            raise RuntimeError("503")
    monkeypatch.setattr(product_urls, "_session", lambda: Down())
    resolve = product_urls.build({"slug": "s", "product_url_source": {"type": "sitemap", **SITEMAP}})
    assert resolve({"Name": "x"}) == ""
    assert "continuing without" in capsys.readouterr().out


def test_every_registry_source_is_a_known_type_with_its_fields():
    stores = json.loads((Path(__file__).resolve().parent.parent / "dispensaries.json").read_text())
    needs = {"sitemap": {"sitemap", "template"}, "joint": {"site", "business_id"}}
    for s in stores:
        src = s.get("product_url_source")
        if src:
            assert src["type"] in product_urls.SOURCES and needs[src["type"]] <= src.keys(), s["slug"]
            assert "product_url_template" not in s, f"{s['slug']} has both a source and a template"
