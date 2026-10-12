"""Customer surfaces show only trusted listings, and the product's identity from the
matched catalog entry (services/shop_listings.py) — never the listing's own columns."""
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import get_current_user, SupabaseAuthUser
from database import engine
from models import (BrandCatalog, BrandCatalogEntry, Customer, Dispensary, FeaturedListing, Listing,
                    Order, OrderItem, PreferredDispensary)
from routes.customer import router as customer_router
from routes_me import router as me_router
from routes.orders import router as orders_router
from services.consent import TERMS_VERSION

AUTH_UID = uuid4()


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (OrderItem, Order, FeaturedListing, PreferredDispensary, Listing,
                      BrandCatalogEntry, BrandCatalog, Dispensary, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


@pytest.fixture
def world():
    with Session(engine) as session:
        shop = Dispensary(name="Bergen", slug="bergen", accepts_pickup=True)
        other = Dispensary(name="Queens", slug="queens", accepts_pickup=True)
        catalog = BrandCatalog(brand_slug="mfny", brand_name="MFNY", source_method="test")
        session.add_all([shop, other, catalog])
        session.commit()
        entry = BrandCatalogEntry(catalog_id=catalog.id, name="Skunk BagelHole", category="pre-rolls",
                                  product_line="BagelHole Live Resin", strain="Skunk", variant="1.5g")
        session.add(entry)
        session.commit()

        def listing(store, name, method, line, category="concentrate"):
            # the listing's own columns say something else: the shop must not read them
            return Listing(dispensary_id=store.id, scraped_name=name, scraped_brand="MFNY",
                           scraped_category=category, product_line=line, strain="Skunk Guess",
                           variant="1g", price_cents=2000, in_stock=True, is_active=True,
                           catalog_entry_id=entry.id, catalog_match_method=method)
        rows = {
            "trusted": listing(shop, "MFNY Skunk Bagel Hole", "attributes", "Bagel Hole"),
            "manual": listing(other, "Skunk BH 1.5", "manual", None),
            "unsure": listing(shop, "MFNY Skunk Mini", "review_unsure", "Mini", "pre-rolls"),
            "jev": listing(other, "MFNY Skunk Mini 2", "jev", "Mini", "pre-rolls"),
        }
        rows["none"] = Listing(dispensary_id=shop.id, scraped_name="MFNY Mystery", scraped_brand="MFNY",
                               scraped_category="pre-rolls", product_line="Mini", variant="1g",
                               price_cents=900, in_stock=True, is_active=True, catalog_match_method="none")
        session.add_all(rows.values())
        session.add(Customer(name="Ada", phone="+15552030009", auth_user_id=AUTH_UID, first_name="Ada",
                             age_confirmed_at=datetime.utcnow(), terms_version=TERMS_VERSION,
                             terms_accepted_at=datetime.utcnow()))
        session.commit()
        return {"shop": str(shop.id), "other": str(other.id), **{k: str(v.id) for k, v in rows.items()}}


def _client():
    app = FastAPI()
    app.include_router(customer_router)
    app.include_router(me_router)
    app.include_router(orders_router)
    app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
        user_id=str(AUTH_UID), email=None, phone=None, role="authenticated", raw_claims={})
    return TestClient(app)


UNTRUSTED = ("unsure", "jev", "none")


def test_brand_page_groups_trusted_listings_by_the_entrys_identity(world):
    brand = _client().get("/customer/brands/MFNY").json()
    [product] = brand["products"]
    assert (product["category"], product["product_line"], product["strain"], product["variant"]) == \
        ("pre-rolls", "BagelHole Live Resin", "Skunk", "1.5g")
    ids = {o["listing_id"] if "listing_id" in o else o.get("id") for o in product["offerings"]}
    assert len(product["offerings"]) == 2 and not ids & {world[k] for k in UNTRUSTED}
    lines = _client().get("/customer/brands/MFNY/lines/Mini").json()
    assert not lines.get("products")


def test_brands_and_categories_count_trusted_listings_only(world):
    client = _client()
    assert [(b["name"], b["listing_count"]) for b in client.get("/customer/brands").json()] == [("MFNY", 2)]
    assert [(c["name"], c["listing_count"]) for c in client.get("/customer/categories").json()] == \
        [("pre-rolls", 2)]
    assert client.get("/customer/categories/concentrate").json().get("products") in ([], None)
    cat = client.get("/customer/categories/pre-rolls").json()
    assert [p["product_line"] for p in cat["products"]] == ["BagelHole Live Resin"]


def test_a_store_shelf_and_listing_page_show_trusted_listings_only(world):
    client = _client()
    shelf = client.get(f"/customer/dispensaries/{world['shop']}/listings").json()
    assert [r["id"] for r in shelf] == [world["trusted"]]
    assert shelf[0]["product_line"] == "BagelHole Live Resin"
    assert client.get(f"/customer/dispensaries/{world['shop']}/listings/{world['trusted']}").status_code == 200
    for k in ("unsure", "none"):
        assert client.get(f"/customer/dispensaries/{world['shop']}/listings/{world[k]}").status_code == 404
    opts = client.get(f"/customer/dispensaries/{world['shop']}/filter-options").json()
    assert opts["variants"] == ["1.5g"]


def test_an_untrusted_listing_cannot_be_ordered(world):
    resp = _client().post("/me/orders", json={"dispensary_id": world["shop"],
                                              "items": [{"listing_id": world["unsure"], "quantity": 1}]})
    assert resp.status_code == 404


def test_products_search_and_home_feed_show_trusted_listings_only(world):
    client = _client()
    rows = client.get("/customer/products", params={"brand": "MFNY"}).json()
    assert [(r["product_line"], r["listing_count"], r["any_in_stock"]) for r in rows] == \
        [("BagelHole Live Resin", 2, True)]
    assert client.get("/customer/products", params={"q": "Mini"}).json() == []
    client.post(f"/me/preferred-dispensaries/{world['shop']}")
    rails = client.get("/me/feed", params={"view": "combined"}).json()["combined"]
    shown = {item["id"] for rail in rails.values() for item in rail}
    assert shown <= {world["trusted"], world["manual"]} and world["trusted"] in shown
