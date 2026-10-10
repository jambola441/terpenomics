"""Brand logos: read off a brand's site, picked in the admin, shown on its tile.

The properties worth pinning: candidates come out most-likely-first and absolute; a
logo is stored at web size (an SVG kept only when it carries no script); fetching
a typed URL never reaches a private address; and once picked, the brand list and
page show it straight away.
"""
import io
import os
import socket
import sys
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import (BrandCatalog, BrandCatalogEntry, BrandLogo, Customer, Dispensary, FeaturedListing,
                    Listing, Order, OrderItem, PreferredDispensary)
from routes.admin import router as admin_router
from routes.admin.auth import require_admin
from routes.customer import router as customer_router
from services import brand_logos as logos
from services import photo_store

PIL = pytest.importorskip("PIL.Image")
REAL_FETCH = logos.fetch


def png(w, h, alpha=True):
    buf = io.BytesIO()
    PIL.new("RGBA" if alpha else "RGB", (w, h), (200, 30, 30, 128) if alpha else (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (OrderItem, Order, FeaturedListing, PreferredDispensary, Listing, BrandLogo,
                      BrandCatalogEntry, BrandCatalog, Dispensary, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


@pytest.fixture
def public_dns(monkeypatch):
    """Every host resolves to a public address, unless the test says otherwise."""
    answers = {}

    def getaddrinfo(host, port, *a, **kw):
        ip = answers.get(host, "93.184.216.34")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return answers


# --------------------------------------------------------------------------- unit

def test_brand_key_matches_the_catalogs():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import catalog_store
    for name in ("Papa & Barkley", "Papa and Barkley", "AYRLOOM", "Grön", "1906 (Drops)", "Off+Hours"):
        assert logos.brand_key(name) == catalog_store.brand_key(name)


def test_candidates_come_most_likely_first_and_absolute():
    html = """<html><head>
      <link rel="icon" href="/favicon-16.png" sizes="16x16">
      <link rel="icon" href="/icon-192.png" sizes="192x192">
      <link rel="icon" type="image/svg+xml" href="/icon.svg">
      <link rel="apple-touch-icon" href="/apple-57.png" sizes="57x57">
      <link rel="apple-touch-icon" href="/apple-touch-icon-120x120.png">
      <link rel="apple-touch-icon" href="/apple-180.png" sizes="180x180">
      <meta property="og:image" content="https://cdn.example/banner.jpg">
      <script type="application/ld+json">{"@type": "Organization", "logo": {"url": "/brand-logo.png"}}</script>
    </head><body>
      <header><img class="site-header__logo" src="//cdn.example/logo.svg" alt="Acme"></header>
      <img src="data:image/png;base64,AAAA" class="logo">
      <img src="http://insecure.example/logo.png" alt="logo">
      <img src="/hero.jpg" alt="Our farm">
    </body></html>"""
    got = logos.candidates_from_html(html, "https://acme.example/")
    assert [(c["kind"], c["url"]) for c in got] == [
        ("site logo", "https://acme.example/brand-logo.png"),
        ("logo image", "https://cdn.example/logo.svg"),
        ("app icon", "https://acme.example/apple-180.png"),
        ("icon", "https://acme.example/icon-192.png"),
        ("icon", "https://acme.example/icon.svg"),
        ("share image", "https://cdn.example/banner.jpg"),
    ]


def test_a_page_with_no_app_icon_gets_the_usual_one_guessed():
    got = logos.candidates_from_html("<html></html>", "https://acme.example/shop")
    assert got == [{"url": "https://acme.example/apple-touch-icon.png", "kind": "app icon (guessed)"}]


def test_a_logo_is_stored_at_web_size_with_its_transparency():
    body, content_type, ext = logos.logo_file(png(1200, 600))
    im = PIL.open(io.BytesIO(body))
    assert (content_type, ext, im.format, im.size, im.mode) == ("image/webp", "webp", "WEBP", (384, 192), "RGBA")


def test_an_svg_is_kept_unless_it_carries_script():
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><circle r="4"/></svg>'
    assert logos.logo_file(svg) == (svg, "image/svg+xml", "svg")
    for bad in (b'<svg><script>alert(1)</script></svg>', b'<svg onload="alert(1)"></svg>',
                b'<svg><a href="javascript:x">y</a></svg>'):
        with pytest.raises(ValueError, match="script"):
            logos.logo_file(bad)
    with pytest.raises(ValueError, match="not an image"):
        logos.logo_file(b"<html>nope</html>")


@pytest.mark.parametrize("url,ip", [
    ("http://acme.example/", None),               # https only
    ("https://localhost/", "127.0.0.1"),
    ("https://intranet.example/", "10.0.0.5"),
    ("https://metadata.example/", "169.254.169.254"),
    ("https://v6.example/", "::1"),
])
def test_a_typed_url_never_reaches_a_private_address(public_dns, url, ip):
    host = url.split("/")[2]
    if ip:
        public_dns[host] = ip
    with pytest.raises(logos.UnsafeURL):
        logos.check_public(url)


def test_a_public_https_url_is_allowed(public_dns):
    logos.check_public("https://acme.example/logo.png")


# --------------------------------------------------------------------------- endpoints

@pytest.fixture
def world():
    with Session(engine) as session:
        shop = Dispensary(name="Bergen", slug="bergen")
        session.add_all([shop, BrandCatalog(brand_slug="ayrloom", brand_name="Ayrloom",
                                            source_url="https://ayrloom.com/products.json?limit=250",
                                            source_method="shopify_products_json"),
                         BrandCatalog(brand_slug="jetpacks", brand_name="Jetpacks",
                                      source_url=None, source_method="listings_bootstrap")])
        session.commit()
        rows = [("Ayrloom", 3), ("AYRLOOM", 1), ("Jetpacks", 2), ("Tiny", 1)]
        for brand, n in rows:
            for i in range(n):
                session.add(Listing(dispensary_id=shop.id, scraped_name=f"{brand} {i}", scraped_brand=brand,
                                    scraped_category="edible", price_cents=1000, in_stock=True, is_active=True,
                                    image_url=f"https://pos.example/{brand}-{i}.jpg"))
        session.commit()


@pytest.fixture
def client(monkeypatch, public_dns):
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    uploads = {}

    def upload(path, data, content_type):
        uploads[path] = (data, content_type)
        return f"https://abc.supabase.co/storage/v1/object/public/photos/{path}"
    monkeypatch.setattr(photo_store, "upload", upload)
    monkeypatch.setattr(logos, "fetch", lambda url, max_bytes, accept: (png(800, 400), "image/png", url))
    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(customer_router)
    admin = SupabaseAuthUser(user_id=str(uuid4()), email="ops@terpee.example", phone=None,
                             role="admin", raw_claims={})
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[get_current_user] = lambda: admin
    c = TestClient(app)
    c.uploads = uploads
    return c


def test_the_list_counts_spellings_together_and_knows_storefront_sites(world, client):
    rows = client.get("/admin/brand-logos").json()
    assert [(r["brand_name"], r["listing_count"]) for r in rows] == [("Ayrloom", 4), ("Jetpacks", 2), ("Tiny", 1)]
    sites = {r["brand_name"]: r["site_url"] for r in rows}
    assert sites == {"Ayrloom": "https://ayrloom.com/", "Jetpacks": None, "Tiny": None}


def test_choosing_a_candidate_stores_it_and_tiles_show_it_at_once(world, client):
    # Cached before the pick: the pick must still show straight away.
    assert client.get("/customer/brands/Ayrloom").json()["logo_url"] is None
    row = client.post("/admin/brand-logos/ayrloom", json={
        "brand_name": "Ayrloom", "image_url": "https://ayrloom.com/logo.png", "site_url": "https://ayrloom.com/"}).json()
    [(path, (data, content_type))] = client.uploads.items()
    assert path.startswith("logos/ayrloom-") and path.endswith(".webp") and content_type == "image/webp"
    assert row["logo_url"].endswith(path) and row["chosen_by"] == "ops@terpee.example"
    brands = {b["name"]: b["logo_url"] for b in client.get("/customer/brands").json()}
    assert brands["Ayrloom"] == brands["AYRLOOM"] == row["logo_url"] and brands["Jetpacks"] is None
    assert client.get("/customer/brands/Ayrloom").json()["logo_url"] == row["logo_url"]

    assert client.delete("/admin/brand-logos/ayrloom").json() == {"ok": True}
    assert client.get("/customer/brands/Ayrloom").json()["logo_url"] is None


def test_an_uploaded_file_becomes_the_logo(world, client):
    row = client.post("/admin/brand-logos/tiny/upload", data={"brand_name": "Tiny"},
                      files={"file": ("tiny.png", png(100, 100), "image/png")}).json()
    assert row["logo_url"] and row["source_url"] is None
    bad = client.post("/admin/brand-logos/tiny/upload", data={"brand_name": "Tiny"},
                      files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 422


def test_a_private_address_is_refused_before_anything_is_fetched(world, client, public_dns, monkeypatch):
    monkeypatch.setattr(logos, "fetch", REAL_FETCH)   # refuses before opening a connection
    public_dns["internal.example"] = "10.1.2.3"
    resp = client.post("/admin/brand-logos/ayrloom", json={
        "brand_name": "Ayrloom", "image_url": "https://internal.example/logo.png"})
    assert resp.status_code == 400 and "not a public address" in resp.json()["detail"]
    resp = client.post("/admin/brand-logos/ayrloom/candidates", json={"site_url": "https://internal.example/"})
    assert resp.status_code == 400
