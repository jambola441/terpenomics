"""Logging an in-store purchase for a customer, as the admin customer page does.

The page creates the purchase, adds items by listing, finalizes it, then reads
the customer's purchases back with each listing's terpene profile beside the
feedback controls. Pins that round trip, which broke silently when purchases
moved from products to listings.
"""
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser
from database import engine
from models import Customer, Dispensary, Listing, ListingTerpene, Purchase, PurchaseItem, Terpene
from routes.admin import router as admin_router
from routes.admin.auth import require_admin


def _clear():
    with Session(engine) as session:
        for model in (PurchaseItem, Purchase, ListingTerpene, Terpene, Listing, Dispensary, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    _clear()
    yield
    # Other suites clear listings without knowing about terpene links, so
    # leave nothing behind that would block their deletes.
    _clear()


@pytest.fixture
def world():
    with Session(engine) as session:
        customer = Customer(name="Ada", phone="+15552030001", auth_user_id=uuid4())
        store = Dispensary(name="Bergen Botanics", slug="bergen")
        session.add_all([customer, store])
        session.commit()

        profiled = Listing(dispensary_id=store.id, scraped_name="Sunset Sherbet 3.5g", price_cents=4500)
        bare = Listing(dispensary_id=store.id, scraped_name="Mystery Gummies", price_cents=2000)
        myrcene, limonene = Terpene(name="Myrcene"), Terpene(name="Limonene")
        session.add_all([profiled, bare, myrcene, limonene])
        session.commit()
        session.add_all([
            ListingTerpene(listing_id=profiled.id, terpene_id=limonene.id, percent=0.4),
            ListingTerpene(listing_id=profiled.id, terpene_id=myrcene.id, percent=1.2),
        ])
        session.commit()
        return {"customer_id": str(customer.id), "profiled": str(profiled.id), "bare": str(bare.id)}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
        user_id="admin", email=None, phone=None, role="admin", raw_claims={},
    )
    return TestClient(app)


def _log_purchase(client, customer_id, items):
    purchase = client.post("/admin/purchases", json={"customer_id": customer_id, "source": "manual"})
    assert purchase.status_code == 200, purchase.text
    pid = purchase.json()["id"]
    added = client.post(f"/admin/purchases/{pid}/items/batch", json=items)
    assert added.status_code == 200, added.text
    done = client.post(f"/admin/purchases/{pid}/finalize")
    assert done.status_code == 200, done.text
    return done.json()


def test_a_purchase_is_logged_by_listing(client, world):
    done = _log_purchase(client, world["customer_id"], [
        {"listing_id": world["profiled"], "quantity": 2, "line_amount_cents": 9000},
        {"listing_id": world["bare"], "quantity": 1, "line_amount_cents": 2000},
    ])
    assert done["total_amount_cents"] == 11000


def test_items_carry_their_listings_terpenes_strongest_first(client, world):
    _log_purchase(client, world["customer_id"], [
        {"listing_id": world["profiled"], "quantity": 1, "line_amount_cents": 4500},
        {"listing_id": world["bare"], "quantity": 1, "line_amount_cents": 2000},
    ])
    [purchase] = client.get(f"/admin/customers/{world['customer_id']}/purchases").json()
    by_listing = {i["listing_id"]: i for i in purchase["items"]}

    assert [t["name"] for t in by_listing[world["profiled"]]["terpenes"]] == ["Myrcene", "Limonene"]
    # No lab data is an empty profile, not a missing key.
    assert by_listing[world["bare"]]["terpenes"] == []


def test_a_customer_with_no_purchases_gets_an_empty_list(client, world):
    assert client.get(f"/admin/customers/{world['customer_id']}/purchases").json() == []
