"""A store's menu, seen against every other store's.

A dispensary's own menu can tell a shopper the price. It cannot tell them
whether that price is any good. These tests are about the half the store cannot
answer for itself, attached to every row of its menu.
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
        here = Dispensary(name="Bergen Botanics", slug="bergen", lat=40.68, lng=-73.97)
        cheaper = Dispensary(name="Atlantic Leaf", slug="atlantic", lat=40.68, lng=-73.96)
        dearer = Dispensary(name="Pricey Co", slug="pricey", lat=40.70, lng=-73.99)
        retired = Dispensary(name="Closed Co", slug="closed", is_active=False)
        session.add_all([here, cheaper, dearer, retired])
        session.commit()

        session.add_all([
            # On the menu under test.
            _row(here),
            _row(here, strain="House Exclusive", scraped_name="House Exclusive"),
            _row(here, scraped_brand=None, strain="Bulk Shake",
                 subtype=None, scraped_name="Bulk Shake", price_cents=1500),

            # The same Blue Dream elsewhere.
            _row(cheaper, price_cents=3500),
            _row(dearer, price_cents=5000),
            _row(retired, price_cents=100),
            _row(cheaper, price_cents=200, in_stock=False),
            _row(dearer, price_cents=300, variant="7g"),

            # The unbranded, subtype-less shake elsewhere: identity is still a
            # match, with nulls on both sides.
            _row(cheaper, scraped_brand=None, strain="Bulk Shake",
                 subtype=None, scraped_name="Bulk Shake", price_cents=1200),
        ])
        session.commit()
        return {"here": str(here.id)}


def _menu(world) -> dict[str, dict]:
    app = FastAPI()
    app.include_router(customer_router)
    rows = TestClient(app).get(f"/customer/dispensaries/{world['here']}/listings").json()
    return {row["display_name"]: row for row in rows}


def test_every_row_carries_a_comparison(world):
    assert all("market" in row for row in _menu(world).values())


def test_a_row_knows_how_many_other_stores_carry_it(world):
    assert _menu(world)["Blue Dream"]["market"]["other_store_count"] == 2


def test_a_row_knows_what_it_costs_elsewhere(world):
    market = _menu(world)["Blue Dream"]["market"]
    assert market["min_cents"] == 3500
    assert market["avg_cents"] == 4250
    assert market["max_cents"] == 5000


def test_a_closed_store_is_not_somewhere_you_can_go(world):
    # The $1.00 Blue Dream at Closed Co would otherwise be the market floor.
    assert _menu(world)["Blue Dream"]["market"]["min_cents"] == 3500


def test_an_out_of_stock_row_elsewhere_is_not_an_alternative(world):
    assert _menu(world)["Blue Dream"]["market"]["min_cents"] == 3500


def test_a_different_size_is_a_different_product(world):
    # The 7g at Pricey Co is not this 3.5g; comparing them compares nothing.
    assert _menu(world)["Blue Dream"]["market"]["min_cents"] == 3500


def test_a_product_nobody_else_carries_says_so_plainly(world):
    market = _menu(world)["House Exclusive"]["market"]
    assert market["other_store_count"] == 0
    assert market["min_cents"] is None
    assert market["is_cheapest"] is False


def test_an_unbranded_product_still_matches_its_twin(world):
    # Brand and subtype are both null on either side. SQL will not match NULL to
    # NULL, so without coalescing this row would look unique to the world.
    market = _menu(world)["Bulk Shake"]["market"]
    assert market["other_store_count"] == 1
    assert market["min_cents"] == 1200


def test_the_cheapest_store_is_told_it_is_cheapest(world):
    assert _menu(world)["Blue Dream"]["market"]["is_cheapest"] is False
    assert _menu(world)["Bulk Shake"]["market"]["is_cheapest"] is False

    with Session(engine) as session:
        row = session.exec(
            select(Listing).where(Listing.strain == "Blue Dream")
            .where(Listing.dispensary_id == UUID(world["here"]))
        ).first()
        row.price_cents = 3000
        session.add(row)
        session.commit()

    assert _menu(world)["Blue Dream"]["market"]["is_cheapest"] is True


def test_matching_the_cheapest_price_still_counts_as_cheapest(world):
    with Session(engine) as session:
        row = session.exec(
            select(Listing).where(Listing.strain == "Blue Dream")
            .where(Listing.dispensary_id == UUID(world["here"]))
        ).first()
        row.price_cents = 3500
        session.add(row)
        session.commit()

    assert _menu(world)["Blue Dream"]["market"]["is_cheapest"] is True


def test_the_menu_and_the_listing_page_agree(world):
    app = FastAPI()
    app.include_router(customer_router)
    client = TestClient(app)

    row = _menu(world)["Blue Dream"]
    detail = client.get(
        f"/customer/dispensaries/{world['here']}/listings/{row['id']}"
    ).json()

    # A card that says "2 other stores" must open a page that says the same.
    assert detail["price_context"]["other_store_count"] == row["market"]["other_store_count"]
    assert detail["price_context"]["min_cents"] == row["market"]["min_cents"]
    assert detail["price_context"]["is_cheapest"] == row["market"]["is_cheapest"]


def test_one_store_listing_it_twice_is_still_one_store(world):
    with Session(engine) as session:
        cheaper = session.exec(
            select(Dispensary).where(Dispensary.slug == "atlantic")
        ).first()
        session.add(_row(cheaper, price_cents=3600, scraped_name="Blue Dream (dupe)"))
        session.commit()

    assert _menu(world)["Blue Dream"]["market"]["other_store_count"] == 2
