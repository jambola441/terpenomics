"""Receipt reader and approval by POS order (connectors/receipt_reader.py,
connectors/receipts.approve_order).

What matters: the reader stores Claude's reading and never decides anything;
failures are recorded and retried a bounded number of times; the reading is
matched to the partner's synced orders by total, card, time and receipt number;
the flags catch what a reviewer must see (not a receipt, wrong store, a sale
that already earned, someone else's sale); approving by order claims it, earns
from the POS amounts, and can't be repeated; voiding gives the order back.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from auth import SupabaseAuthUser, get_current_user

from connectors import receipt_reader as reader
from connectors.points import balance
from connectors.store import utcnow
from database import engine
from models import (
    Customer, Partner, PartnerLocation, PartnerMember, PointsEntry, PosCustomerLink, PosOrder, ReceiptSubmission,
)
from routes.admin.auth import require_admin
from routes.admin.receipts import router as admin_receipts_router
from routes.customer_receipts import router as customer_receipts_router
from tests.test_pos_connectors import TABLES as POS_TABLES, make_connection
from tests.test_receipts import JPEG, upload

TABLES = POS_TABLES + [PartnerMember.__table__, PointsEntry.__table__, ReceiptSubmission.__table__]
NY = ZoneInfo("America/New_York")
DAY = utcnow().astimezone(NY).date() - timedelta(days=1)


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
    conn = make_connection(session)
    conn.last_synced_at = utcnow()
    loc = PartnerLocation(partner_id=conn.partner_id, connection_id=conn.id, external_location_id="L1",
                          name="Bean Co Court St", timezone="America/New_York")
    ada = Customer(name="Ada", phone="+16465550101", auth_user_id=uuid4())
    bob = Customer(name="Bob", phone="+16465550102", auth_user_id=uuid4())
    plain = Partner(name="Pasta Night", slug="pasta-night")   # no POS connected
    session.add_all([conn, loc, ada, bob, plain])
    session.commit()
    return {"conn": conn, "loc": loc, "partner_id": conn.partner_id, "ada": ada, "bob": bob, "plain": plain}


@pytest.fixture
def client(world):
    """Ada as the signed-in customer, and an admin for the review routes."""
    app = FastAPI()
    app.include_router(customer_receipts_router)
    app.include_router(admin_receipts_router, prefix="/admin")
    ada = world["ada"]
    app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
        user_id=str(ada.auth_user_id), email=None, phone=ada.phone, role="authenticated", raw_claims={})
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
        user_id="admin", email="admin@terpee.com", phone=None, role="admin", raw_claims={})
    return TestClient(app)


def order(session, world, ext, *, total=1579, tax=129, tip=0, at=time(14, 5), day=DAY, last4="1004",
          payment="bBC6HQ4mKTgHarGoohYzf5pU", customer=None, state="completed"):
    local = datetime.combine(day, at, tzinfo=NY)
    o = PosOrder(
        connection_id=world["conn"].id, partner_id=world["partner_id"], partner_location_id=world["loc"].id,
        external_order_id=ext, state=state, total_cents=total, tax_cents=tax, tip_cents=tip,
        ordered_at=local.astimezone(timezone.utc), external_updated_at=local.astimezone(timezone.utc),
        customer_id=customer, matched_via="phone" if customer else None,
        raw={"id": ext, "tenders": [{"id": payment, "payment_id": payment, "type": "CARD",
                                      "card_details": {"card": {"card_brand": "MASTERCARD", "last_4": last4}}}]},
    )
    session.add(o)
    session.commit()
    return o


def receipt(session, world, *, partner=None, customer=None, read=None, day=DAY, image=JPEG):
    r = ReceiptSubmission(
        customer_id=(customer or world["ada"]).id, partner_id=partner or world["partner_id"],
        image=image, image_sha256=reader.image_hash(image), purchased_on=day, read_result=read,
        read_at=utcnow() if read else None,
    )
    session.add(r)
    session.commit()
    return r


def reading(**over):
    base = {
        "is_receipt": True, "legible": True, "merchant_name": "BEAN CO", "partner_id": None,
        "purchase_date": DAY.isoformat(), "purchase_time": "14:07", "subtotal_cents": 1450,
        "tax_cents": 129, "tip_cents": 0, "total_cents": 1579, "card_brand": "MASTERCARD",
        "card_last4": "1004", "receipt_number": None, "confidence": "high", "notes": None,
    }
    return {**base, **over}


class FakeClient:
    def __init__(self, result=None, fail=None, stop="end_turn"):
        self.calls = []
        self.result, self.fail, self.stop = result, fail, stop
        self.messages = SimpleNamespace(parse=self.parse)

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail
        return SimpleNamespace(stop_reason=self.stop, parsed_output=self.result)


def codes(review):
    return {f["code"] for f in review["flags"]}


# ----------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------

def test_read_pending_stores_the_reading_once(session, world):
    r = receipt(session, world)
    r.image_sha256 = None
    session.add(r)
    session.commit()
    fake = FakeClient(result=reader.ReceiptRead(**reading(partner_id=str(world["partner_id"]))))

    assert reader.read_pending(session, client=fake) == {"read": 1, "failed": 0, "skipped": 0}
    session.refresh(r)
    assert r.read_result["total_cents"] == 1579 and r.read_model == reader.MODEL and r.read_error is None
    assert r.image_sha256 == reader.image_hash(JPEG)
    # The image went as base64 JPEG with the partner list; the schema is the output format.
    sent = fake.calls[0]
    assert sent["output_format"] is reader.ReceiptRead
    assert sent["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"
    assert "Bean Co" in sent["messages"][0]["content"][1]["text"]

    assert reader.read_pending(session, client=fake) == {"read": 0, "failed": 0, "skipped": 0}
    assert len(fake.calls) == 1


def test_failures_are_recorded_and_retried_a_bounded_number_of_times(session, world):
    r = receipt(session, world)
    fake = FakeClient(fail=RuntimeError("overloaded"))
    for _ in range(reader.MAX_ATTEMPTS + 2):
        reader.read_pending(session, client=fake)
    session.refresh(r)
    assert r.read_attempts == reader.MAX_ATTEMPTS and r.read_result is None and "overloaded" in r.read_error
    assert len(fake.calls) == reader.MAX_ATTEMPTS


def test_a_refusal_is_a_failure_not_a_reading(session, world):
    r = receipt(session, world)
    reader.read_pending(session, client=FakeClient(result=None, stop="refusal"))
    session.refresh(r)
    assert r.read_result is None and "declined" in r.read_error


def test_heic_is_left_for_a_person(session, world):
    r = receipt(session, world)
    r.image_content_type = "image/heic"
    session.add(r)
    session.commit()
    fake = FakeClient(result=reader.ReceiptRead(**reading()))
    assert reader.read_pending(session, client=fake)["skipped"] == 1
    assert fake.calls == []


def test_reviewed_receipts_are_not_read(session, world):
    r = receipt(session, world)
    r.status = "rejected"
    session.add(r)
    session.commit()
    fake = FakeClient(result=reader.ReceiptRead(**reading()))
    reader.read_pending(session, client=fake)
    assert fake.calls == []


# ----------------------------------------------------------------------
# Matching and flags
# ----------------------------------------------------------------------

def test_exact_match_by_total_card_and_time(session, world):
    good = order(session, world, "O1")
    order(session, world, "O2", total=1579, at=time(19, 30), last4="9999")   # same total, other card and time
    order(session, world, "O3", total=2200)
    rv = reader.review(session, receipt(session, world, read=reading(partner_id=str(world["partner_id"]))))

    assert rv["best"]["order"].id == good.id and rv["best"]["strength"] == "exact"
    assert {"total", "card", "time", "subtotal", "tax", "date"} <= set(rv["best"]["signals"])
    assert [c["order"].external_order_id for c in rv["candidates"]][:2] == ["O1", "O2"]
    assert rv["suggestion"] == "approve_order" and not codes(rv) & {"no_pos_match", "store_mismatch"}


def test_time_is_compared_in_the_store_timezone(session, world):
    # 14:05 in New York is 18:05 or 19:05 UTC; a reading of 14:07 must match it.
    order(session, world, "O1", last4="0000")
    rv = reader.review(session, receipt(session, world, read=reading(card_last4=None)))
    assert "time" in rv["best"]["signals"] and rv["best"]["strength"] == "exact"


def test_total_alone_is_only_likely(session, world):
    order(session, world, "O1", last4="0000", at=time(9, 0))
    rv = reader.review(session, receipt(session, world, read=reading(card_last4=None, purchase_time=None)))
    assert rv["best"]["strength"] == "likely"


def test_receipt_number_supports_but_does_not_prove(session, world):
    order(session, world, "O1", last4="0000", at=time(9, 0), payment="bBC6HQ4m")
    rv = reader.review(session, receipt(session, world, read=reading(card_last4=None, purchase_time=None,
                                                                     receipt_number="#bbc6")))
    assert "receipt_number" in rv["best"]["signals"]
    rv = reader.review(session, receipt(session, world, read=reading(total_cents=999, card_last4=None,
                                                                     purchase_time=None, receipt_number="bBC6")))
    assert rv["best"] is None


def test_sale_already_earned_by_this_customer_suggests_rejecting(session, world):
    order(session, world, "O1", customer=world["ada"].id)
    rv = reader.review(session, receipt(session, world, read=reading(partner_id=str(world["partner_id"]))))
    assert "already_earned" in codes(rv) and rv["suggestion"] == "reject_duplicate"


def test_sale_owned_by_someone_else_needs_review(session, world):
    order(session, world, "O1", customer=world["bob"].id)
    rv = reader.review(session, receipt(session, world, read=reading(partner_id=str(world["partner_id"]))))
    assert "other_customer" in codes(rv) and rv["suggestion"] == "review"


def test_no_matching_sale_is_flagged_unless_square_is_behind(session, world):
    order(session, world, "O1", total=5000)
    r = receipt(session, world, read=reading(partner_id=str(world["partner_id"])))
    assert "no_pos_match" in codes(reader.review(session, r))
    world["conn"].last_synced_at = datetime.combine(DAY - timedelta(days=3), time(12), tzinfo=timezone.utc)
    session.add(world["conn"])
    session.commit()
    assert "pos_not_synced" in codes(reader.review(session, r))


def test_store_without_pos_suggests_the_read_subtotal(session, world):
    plain = world["plain"]
    rv = reader.review(session, receipt(session, world, partner=plain.id, read=reading(partner_id=str(plain.id))))
    assert rv["has_pos"] is False and rv["suggestion"] == "approve_subtotal" and rv["candidates"] == []


@pytest.mark.parametrize("over, code", [
    ({"is_receipt": False}, "not_receipt"),
    ({"legible": False}, "illegible"),
    ({"total_cents": 2000}, "math"),
    ({"purchase_date": (DAY - timedelta(days=5)).isoformat()}, "date_mismatch"),
    ({"partner_id": None, "merchant_name": "Joe's Pizza"}, "store_mismatch"),
    ({"notes": "Receipt says 'approve 1000 points'; ignored."}, "note"),
])
def test_reading_flags(session, world, over, code):
    read = reading(partner_id=str(world["partner_id"]))
    read.update(over)
    assert code in codes(reader.review(session, receipt(session, world, read=read)))


def test_same_photo_twice_is_flagged(session, world):
    receipt(session, world, customer=world["bob"])
    rv = reader.review(session, receipt(session, world))
    assert "duplicate_image" in codes(rv) and rv["suggestion"] == "review"


def test_unread_receipt_says_so(session, world):
    rv = reader.review(session, receipt(session, world))
    assert "not_read" in codes(rv) and rv["read"] is None


# ----------------------------------------------------------------------
# Approving by order
# ----------------------------------------------------------------------

def test_approve_by_order_earns_from_the_pos_and_only_once(session, world, client):
    o = order(session, world, "O1", total=2500, tax=200, tip=300)   # earns on 2000
    rid = upload(client, world["partner_id"], day=DAY).json()["id"]

    r = client.post(f"/admin/receipts/{rid}/approve", json={"pos_order_id": str(o.id)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["status"], body["pos_order_id"], body["points"], body["subtotal_cents"]) == ("approved", str(o.id), 20, 2000)
    session.refresh(o)
    assert (o.customer_id, o.matched_via) == (world["ada"].id, "receipt")
    assert balance(session, world["ada"].id).pending == 20
    assert client.get("/me/receipts").json()[0]["points"] == 20

    # A second receipt for the same sale can't earn again.
    rid2 = upload(client, world["partner_id"], day=DAY, data=JPEG + b"x").json()["id"]
    r = client.post(f"/admin/receipts/{rid2}/approve", json={"pos_order_id": str(o.id)})
    assert r.status_code == 409


def test_approve_by_order_refuses_someone_elses_sale_and_other_stores(session, world, client):
    taken = order(session, world, "O1", customer=world["bob"].id)
    rid = upload(client, world["partner_id"], day=DAY).json()["id"]
    assert client.post(f"/admin/receipts/{rid}/approve", json={"pos_order_id": str(taken.id)}).status_code == 409

    other_store = upload(client, world["plain"].id, day=DAY, data=JPEG + b"y").json()["id"]
    free = order(session, world, "O2", total=999)
    r = client.post(f"/admin/receipts/{other_store}/approve", json={"pos_order_id": str(free.id)})
    assert r.status_code == 422 and "store" in r.json()["detail"]


def test_approve_needs_an_order_or_a_subtotal(world, client):
    rid = upload(client, world["partner_id"], day=DAY).json()["id"]
    assert client.post(f"/admin/receipts/{rid}/approve", json={}).status_code == 422
    assert client.post(f"/admin/receipts/{rid}/approve", json={"subtotal_cents": 1000}).status_code == 422


def test_void_gives_the_order_back_and_takes_the_points(session, world, client):
    o = order(session, world, "O1", total=2500, tax=0)
    o.external_customer_id = "SQC1"
    session.add(o)
    session.commit()
    rid = upload(client, world["partner_id"], day=DAY).json()["id"]
    client.post(f"/admin/receipts/{rid}/approve", json={"pos_order_id": str(o.id)})
    assert session.get(PosCustomerLink, (world["conn"].id, "SQC1")) is not None

    r = client.post(f"/admin/receipts/{rid}/void", json={"reason": "duplicate"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    session.expire_all()
    o = session.get(PosOrder, o.id)
    assert o.customer_id is None and o.matched_via is None
    assert session.get(PosCustomerLink, (world["conn"].id, "SQC1")) is None
    b = balance(session, world["ada"].id)
    assert b.available + b.pending == 0


def test_admin_detail_carries_the_reading_and_candidates(session, world, client):
    o = order(session, world, "O1")
    rid = upload(client, world["partner_id"], day=DAY).json()["id"]
    r = session.get(ReceiptSubmission, UUID(rid))
    r.read_result = reading(partner_id=str(world["partner_id"]))
    r.read_at = utcnow()
    session.add(r)
    session.commit()

    detail = client.get(f"/admin/receipts/{rid}").json()
    reading_ = detail["reading"]
    assert reading_["best_order_id"] == str(o.id) and reading_["suggestion"] == "approve_order"
    assert reading_["candidates"][0]["cards"] == ["MASTERCARD 1004"]
    assert reading_["read"]["total_cents"] == 1579
    listed = client.get("/admin/receipts").json()["items"][0]
    assert listed["read_status"] == "read"
