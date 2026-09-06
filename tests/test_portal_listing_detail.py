"""One listing, comprehensively.

The screen answers three questions a store's own menu cannot: who is selling
this, who else sells it and for how much, and what else on this shelf is like
it. These tests are about those answers.
"""
from uuid import UUID

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


def _row(dispensary, **kwargs):
    defaults = dict(
        scraped_brand="Aeris",
        scraped_category="flower",
        subtype="smalls",
        product_line=None,
        strain="Blue Dream",
        variant="3.5g",
        scraped_name="Blue Dream 3.5g",
        price_cents=4000,
        in_stock=True,
        is_active=True,
    )
    defaults.update(kwargs)
    return Listing(dispensary_id=dispensary.id, **defaults)


@pytest.fixture
def world():
    with Session(engine) as session:
        here = Dispensary(
            name="Bergen Botanics", slug="bergen", address="623 Bergen St",
            lat=40.68, lng=-73.97, accepts_pickup=True,
            website_url="https://bergen.test", logo_url="https://bergen.test/logo.png",
        )
        cheaper = Dispensary(name="Atlantic Leaf", slug="atlantic", lat=40.68, lng=-73.96)
        dearer = Dispensary(name="Pricey Co", slug="pricey", lat=40.70, lng=-73.99)
        retired = Dispensary(name="Closed Co", slug="closed", is_active=False)
        session.add_all([here, cheaper, dearer, retired])
        session.commit()

        subject = _row(here, scraped_name="Blue Dream -Hybrid- | 3.5g | Aeris")
        session.add_all([
            subject,
            # The same product elsewhere.
            _row(cheaper, price_cents=3500),
            _row(dearer, price_cents=5000),
            # Same product, but the store is gone.
            _row(retired, price_cents=100),
            # Same product elsewhere but out of stock: not somewhere to go today.
            _row(cheaper, price_cents=200, variant="7g", in_stock=False),
            # Same shelf, same brand and subtype -- the closest neighbours.
            _row(here, strain="Gelato", price_cents=4200, scraped_name="Gelato"),
            # Same shelf, same category, different subtype and brand.
            _row(here, strain="Northern Lights", subtype="prepack",
                 scraped_brand="Botanica", price_cents=3800, scraped_name="Northern Lights"),
            # Same shelf, different category entirely: not similar.
            _row(here, scraped_category="edible", subtype="gummy", strain=None,
                 scraped_name="Peach Gummies", price_cents=2400),
        ])
        session.commit()
        return {"here": str(here.id), "listing": str(subject.id), "cheaper": str(cheaper.id)}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(customer_router)
    return TestClient(app)


def _get(world):
    return _client().get(f"/customer/dispensaries/{world['here']}/listings/{world['listing']}").json()


# ---------------------------
# The store selling it
# ---------------------------

def test_the_listing_carries_its_whole_store(world):
    store = _get(world)["dispensary"]
    assert store["name"] == "Bergen Botanics"
    assert store["address"] == "623 Bergen St"
    assert store["accepts_pickup"] is True
    assert store["website_url"] == "https://bergen.test"
    # Coordinates so the screen can show a distance and a directions link.
    assert (store["lat"], store["lng"]) == (40.68, -73.97)


# ---------------------------
# Also available at
# ---------------------------

def test_also_available_at_lists_the_other_stores_cheapest_first(world):
    elsewhere = _get(world)["also_available_at"]
    assert [row["dispensary"]["name"] for row in elsewhere] == ["Atlantic Leaf", "Pricey Co"]
    assert [row["price_cents"] for row in elsewhere] == [3500, 5000]


def test_a_closed_store_is_not_somewhere_you_can_go(world):
    names = [row["dispensary"]["name"] for row in _get(world)["also_available_at"]]
    assert "Closed Co" not in names


def test_a_different_size_is_a_different_product(world):
    # The 7g at Atlantic is not this 3.5g, and listing it would compare
    # two prices that are not comparable.
    assert all(row["price_cents"] != 200 for row in _get(world)["also_available_at"])


def test_price_context_summarizes_the_alternatives(world):
    context = _get(world)["price_context"]
    assert context["other_store_count"] == 2
    assert context["min_cents"] == 3500
    assert context["avg_cents"] == 4250
    assert context["max_cents"] == 5000
    # 4000 here against 3500 elsewhere: not the cheapest.
    assert context["is_cheapest"] is False


def test_being_the_cheapest_is_stated_plainly(world):
    with Session(engine) as session:
        subject = session.get(Listing, UUID(world["listing"]))
        subject.price_cents = 3000
        session.add(subject)
        session.commit()

    assert _get(world)["price_context"]["is_cheapest"] is True


def test_a_product_nobody_else_carries_has_no_comparison(world):
    with Session(engine) as session:
        subject = session.get(Listing, UUID(world["listing"]))
        subject.strain = "House Exclusive"
        session.add(subject)
        session.commit()

    body = _get(world)
    assert body["also_available_at"] == []
    assert body["price_context"]["other_store_count"] == 0
    assert body["price_context"]["avg_cents"] is None
    # Nothing to be cheapest than.
    assert body["price_context"]["is_cheapest"] is False


# ---------------------------
# Similar on this shelf
# ---------------------------

def test_similar_items_come_from_the_same_store_and_category(world):
    similar = _get(world)["similar_at_dispensary"]
    assert similar, "expected neighbours on the same shelf"
    assert all(row["scraped_category"] == "flower" for row in similar)
    assert "Peach Gummies" not in [row["display_name"] for row in similar]


def test_the_listing_is_not_similar_to_itself(world):
    assert world["listing"] not in [row["id"] for row in _get(world)["similar_at_dispensary"]]


def test_the_closest_neighbours_come_first(world):
    # Same brand and subtype beats same category alone.
    similar = _get(world)["similar_at_dispensary"]
    assert similar[0]["display_name"] == "Gelato"


def test_similar_items_are_named_for_a_shopper(world):
    similar = _get(world)["similar_at_dispensary"]
    assert all(row["display_name"] and "|" not in row["display_name"] for row in similar)


# ---------------------------
# The rest of the screen
# ---------------------------

def test_the_product_key_matches_the_product_page(world):
    body = _get(world)
    detail = _client().get(
        "/customer/products/detail",
        params={"key": body["product_key"], "brand": body["scraped_brand"]},
    )
    assert detail.status_code == 200
    assert detail.json()["dispensary_count"] == 3


def test_the_screen_says_when_stock_was_last_checked(world):
    # Null until a scrape has touched the row, but the key is always present so
    # the client can decide whether to say anything.
    assert "last_seen_at" in _get(world)
