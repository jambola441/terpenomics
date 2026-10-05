"""Receipt uploads with human review (connectors/receipts.py and its routes).

What matters: a customer can only upload real photos for real partners and only
sees their own receipts; points come from the reviewer's subtotal at the usual
rate and pending rule; a receipt is reviewed once; voiding takes the points back;
and the reviewer is shown likely duplicates.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from connectors.points import balance
from connectors.store import as_utc, upsert_orders, utcnow
from database import engine
from models import Customer, Partner, PartnerMember, PointsEntry, ReceiptSubmission
from routes.admin.auth import require_admin
from routes.admin.receipts import router as admin_receipts_router
from routes.customer_receipts import router as customer_receipts_router
from tests.test_pos_connectors import TABLES as POS_TABLES, make_connection, norm

TABLES = POS_TABLES + [PartnerMember.__table__, PointsEntry.__table__, ReceiptSubmission.__table__]
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2000
TODAY = utcnow().date()


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    monkeypatch.delenv("POINTS_PER_DOLLAR", raising=False)
    SQLModel.metadata.drop_all(engine, tables=list(reversed(TABLES)))
    SQLModel.metadata.create_all(engine, tables=TABLES)
    yield


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


@pytest.fixture
def world(session):
    conn = make_connection(session)                  # partner "Bean Co"
    ada = Customer(name="Ada", phone="+16465550101", auth_user_id=uuid4())
    bob = Customer(name="Bob", phone="+16465550102", auth_user_id=uuid4())
    closed = Partner(name="Gone", slug="gone", is_active=False)
    session.add_all([ada, bob, closed])
    session.commit()
    return {"conn": conn, "partner_id": conn.partner_id, "ada": ada, "bob": bob, "closed": closed}


@pytest.fixture
def client(world):
    app = FastAPI()
    app.include_router(customer_receipts_router)
    app.include_router(admin_receipts_router, prefix="/admin")
    who = {"customer": world["ada"]}

    def current_user():
        c = who["customer"]
        return SupabaseAuthUser(user_id=str(c.auth_user_id), email=None, phone=c.phone,
                                role="authenticated", raw_claims={})

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
        user_id="admin", email="admin@terpee.com", phone=None, role="admin", raw_claims={})
    c = TestClient(app)
    c.who = who
    return c


def upload(client, partner_id, *, day=TODAY, data=JPEG, ctype="image/jpeg", note=None):
    form = {"partner_id": str(partner_id), "purchased_on": day.isoformat()}
    if note:
        form["note"] = note
    return client.post("/me/receipts", data=form, files={"image": ("r.jpg", data, ctype)})


# ----------------------------------------------------------------------
# Customer side
# ----------------------------------------------------------------------

def test_customer_lists_active_partners_only(client, world):
    names = [p["name"] for p in client.get("/me/partners").json()]
    assert names == ["Bean Co"]


def test_upload_and_see_it_pending(client, world):
    r = upload(client, world["partner_id"], note="  paid cash  ")
    assert r.status_code == 201
    body = r.json()
    assert (body["status"], body["partner_name"], body["customer_note"]) == ("pending", "Bean Co", "paid cash")
    mine = client.get("/me/receipts").json()
    assert [x["id"] for x in mine] == [body["id"]]


@pytest.mark.parametrize("kwargs, message", [
    ({"data": b""}, "empty"),
    ({"ctype": "application/pdf"}, "photo"),
    ({"day": TODAY + timedelta(days=3)}, "future"),
])
def test_bad_uploads_are_refused(client, world, kwargs, message):
    r = upload(client, world["partner_id"], **kwargs)
    assert r.status_code == 422 and message in r.json()["detail"]


def test_inactive_or_unknown_partner_is_refused(client, world):
    assert upload(client, world["closed"].id).status_code == 422
    assert upload(client, uuid4()).status_code == 422


def test_pending_uploads_are_capped(client, world, monkeypatch):
    from connectors import receipts
    monkeypatch.setattr(receipts, "MAX_PENDING_PER_CUSTOMER", 2)
    assert upload(client, world["partner_id"]).status_code == 201
    assert upload(client, world["partner_id"]).status_code == 201
    r = upload(client, world["partner_id"])
    assert r.status_code == 422 and "too many" in r.json()["detail"]


def test_customers_only_see_their_own_receipts(client, world):
    upload(client, world["partner_id"])
    client.who["customer"] = world["bob"]
    assert client.get("/me/receipts").json() == []


# ----------------------------------------------------------------------
# Review
# ----------------------------------------------------------------------

def test_reviewer_sees_queue_photo_and_approves(client, world, session):
    rid = upload(client, world["partner_id"], day=TODAY - timedelta(days=1)).json()["id"]

    queue = client.get("/admin/receipts").json()
    assert queue["counts"] == {"pending": 1, "approved": 0, "rejected": 0}
    assert queue["items"][0]["customer_name"] == "Ada"

    img = client.get(f"/admin/receipts/{rid}/image")
    assert img.status_code == 200 and img.content == JPEG and img.headers["content-type"] == "image/jpeg"

    detail = client.post(f"/admin/receipts/{rid}/approve", json={
        "subtotal_cents": 2350, "purchased_on": (TODAY - timedelta(days=1)).isoformat(),
    }).json()
    assert (detail["status"], detail["subtotal_cents"], detail["points"]) == ("approved", 2350, 23)
    assert detail["reviewed_by"] == "admin@terpee.com"

    (entry,) = session.exec(select(PointsEntry)).all()
    assert (entry.kind, entry.points, entry.eligible_cents, entry.pos_order_id) == ("receipt", 23, 2350, None)
    assert as_utc(entry.available_at).date() == TODAY - timedelta(days=1) + timedelta(days=7)
    assert balance(session, world["ada"].id).pending == 23

    mine = client.get("/me/receipts").json()[0]
    assert (mine["status"], mine["points"]) == ("approved", 23)


def test_old_receipt_points_are_available_at_once(client, world, session):
    day = TODAY - timedelta(days=20)
    rid = upload(client, world["partner_id"], day=day).json()["id"]
    client.post(f"/admin/receipts/{rid}/approve", json={"subtotal_cents": 1000, "purchased_on": day.isoformat()})
    assert balance(session, world["ada"].id).available == 10


def test_reviewer_can_correct_the_store(client, world, session):
    other = Partner(name="Pasta", slug="pasta")
    session.add(other)
    session.commit()
    rid = upload(client, world["partner_id"]).json()["id"]
    detail = client.post(f"/admin/receipts/{rid}/approve", json={
        "subtotal_cents": 500, "purchased_on": TODAY.isoformat(), "partner_id": str(other.id),
    }).json()
    assert detail["partner_name"] == "Pasta"
    assert session.exec(select(PointsEntry)).one().partner_id == other.id


def test_receipt_is_reviewed_once(client, world, session):
    rid = upload(client, world["partner_id"]).json()["id"]
    ok = {"subtotal_cents": 1000, "purchased_on": TODAY.isoformat()}
    assert client.post(f"/admin/receipts/{rid}/approve", json=ok).status_code == 200
    assert client.post(f"/admin/receipts/{rid}/approve", json=ok).status_code == 409
    assert client.post(f"/admin/receipts/{rid}/reject", json={"reason": "x"}).status_code == 409
    assert len(session.exec(select(PointsEntry)).all()) == 1


def test_reject_needs_a_reason_and_customer_sees_it(client, world, session):
    rid = upload(client, world["partner_id"]).json()["id"]
    assert client.post(f"/admin/receipts/{rid}/reject", json={"reason": "  "}).status_code == 422
    assert client.post(f"/admin/receipts/{rid}/reject", json={"reason": "Not a Bean Co receipt"}).status_code == 200
    mine = client.get("/me/receipts").json()[0]
    assert (mine["status"], mine["reject_reason"]) == ("rejected", "Not a Bean Co receipt")
    assert session.exec(select(PointsEntry)).all() == []


def test_void_takes_the_points_back(client, world, session):
    rid = upload(client, world["partner_id"]).json()["id"]
    client.post(f"/admin/receipts/{rid}/approve", json={"subtotal_cents": 1000, "purchased_on": TODAY.isoformat()})
    assert client.post(f"/admin/receipts/{rid}/void", json={"reason": "duplicate of a synced order"}).status_code == 200
    entries = session.exec(select(PointsEntry).order_by(PointsEntry.created_at)).all()
    assert [(e.kind, e.points) for e in entries] == [("receipt", 10), ("adjust", -10)]
    assert as_utc(entries[1].available_at) == as_utc(entries[0].available_at)  # cancels while still pending
    assert balance(session, world["ada"].id).total == 0
    assert client.post(f"/admin/receipts/{rid}/void", json={"reason": "again"}).status_code == 409


@pytest.mark.parametrize("subtotal", [0, -5, 2_000_000])
def test_bad_subtotals_are_refused(client, world, subtotal):
    rid = upload(client, world["partner_id"]).json()["id"]
    r = client.post(f"/admin/receipts/{rid}/approve", json={"subtotal_cents": subtotal, "purchased_on": TODAY.isoformat()})
    assert r.status_code == 422


# ----------------------------------------------------------------------
# Duplicates
# ----------------------------------------------------------------------

def test_reviewer_is_shown_likely_duplicates(client, world, session):
    first = upload(client, world["partner_id"], day=TODAY - timedelta(days=1)).json()["id"]
    second = upload(client, world["partner_id"], day=TODAY).json()["id"]

    # A synced order at the same store yesterday, already matched to Ada.
    rows, _, _ = upsert_orders(session, world["conn"], [norm("O1", total=2500, ordered=utcnow() - timedelta(days=1))], {})
    rows[0].customer_id = world["ada"].id
    rows[0].tax_cents = 200
    session.add(rows[0])
    session.commit()

    detail = client.get(f"/admin/receipts/{second}").json()
    assert [d["id"] for d in detail["duplicate_receipts"]] == [first]
    (order,) = detail["nearby_orders"]
    assert (order["same_customer"], order["subtotal_cents"]) == (True, 2300)
    assert detail["stale"] is False
    assert detail["points_per_dollar"] == 1


def test_old_receipts_are_flagged_stale(client, world):
    rid = upload(client, world["partner_id"], day=TODAY - timedelta(days=45)).json()["id"]
    assert client.get(f"/admin/receipts/{rid}").json()["stale"] is True
