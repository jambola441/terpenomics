"""
Smoke tests — one live HTTP request per active dispensary.

Run all:   pytest tests/test_smoke.py -m live -v
Skip live: pytest tests/test_smoke.py -m "not live"
One store: pytest tests/test_smoke.py -m live -k soulmate
"""

import json
import os
import time
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REGISTRY = os.path.join(ROOT, "dispensaries.json")

GQL_URL     = "https://dutchie.com/graphql"
BLAZE_BASE  = "https://ecom-api.blaze.me/api/v1/products/"
TA_URL      = "https://www.thetravelagency.co/menu.data"

HEADERS_HTML = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
}
IMPERSONATE = "safari17_0"

PRODUCTS_QUERY = """
query FilteredProducts($productsFilter: productsFilterInput!, $page: Int, $perPage: Int) {
  filteredProducts(filter: $productsFilter, page: $page, perPage: $perPage) {
    products { _id Name type }
    queryInfo { totalCount }
  }
}
"""


def _load_active():
    reg = json.load(open(REGISTRY))
    return [d for d in reg if d["status"] == "active"]


def _id(d):
    return d["slug"]


@pytest.mark.live
@pytest.mark.parametrize("store", [d for d in _load_active() if d["platform"] == "dutchie_graphql"], ids=_id)
def test_dutchie_graphql(store):
    from curl_cffi import requests as cffi_req

    session = cffi_req.Session(impersonate=IMPERSONATE)
    payload = {
        "operationName": "FilteredProducts",
        "variables": {
            "productsFilter": {
                "dispensaryId":           store["dutchie_id"],
                "Status":                 "Active",
                "bypassOnlineThresholds": True,
                "removeProductsBelowOptionThresholds": False,
            },
            "page":    1,
            "perPage": 1,
        },
        "query": PRODUCTS_QUERY,
    }
    headers = {
        "Accept":       "application/json",
        "Content-Type": "application/json",
        "Origin":       "https://dutchie.com",
        "Referer":      "https://dutchie.com/",
    }
    resp = session.post(GQL_URL, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    body = resp.json()
    assert "errors" not in body, body.get("errors")
    fp = (body.get("data") or {}).get("filteredProducts", {})
    assert (fp.get("queryInfo") or {}).get("totalCount", 0) >= 1, f"0 products for {store['slug']}"
    products = fp.get("products") or []
    assert products, f"no products returned for {store['slug']}"
    p = products[0]
    assert p.get("Name"), "product missing Name"
    assert p.get("type"),  "product missing type"


@pytest.mark.live
@pytest.mark.parametrize("store", [d for d in _load_active() if d["platform"] == "tymber"], ids=_id)
def test_tymber(store):
    import requests

    headers = {"X-Store": store["blaze_id"], "Accept": "application/json"}
    resp = requests.get(BLAZE_BASE, headers=headers, params={"limit": 1, "offset": 0}, timeout=20)
    resp.raise_for_status()
    body = resp.json()
    data = body.get("data") or []
    assert len(data) >= 1, f"0 products for {store['slug']}"
    p = (data[0].get("attributes") or {})
    assert p.get("name"), "product missing name"


@pytest.mark.live
@pytest.mark.parametrize("store", [d for d in _load_active() if d["platform"] == "dutchie_plus"], ids=_id)
def test_dutchie_plus(store):
    import httpx, json, re

    resp = httpx.get(store["menu_url"], headers=HEADERS_HTML, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    m = re.search(r'window\.__remixContext\s*=\s*', resp.text)
    assert m, "no __remixContext found"
    start = m.end()
    ctx = json.loads(resp.text[start:resp.text.find("</script>", start)].rstrip("; \t\n"))
    for k, v in ctx["state"]["loaderData"].items():
        if "location" in k and isinstance(v, dict) and "resultData" in v:
            products = v["resultData"].get("menu", {}).get("products", [])
            assert len(products) >= 1, f"0 products for {store['slug']}"
            assert products[0].get("name"), "product missing name"
            return
    pytest.fail("dutchie_plus loader data not found in page")


@pytest.mark.live
@pytest.mark.parametrize("store", [d for d in _load_active() if d["platform"] == "flowhub"], ids=_id)
def test_flowhub(store):
    import httpx, json, re

    resp = httpx.get(store["menu_url"], headers=HEADERS_HTML, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    m = re.search(r'window\.__remixContext\s*=\s*', resp.text)
    assert m, "no __remixContext found"
    start = m.end()
    ctx = json.loads(resp.text[start:resp.text.find("</script>", start)].rstrip("; \t\n"))
    for k, v in ctx["state"]["loaderData"].items():
        if "medrec" in k and isinstance(v, dict) and "products" in v:
            blob = v["products"]
            products = blob.get("products", []) if isinstance(blob, dict) else []
            assert len(products) >= 1, f"0 products for {store['slug']}"
            assert products[0].get("name"), "product missing name"
            return
    pytest.fail("flowhub loader data not found in page")


@pytest.mark.live
@pytest.mark.parametrize("store", [d for d in _load_active() if d["platform"] == "travel_agency"], ids=_id)
def test_travel_agency(store):
    import httpx

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, */*",
        "Referer": "https://www.thetravelagency.co/menu/",
    }
    resp = httpx.get(TA_URL, params={"page": 1, "_routes": "routes/_layout.menu"},
                     headers=headers, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    arr = resp.json()

    def decode(a, idx):
        val = a[idx]
        if isinstance(val, dict):
            return {a[int(k[1:])]: decode(a, v) for k, v in val.items()}
        if isinstance(val, list):
            return [decode(a, i) for i in val]
        return val

    data = decode(arr, 0)
    route = data.get("routes/_layout.menu", {}).get("data", {})
    products = route.get("products") or []
    assert len(products) >= 1, "0 products from Travel Agency"
    assert products[0].get("name"), "product missing name"
