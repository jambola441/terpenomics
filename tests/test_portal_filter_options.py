"""A store's filter options name the categories it has in stock, with counts,
so its page shows a rail for each and none for the ones it doesn't carry."""
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


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(customer_router)
    return TestClient(app)


def test_categories_count_in_stock_active_listings_biggest_first():
    with Session(engine) as session:
        shop = Dispensary(name="Bergen Botanics", slug="bergen")
        other = Dispensary(name="Elsewhere", slug="elsewhere")
        session.add_all([shop, other])
        session.commit()
        rows = [("flower", True, True)] * 3 + [("edible", True, True)] * 2 + [
            ("vaporizers", False, True),   # out of stock: not on the shelf
            ("tincture", True, False),     # delisted
            (None, True, True),            # uncategorised
        ]
        for i, (category, in_stock, active) in enumerate(rows):
            session.add(Listing(
                dispensary_id=shop.id, scraped_name=f"item {i}", scraped_category=category,
                price_cents=1000, in_stock=in_stock, is_active=active,
            ))
        session.add(Listing(
            dispensary_id=other.id, scraped_name="theirs", scraped_category="topical",
            price_cents=1000, in_stock=True, is_active=True,
        ))
        session.commit()
        shop_id = shop.id

    body = _client().get(f"/customer/dispensaries/{shop_id}/filter-options").json()
    assert body["categories"] == [{"name": "flower", "count": 3}, {"name": "edible", "count": 2}]
