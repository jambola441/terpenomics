"""GET /customer/brands/{brand}/lines/{line}: one product line of a brand,
cut from the brand's own answer."""
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
    """Jaunty with two lines and an unlined vape, across two stores."""
    with Session(engine) as session:
        north = Dispensary(name="North", slug="north", lat=40.73, lng=-73.99)
        south = Dispensary(name="South", slug="south", lat=40.68, lng=-73.97)
        session.add_all([north, south])
        session.commit()

        def vape(shop, line, strain, price, in_stock=True):
            session.add(Listing(
                dispensary_id=shop.id, scraped_name=f"Jaunty {line or ''} {strain}",
                scraped_brand="Jaunty", scraped_category="vaporizers", subtype="cartridge",
                product_line=line, strain=strain, price_cents=price,
                in_stock=in_stock, is_active=True,
            ))

        vape(north, "Palms", "Blue Dream", 3800)
        vape(south, "Palms", "Blue Dream", 4000)
        vape(north, "Palms", "Jack Herer", 4000)
        vape(north, "Palms", "Grape Ape", 4500, in_stock=False)
        vape(north, "Classic", "Gelato", 3500)
        vape(north, None, "Mango Haze", 3000)
        session.commit()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(customer_router)
    return TestClient(app)


def test_a_line_holds_only_its_own_products(catalogue):
    body = _client().get("/customer/brands/Jaunty/lines/Palms").json()
    assert body["brand"] == "Jaunty" and body["name"] == "Palms"
    assert sorted(p["strain"] for p in body["products"]) == ["Blue Dream", "Jack Herer"]
    assert all(p["product_line"] == "Palms" for p in body["products"])
    assert body["product_count"] == 2
    assert body["dispensary_count"] == 2


def test_products_keep_the_brand_page_shape(catalogue):
    brand = _client().get("/customer/brands/Jaunty").json()
    line = _client().get("/customer/brands/Jaunty/lines/Palms").json()
    in_brand = {p["key"]: p for p in brand["products"]}
    for product in line["products"]:
        assert product == in_brand[product["key"]]


def test_out_of_stock_members_come_back_on_request(catalogue):
    body = _client().get("/customer/brands/Jaunty/lines/Palms", params={"in_stock": False}).json()
    assert "Grape Ape" in [p["strain"] for p in body["products"]]


def test_a_line_the_brand_does_not_have_is_empty(catalogue):
    body = _client().get("/customer/brands/Jaunty/lines/Nowhere").json()
    assert body["products"] == [] and body["product_count"] == 0


def test_an_unknown_brand_is_404(catalogue):
    assert _client().get("/customer/brands/Nobody/lines/Palms").status_code == 404
