"""Pickup orders: placing one, seeing your own, and the fulfillment lifecycle.

The security-relevant properties get their own tests, because they are the ones
that would be expensive to get wrong: an order is bound to the caller's token
rather than a client-supplied id, and totals come from the listing rather than
the request body.
"""
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import (
    Customer,
    Dispensary,
    Listing,
    Order,
    OrderItem,
    OrderStatus,
    PosType,
)
from routes.admin.auth import require_admin
from routes.admin.orders import router as admin_orders_router
from routes.orders import MAX_OPEN_ORDERS, router as orders_router

AUTH_UID = uuid4()
OTHER_UID = uuid4()


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (OrderItem, Order, Listing, Dispensary, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


@pytest.fixture
def world():
    """A pickup-enabled store with two listings, plus a second store that is not."""
    with Session(engine) as session:
        customer = Customer(name="Ada", phone="+15552010001", auth_user_id=AUTH_UID)
        other = Customer(name="Grace", phone="+15552010002", auth_user_id=OTHER_UID)
        shop = Dispensary(
            name="Brooklyn Organic Buds", slug="bob", accepts_pickup=True,
            pos_type=PosType.alleaves, address="623 Bergen St",
        )
        closed = Dispensary(name="No Pickup", slug="nope", accepts_pickup=False)
        session.add_all([customer, other, shop, closed])
        session.commit()

        flower = Listing(
            dispensary_id=shop.id, scraped_name="Sunset Sherbet", scraped_brand="Aeris",
            variant="3.5g", price_cents=4500, in_stock=True, is_active=True,
        )
        vape = Listing(
            dispensary_id=shop.id, scraped_name="Blue Dream Cart", scraped_brand="Aeris",
            variant="1g", price_cents=6000, in_stock=True, is_active=True,
        )
        elsewhere = Listing(
            dispensary_id=closed.id, scraped_name="Other Store Item",
            price_cents=1000, in_stock=True, is_active=True,
        )
        session.add_all([flower, vape, elsewhere])
        session.commit()

        return {
            "customer_id": customer.id, "other_id": other.id,
            "shop_id": shop.id, "closed_id": closed.id,
            "flower_id": flower.id, "vape_id": vape.id, "elsewhere_id": elsewhere.id,
        }


def _app(auth_uid=AUTH_UID, admin=True):
    app = FastAPI()
    app.include_router(orders_router)
    app.include_router(admin_orders_router, prefix="/admin")
    if auth_uid is not None:
        app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
            user_id=str(auth_uid), email=None, phone=None,
            role="authenticated", raw_claims={},
        )
    if admin:
        app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
            user_id="admin", email=None, phone=None, role="admin", raw_claims={},
        )
    return TestClient(app)


@pytest.fixture
def client():
    return _app()


def _order_body(world, qty=1):
    return {
        "dispensary_id": str(world["shop_id"]),
        "items": [{"listing_id": str(world["flower_id"]), "quantity": qty}],
    }


# ---------------------------
# Creating an order
# ---------------------------

def test_submitting_a_cart_creates_an_order(client, world):
    resp = client.post("/me/orders", json={
        "dispensary_id": str(world["shop_id"]),
        "items": [
            {"listing_id": str(world["flower_id"]), "quantity": 2},
            {"listing_id": str(world["vape_id"]), "quantity": 1},
        ],
        "note": "  ring the bell  ",
    })
    assert resp.status_code == 201
    body = resp.json()

    assert body["status"] == "submitted"
    assert body["total_amount_cents"] == 4500 * 2 + 6000
    assert body["dispensary_name"] == "Brooklyn Organic Buds"
    assert body["note"] == "ring the bell"
    assert len(body["pickup_code"]) == 6
    assert {i["name"] for i in body["items"]} == {"Sunset Sherbet", "Blue Dream Cart"}


def test_the_order_says_payment_happens_at_pickup(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()
    assert body["payment_method"] == "pay_at_pickup"


def test_totals_come_from_the_listing_not_the_request(client, world):
    """A client that invents its own prices is ignored."""
    resp = client.post("/me/orders", json={
        "dispensary_id": str(world["shop_id"]),
        "items": [{
            "listing_id": str(world["flower_id"]),
            "quantity": 1,
            # None of these are fields the endpoint accepts; if the model ever
            # grew looser they would be the way to underpay.
            "price_cents": 1,
            "line_amount_cents": 1,
            "unit_price_cents": 1,
        }],
        "total_amount_cents": 1,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["total_amount_cents"] == 4500
    assert body["items"][0]["unit_price_cents"] == 4500


def test_the_order_binds_to_the_token_not_a_supplied_customer_id(client, world):
    """customer_id in the body is not a way to order as someone else."""
    resp = client.post("/me/orders", json={
        **_order_body(world),
        "customer_id": str(world["other_id"]),
    })
    assert resp.status_code == 201
    with Session(engine) as session:
        order = session.exec(select(Order)).one()
        assert order.customer_id == world["customer_id"]


def test_items_are_snapshotted_against_later_scrapes(client, world):
    """A re-scrape must not rewrite what the customer ordered."""
    body = client.post("/me/orders", json=_order_body(world)).json()

    with Session(engine) as session:
        listing = session.get(Listing, world["flower_id"])
        listing.scraped_name = "Renamed By Scraper"
        listing.price_cents = 9900
        session.add(listing)
        session.commit()

    again = client.get(f"/me/orders/{body['id']}").json()
    assert again["items"][0]["name"] == "Sunset Sherbet"
    assert again["items"][0]["unit_price_cents"] == 4500
    assert again["total_amount_cents"] == 4500


def test_repeated_listings_merge_into_one_line(client, world):
    body = client.post("/me/orders", json={
        "dispensary_id": str(world["shop_id"]),
        "items": [
            {"listing_id": str(world["flower_id"]), "quantity": 1},
            {"listing_id": str(world["flower_id"]), "quantity": 2},
        ],
    }).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 3
    assert body["total_amount_cents"] == 4500 * 3


def test_a_store_that_does_not_take_pickup_is_refused(client, world):
    resp = client.post("/me/orders", json={
        "dispensary_id": str(world["closed_id"]),
        "items": [{"listing_id": str(world["elsewhere_id"]), "quantity": 1}],
    })
    assert resp.status_code == 409
    assert "not accepting" in resp.json()["detail"]


def test_items_from_another_store_are_refused(client, world):
    resp = client.post("/me/orders", json={
        "dispensary_id": str(world["shop_id"]),
        "items": [{"listing_id": str(world["elsewhere_id"]), "quantity": 1}],
    })
    assert resp.status_code == 422
    assert "same dispensary" in resp.json()["detail"]


def test_an_out_of_stock_item_is_refused(client, world):
    with Session(engine) as session:
        listing = session.get(Listing, world["flower_id"])
        listing.in_stock = False
        session.add(listing)
        session.commit()

    resp = client.post("/me/orders", json=_order_body(world))
    assert resp.status_code == 409
    assert "no longer available" in resp.json()["detail"]


def test_an_unknown_listing_is_refused(client, world):
    resp = client.post("/me/orders", json={
        "dispensary_id": str(world["shop_id"]),
        "items": [{"listing_id": str(uuid4()), "quantity": 1}],
    })
    assert resp.status_code == 404


def test_an_empty_cart_is_refused(client, world):
    resp = client.post("/me/orders", json={
        "dispensary_id": str(world["shop_id"]), "items": [],
    })
    assert resp.status_code == 422


def test_open_orders_are_capped(client, world):
    for _ in range(MAX_OPEN_ORDERS):
        assert client.post("/me/orders", json=_order_body(world)).status_code == 201
    resp = client.post("/me/orders", json=_order_body(world))
    assert resp.status_code == 429

    # Closing one frees a slot.
    with Session(engine) as session:
        order = session.exec(select(Order)).first()
        order.status = OrderStatus.completed
        session.add(order)
        session.commit()
    assert client.post("/me/orders", json=_order_body(world)).status_code == 201


def test_ordering_requires_a_token(world):
    app = FastAPI()
    app.include_router(orders_router)
    resp = TestClient(app).post("/me/orders", json=_order_body(world))
    assert resp.status_code == 401


def test_an_unlinked_account_cannot_order(world):
    """A valid token with no customer row is not an order."""
    resp = _app(auth_uid=uuid4()).post("/me/orders", json=_order_body(world))
    assert resp.status_code == 404


# ---------------------------
# Reading your orders
# ---------------------------

def test_you_only_see_your_own_orders(client, world):
    client.post("/me/orders", json=_order_body(world))

    mine = client.get("/me/orders").json()
    assert len(mine) == 1

    theirs = _app(auth_uid=OTHER_UID).get("/me/orders").json()
    assert theirs == []


def test_another_customers_order_reads_as_missing(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()
    resp = _app(auth_uid=OTHER_UID).get(f"/me/orders/{body['id']}")
    assert resp.status_code == 404


def test_orders_come_back_newest_first(client, world):
    first = client.post("/me/orders", json=_order_body(world)).json()
    second = client.post("/me/orders", json=_order_body(world)).json()

    with Session(engine) as session:
        older = session.get(Order, UUID(first["id"]))
        older.submitted_at = older.submitted_at.replace(year=2020)
        session.add(older)
        session.commit()

    ids = [o["id"] for o in client.get("/me/orders").json()]
    assert ids == [second["id"], first["id"]]


# ---------------------------
# Cancelling
# ---------------------------

def test_a_customer_can_cancel_their_own_order(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()
    resp = client.post(f"/me/orders/{body['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["cancelled_at"] is not None


def test_cancelling_twice_is_refused(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()
    client.post(f"/me/orders/{body['id']}/cancel")
    assert client.post(f"/me/orders/{body['id']}/cancel").status_code == 409


def test_you_cannot_cancel_someone_elses_order(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()
    resp = _app(auth_uid=OTHER_UID).post(f"/me/orders/{body['id']}/cancel")
    assert resp.status_code == 404


# ---------------------------
# Admin fulfillment
# ---------------------------

def test_admin_sees_submitted_orders(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()

    rows = client.get("/admin/orders").json()
    assert len(rows) == 1
    assert rows[0]["id"] == body["id"]
    assert rows[0]["pickup_code"] == body["pickup_code"]
    assert rows[0]["customer_name"] == "Ada"
    assert rows[0]["item_count"] == 1


def test_admin_can_filter_by_status(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()
    client.post(f"/admin/orders/{body['id']}/status", json={"status": "ready"})

    assert len(client.get("/admin/orders?status=ready").json()) == 1
    assert client.get("/admin/orders?status=submitted").json() == []


def test_the_lifecycle_advances_and_stamps_times(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()

    ready = client.post(f"/admin/orders/{body['id']}/status", json={"status": "ready"}).json()
    assert ready["status"] == "ready"
    assert ready["ready_at"] is not None
    assert ready["allowed_transitions"] == ["cancelled", "completed"]

    done = client.post(f"/admin/orders/{body['id']}/status", json={"status": "completed"}).json()
    assert done["status"] == "completed"
    assert done["completed_at"] is not None
    assert done["allowed_transitions"] == []


def test_illegal_transitions_are_refused(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()

    # submitted -> completed skips the queue
    skip = client.post(f"/admin/orders/{body['id']}/status", json={"status": "completed"})
    assert skip.status_code == 409

    client.post(f"/admin/orders/{body['id']}/status", json={"status": "cancelled"})
    reopen = client.post(f"/admin/orders/{body['id']}/status", json={"status": "ready"})
    assert reopen.status_code == 409
    assert "terminal state" in reopen.json()["detail"]


def test_admin_endpoints_require_admin(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()

    app = FastAPI()
    app.include_router(admin_orders_router, prefix="/admin")
    anon = TestClient(app)
    assert anon.get("/admin/orders").status_code == 401
    assert anon.post(f"/admin/orders/{body['id']}/status", json={"status": "ready"}).status_code == 401


def test_admin_detail_carries_contact_details_for_the_counter(client, world):
    body = client.post("/me/orders", json=_order_body(world)).json()
    detail = client.get(f"/admin/orders/{body['id']}").json()
    assert detail["customer_phone"] == "+15552010001"
    assert detail["payment_method"] == "pay_at_pickup"
    assert detail["items"][0]["name"] == "Sunset Sherbet"
