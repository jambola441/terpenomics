"""Browsing brands: the home rail's top slice and the brands section's paging."""
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from database import engine
from models import Dispensary, Listing
from routes.customer import router as customer_router


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (Listing, Dispensary):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


@pytest.fixture
def catalogue():
    """Three brands with deliberately different sizes, so sort order is visible."""
    with Session(engine) as session:
        shop = Dispensary(name="Bergen Botanics", slug="bergen")
        session.add(shop)
        session.commit()

        for brand, count in (("Aeris", 3), ("Botanica", 2), ("Cloudline", 1)):
            for i in range(count):
                session.add(Listing(
                    dispensary_id=shop.id,
                    scraped_name=f"{brand} item {i}",
                    scraped_brand=brand,
                    scraped_category="flower",
                    price_cents=1000,
                    in_stock=True,
                    is_active=True,
                ))
        # Unbranded stock is real, but it is not a brand to browse.
        session.add(Listing(
            dispensary_id=shop.id, scraped_name="House Flower",
            scraped_brand=None, price_cents=900, in_stock=True, is_active=True,
        ))
        session.commit()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(customer_router)
    return TestClient(app)


def test_brands_are_biggest_first_by_default(catalogue):
    rows = _client().get("/customer/brands").json()
    assert [r["name"] for r in rows] == ["Aeris", "Botanica", "Cloudline"]
    assert [r["listing_count"] for r in rows] == [3, 2, 1]


def test_unbranded_listings_are_not_a_brand(catalogue):
    names = [r["name"] for r in _client().get("/customer/brands").json()]
    assert None not in names and "" not in names


def test_brands_can_be_sorted_by_name(catalogue):
    rows = _client().get("/customer/brands", params={"sort": "name"}).json()
    assert [r["name"] for r in rows] == ["Aeris", "Botanica", "Cloudline"]


def test_brands_can_be_searched(catalogue):
    rows = _client().get("/customer/brands", params={"q": "bot"}).json()
    assert [r["name"] for r in rows] == ["Botanica"]


def test_brands_page_through(catalogue):
    client = _client()
    first = client.get("/customer/brands", params={"limit": 2}).json()
    second = client.get("/customer/brands", params={"limit": 2, "offset": 2}).json()
    assert [r["name"] for r in first] == ["Aeris", "Botanica"]
    assert [r["name"] for r in second] == ["Cloudline"]
