"""One product, every store carrying it.

The page exists so that tapping a product card always lands somewhere of the
same shape. Before this endpoint a product was reachable only through its brand,
so an unbranded one sent the shopper into a single store's shelf from the
category screen and back to a category listing from search.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from database import engine
from models import Dispensary, Listing
from routes.customer import router as customer_router

KEY = "flower||Reserve|Blue Dream|3.5g"


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
    """One product at two stores, the same key under a second brand, and an
    unbranded product that only the key can find."""
    with Session(engine) as session:
        bergen = Dispensary(name="Bergen Botanics", slug="bergen", lat=40.68, lng=-73.97)
        atlantic = Dispensary(name="Atlantic Leaf", slug="atlantic", lat=40.68, lng=-73.96)
        session.add_all([bergen, atlantic])
        session.commit()

        def row(dispensary, brand, price, **kwargs):
            return Listing(
                dispensary_id=dispensary.id,
                scraped_brand=brand,
                scraped_category=kwargs.get("category", "flower"),
                subtype=None,
                product_line=kwargs.get("product_line", "Reserve"),
                strain=kwargs.get("strain", "Blue Dream"),
                variant=kwargs.get("variant", "3.5g"),
                scraped_name=kwargs.get("scraped_name", "Blue Dream -Hybrid- | 3.5g"),
                price_cents=price,
                in_stock=kwargs.get("in_stock", True),
                is_active=True,
            )

        session.add_all([
            row(bergen, "Aeris", 4500),
            row(atlantic, "Aeris", 4200),
            # Same key, different brand: a different product.
            row(bergen, "Botanica", 3900),
            # No brand at all -- the case that had no product page before.
            row(bergen, None, 900, product_line=None, strain=None, variant=None,
                scraped_name="RAW Classic Cones - 1 1/4 6 Pack", category="merch"),
            # Out of stock, so it stays out of the default response.
            row(atlantic, "Aeris", 5000, variant="7g", in_stock=False),
        ])
        session.commit()
        return {"bergen": str(bergen.id), "atlantic": str(atlantic.id)}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(customer_router)
    return TestClient(app)


def _get(client, **params):
    return client.get("/customer/products/detail", params=params)


def test_a_product_gathers_every_store_carrying_it(catalogue):
    body = _get(_client(), key=KEY, brand="Aeris").json()
    assert body["name"] == "Reserve Blue Dream"
    assert body["dispensary_count"] == 2
    assert sorted(o["dispensary_name"] for o in body["offerings"]) == ["Atlantic Leaf", "Bergen Botanics"]
    assert body["min_price_cents"] == 4200


def test_brand_scopes_the_key(catalogue):
    # The same five-part key exists under two brands; they are two products.
    aeris = _get(_client(), key=KEY, brand="Aeris").json()
    botanica = _get(_client(), key=KEY, brand="Botanica").json()
    assert aeris["dispensary_count"] == 2
    assert botanica["dispensary_count"] == 1
    assert botanica["min_price_cents"] == 3900


def test_an_unbranded_product_has_a_page(catalogue):
    body = _get(_client(), key="merch||||").json()
    assert body["brand"] is None
    assert body["name"] == "RAW Classic Cones"
    assert len(body["offerings"]) == 1


def test_no_brand_means_unbranded_not_any_brand(catalogue):
    # Omitting the brand must not quietly match the branded rows with this key.
    assert _get(_client(), key=KEY).status_code == 404


def test_out_of_stock_offerings_are_excluded_by_default(catalogue):
    key_7g = "flower||Reserve|Blue Dream|7g"
    assert _get(_client(), key=key_7g, brand="Aeris").status_code == 404
    assert _get(_client(), key=key_7g, brand="Aeris", in_stock=False).status_code == 200


def test_a_key_matching_nothing_is_a_404(catalogue):
    assert _get(_client(), key="flower||Reserve|Nonexistent|3.5g", brand="Aeris").status_code == 404


def test_a_malformed_key_is_rejected(catalogue):
    assert _get(_client(), key="flower|too|few").status_code == 400


def test_the_key_round_trips_from_the_brand_page(catalogue):
    """The brand page builds the keys; this endpoint has to accept them verbatim."""
    brand = _client().get("/customer/brands/Aeris").json()
    for product in brand["products"]:
        detail = _get(_client(), key=product["key"], brand="Aeris").json()
        assert detail["name"] == product["name"]
        assert detail["dispensary_count"] == product["dispensary_count"]
