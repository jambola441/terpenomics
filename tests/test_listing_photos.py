"""A listing shows its brand's photo when its catalog match is trusted.

The same product looked different at every store, because each store's photo is
whatever its point-of-sale system holds. A storefront catalog keeps the brand's
own photo per product and size; every screen that draws a listing shows that one
for a trusted match, and the store's otherwise (services/listing_photos.py).
"""
import os
import sys
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import (
    TRUSTED_MATCH_METHODS,
    BrandCatalog,
    BrandCatalogEntry,
    Customer,
    Dispensary,
    FeaturedListing,
    Listing,
    Order,
    OrderItem,
    PhotoMirror,
    PreferredDispensary,
)
from routes.customer import router as customer_router
from routes.orders import router as orders_router
from routes_me import router as me_router
from services.consent import TERMS_VERSION
from services.listing_photos import listing_photos

AUTH_UID = uuid4()
BRAND_PHOTO = "https://cdn.shopify.com/s/files/aeris-sunset-sherbet.png"
STORE_PHOTO = "https://pos.example/sunset.jpg"


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (OrderItem, Order, FeaturedListing, PreferredDispensary, Listing, PhotoMirror,
                      BrandCatalogEntry, BrandCatalog, Dispensary, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


def _listing(shop, name, *, method=None, entry=None, photo=STORE_PHOTO, strain="Sunset Sherbet"):
    return Listing(
        dispensary_id=shop.id, scraped_name=name, scraped_brand="Aeris",
        scraped_category="flower", strain=strain, variant="3.5g",
        price_cents=4500, in_stock=True, is_active=True, image_url=photo,
        catalog_entry_id=entry.id if entry else None, catalog_match_method=method,
        catalog_match_confidence=1.0 if method else None,
    )


@pytest.fixture
def world():
    with Session(engine) as session:
        shop = Dispensary(name="Bergen Botanics", slug="bergen", accepts_pickup=True)
        catalog = BrandCatalog(brand_slug="aeris", brand_name="Aeris",
                               source_method="shopify_products_json")
        customer = Customer(
            name="Ada", phone="+15552030001", auth_user_id=AUTH_UID, first_name="Ada",
            age_confirmed_at=datetime.utcnow(), terms_version=TERMS_VERSION,
            terms_accepted_at=datetime.utcnow(),
        )
        session.add_all([shop, catalog, customer])
        session.commit()
        with_photo = BrandCatalogEntry(catalog_id=catalog.id, name="Sunset Sherbet",
                                       category="flower", strain="Sunset Sherbet",
                                       variant="3.5g", image_url=BRAND_PHOTO)
        without = BrandCatalogEntry(catalog_id=catalog.id, name="Blue Dream",
                                    category="flower", strain="Blue Dream", variant="3.5g")
        session.add_all([with_photo, without])
        session.commit()
        listings = {
            "trusted": _listing(shop, "Sunset Sherbet 3.5g", method="attributes", entry=with_photo),
            # Recorded for a person to check: not trusted, so not the brand's photo.
            "review": _listing(shop, "Sunset Sherb 3.5", method="jev_review", entry=with_photo,
                               photo="https://pos.example/review.jpg", strain="Sunset Sherb"),
            "no_entry_photo": _listing(shop, "Blue Dream 3.5g", method="attributes", entry=without,
                                       photo="https://pos.example/blue.jpg", strain="Blue Dream"),
            "unmatched": _listing(shop, "House Special", photo=None, strain="House Special"),
        }
        session.add_all(listings.values())
        session.commit()
        return {"shop_id": shop.id, "customer_id": customer.id,
                **{k: v.id for k, v in listings.items()}}


def _client():
    app = FastAPI()
    app.include_router(customer_router)
    app.include_router(me_router)
    app.include_router(orders_router)
    app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
        user_id=str(AUTH_UID), email=None, phone=None, role="authenticated", raw_claims={},
    )
    return TestClient(app)


EXPECTED = {
    "trusted": BRAND_PHOTO,
    "review": "https://pos.example/review.jpg",
    "no_entry_photo": "https://pos.example/blue.jpg",
    "unmatched": None,
}


def test_the_trusted_methods_are_the_matchers():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import catalog_match

    assert set(TRUSTED_MATCH_METHODS) == set(catalog_match.TRUSTED_METHODS)


def test_the_helper_prefers_the_catalog_photo_only_for_a_trusted_match(world):
    with Session(engine) as session:
        listings = session.exec(select(Listing)).all()
        photo = listing_photos(session, listings)
        by_id = {l.id: photo(l) for l in listings}
    assert {k: by_id[world[k]] for k in EXPECTED} == EXPECTED


def test_a_store_shelf_shows_the_brand_photo_for_a_trusted_match(world):
    body = _client().get(f"/customer/dispensaries/{world['shop_id']}/listings").json()
    got = {row["id"]: row["image_url"] for row in body}
    assert {k: got[str(world[k])] for k in EXPECTED} == EXPECTED


def test_the_listing_page_shows_it_too(world):
    client = _client()
    trusted = client.get(f"/customer/dispensaries/{world['shop_id']}/listings/{world['trusted']}").json()
    review = client.get(f"/customer/dispensaries/{world['shop_id']}/listings/{world['review']}").json()
    assert trusted["image_url"] == BRAND_PHOTO
    assert review["image_url"] == "https://pos.example/review.jpg"


def test_brand_category_and_product_pages_show_it(world):
    client = _client()
    brand = client.get("/customer/brands/Aeris").json()
    sunset = next(p for p in brand["products"] if p["strain"] == "Sunset Sherbet")
    assert sunset["image_url"] == BRAND_PHOTO

    product = client.get("/customer/products/detail", params={
        "key": sunset["key"], "brand": "Aeris"}).json()
    assert product["image_url"] == BRAND_PHOTO

    category = client.get("/customer/categories/flower").json()
    sunset = next(p for p in category["products"] if p["strain"] == "Sunset Sherbet")
    assert sunset["image_url"] == BRAND_PHOTO


def test_the_home_feed_shows_it(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['shop_id']}")
    rails = client.get("/me/feed", params={"view": "combined"}).json()["combined"]
    shown = {item["id"]: item["image_url"] for rail in rails.values() for item in rail}
    assert shown[str(world["trusted"])] == BRAND_PHOTO
    assert shown[str(world["no_entry_photo"])] == "https://pos.example/blue.jpg"


def test_an_order_keeps_the_photo_the_shopper_saw(world):
    resp = _client().post("/me/orders", json={
        "dispensary_id": str(world["shop_id"]),
        "items": [{"listing_id": str(world["trusted"]), "quantity": 1}],
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["items"][0]["image_url"] == BRAND_PHOTO


def test_a_store_photo_copied_into_our_storage_is_served_from_there(world):
    copy = "https://abc.supabase.co/storage/v1/object/public/photos/store/k1/640.webp"
    with Session(engine) as session:
        session.add_all([
            PhotoMirror(source_url="https://pos.example/blue.jpg", url=copy, bytes=900_000),
            # A failed copy keeps the original.
            PhotoMirror(source_url="https://pos.example/review.jpg", url=None, failed="HTTP 404"),
            # A catalog photo still wins over a copy of the store's.
            PhotoMirror(source_url=STORE_PHOTO, url="https://abc.supabase.co/x/640.webp"),
        ])
        session.commit()
    body = _client().get(f"/customer/dispensaries/{world['shop_id']}/listings").json()
    got = {row["id"]: row["image_url"] for row in body}
    assert got[str(world["no_entry_photo"])] == copy
    assert got[str(world["review"])] == "https://pos.example/review.jpg"
    assert got[str(world["trusted"])] == BRAND_PHOTO
