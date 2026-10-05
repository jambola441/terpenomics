"""DELETE /me: the login goes, nothing left identifies the person, records add up."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import (
    ConsentEvent, Customer, Dispensary, Order, OrderStatus, Partner, PhoneAuthChallenge,
    PhoneAuthIdentity, PointsEntry, PosConnection, PosCustomerLink, PosOrder, PreferredDispensary,
    Purchase, ReceiptSubmission,
)
from routes_me import router as me_router
from services import supabase_admin

AUTH_UID = uuid4()
PHONE = "+15552010001"
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (ConsentEvent, ReceiptSubmission, PointsEntry, PosCustomerLink, PosOrder, PosConnection,
                      Partner, PreferredDispensary, Order, Purchase, PhoneAuthChallenge, PhoneAuthIdentity,
                      Customer, Dispensary):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


@pytest.fixture
def deleted_users(monkeypatch):
    calls = []
    monkeypatch.setattr(supabase_admin, "delete_user", calls.append)
    return calls


@pytest.fixture
def world():
    with Session(engine) as s:
        c = Customer(name="Ada Lovelace", first_name="Ada", last_name="Lovelace", phone=PHONE,
                     email="ada@example.com", auth_user_id=AUTH_UID, marketing_opt_in=True)
        shop = Dispensary(name="Shop", slug="shop", accepts_pickup=True)
        partner = Partner(name="Bean Co", slug="bean-co")
        s.add_all([c, shop, partner])
        s.flush()
        conn = PosConnection(partner_id=partner.id, provider="square", external_merchant_id="M1")
        s.add(conn)
        s.flush()
        s.add_all([
            Order(customer_id=c.id, dispensary_id=shop.id, pickup_code="AB12", status=OrderStatus.submitted),
            Order(customer_id=c.id, dispensary_id=shop.id, pickup_code="CD34", status=OrderStatus.completed),
            Purchase(customer_id=c.id, total_amount_cents=4500),
            PreferredDispensary(customer_id=c.id, dispensary_id=shop.id),
            PosCustomerLink(connection_id=conn.id, external_customer_id="SQ-1", customer_id=c.id, linked_via="phone"),
            PosOrder(connection_id=conn.id, partner_id=partner.id, external_order_id="O1", state="COMPLETED", ordered_at=NOW, external_updated_at=NOW,
                     customer_id=c.id, customer_phone=PHONE, customer_email="ada@example.com",
                     external_customer_id="SQ-1"),
            PointsEntry(customer_id=c.id, partner_id=partner.id, kind="earn", points=12, available_at=NOW),
            ReceiptSubmission(customer_id=c.id, partner_id=partner.id, image=b"jpeg", customer_note="latte"),
            PhoneAuthIdentity(phone=PHONE, auth_user_id=AUTH_UID),
            PhoneAuthChallenge(phone=PHONE, provider="verifynow", provider_ref="r1", expires_at=NOW),
        ])
        s.commit()
        return c.id


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(me_router)
    app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
        user_id=str(AUTH_UID), email=None, phone=PHONE.lstrip("+"), role="authenticated", raw_claims={},
    )
    return TestClient(app)


def test_delete_scrubs_identity_and_keeps_records(client, world, deleted_users):
    assert client.delete("/me").status_code == 204
    assert deleted_users == [AUTH_UID]

    with Session(engine) as s:
        c = s.get(Customer, world)
        assert c.deleted_at is not None
        assert (c.name, c.first_name, c.last_name, c.phone, c.email, c.auth_user_id) == (None,) * 6
        assert c.marketing_opt_in is False

        statuses = sorted(o.status for o in s.exec(select(Order)).all())
        assert statuses == sorted([OrderStatus.cancelled, OrderStatus.completed])
        assert len(s.exec(select(Purchase)).all()) == 1
        assert len(s.exec(select(PointsEntry)).all()) == 1

        receipt = s.exec(select(ReceiptSubmission)).one()
        assert receipt.image is None and receipt.customer_note is None and receipt.status == "rejected"
        pos = s.exec(select(PosOrder)).one()
        assert (pos.customer_phone, pos.customer_email, pos.external_customer_id) == (None, None, None)
        assert pos.contact_purged_at is not None

        for model in (PosCustomerLink, PreferredDispensary, PhoneAuthIdentity, PhoneAuthChallenge):
            assert s.exec(select(model)).all() == []

        [withdrawal] = s.exec(select(ConsentEvent)).all()
        assert withdrawal.kind == "marketing_sms" and withdrawal.granted is False
        assert withdrawal.source == "account_deleted" and withdrawal.phone == PHONE


def test_after_deletion_the_login_finds_no_customer(client, world, deleted_users):
    client.delete("/me")
    assert client.get("/me").status_code == 404


def test_supabase_failure_changes_nothing(client, world, monkeypatch):
    def boom(_uid):
        raise supabase_admin.SupabaseAdminError("down")
    monkeypatch.setattr(supabase_admin, "delete_user", boom)

    assert client.delete("/me").status_code == 502
    with Session(engine) as s:
        c = s.get(Customer, world)
        assert c.phone == PHONE and c.deleted_at is None
    assert client.get("/me").status_code == 200
