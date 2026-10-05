"""A store's typo stays its own variant; the product's size is what pages group on.

listings.size holds the catalog's size when the store mistyped it (Camino's 100mg
20-pack listed as 50mg); NULL, on rows not re-imported since, reads as the variant.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from database import engine
from models import Dispensary, Listing
from routes.customer import router as customer_router
from services.market import context_for

KEY = "edible|gummy|Gummies|Balance Yuzu Lemon|100mg"


@pytest.fixture
def shelves():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (Listing, Dispensary):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
        stores = [Dispensary(name=n, slug=n.lower(), lat=40.7, lng=-73.9) for n in ("Bergen", "Atlantic", "Court")]
        session.add_all(stores)
        session.commit()
        common = dict(scraped_brand="Camino", scraped_category="edible", subtype="gummy",
                      product_line="Gummies", strain="Balance Yuzu Lemon", in_stock=True, is_active=True,
                      scraped_name="Camino Yuzu Lemon 'Balance' Gummies [20pk]")
        rows = [
            Listing(dispensary_id=stores[0].id, variant="100mg", size="100mg", price_cents=2000, **common),
            Listing(dispensary_id=stores[1].id, variant="50mg", size="100mg", price_cents=1800, **common),
            Listing(dispensary_id=stores[2].id, variant="100mg", size=None, price_cents=2200, **common),
        ]
        session.add_all(rows)
        session.commit()
        return [(r.id, r.dispensary_id) for r in rows]


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(customer_router)
    return TestClient(app)


def test_a_mistyped_listing_is_on_its_products_page(shelves):
    body = _client().get("/customer/products/detail", params={"key": KEY, "brand": "Camino"}).json()
    assert body["variant"] == "100mg" and body["dispensary_count"] == 3
    typo = KEY.replace("100mg", "50mg")
    assert _client().get("/customer/products/detail", params={"key": typo, "brand": "Camino"}).status_code == 404


def test_its_price_is_compared_with_the_product_elsewhere(shelves):
    with Session(engine) as session:
        market = context_for(session, [listing_id for listing_id, _ in shelves])
    assert {m["other_store_count"] for m in market.values()} == {2}
    assert market[str(shelves[1][0])]["is_cheapest"]


def test_the_listing_shows_the_products_size(shelves):
    listing_id, store = shelves[1]
    body = _client().get(f"/customer/dispensaries/{store}/listings/{listing_id}").json()
    assert body["variant"] == "100mg" and body["product_key"] == KEY
