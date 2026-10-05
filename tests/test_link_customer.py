"""/me/link-customer: which customer row a login is joined to.

The join is an identity decision -- it hands the caller that customer's
purchases, orders and points -- so it must rest only on what the token proves.
"""
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import Customer
from routes.admin.auth import require_admin
from routes.admin.customers import router as admin_customers_router
from routes_me import router as me_router


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for row in session.exec(select(Customer)).all():
            session.delete(row)
        session.commit()
    yield


def _client(uid=None, phone=None, email=None, meta=None):
    app = FastAPI()
    app.include_router(me_router)
    app.include_router(admin_customers_router, prefix="/admin")
    claims = {"user_metadata": meta} if meta is not None else {}
    app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
        user_id=str(uid or uuid4()), email=email, phone=phone,
        role="authenticated", raw_claims=claims,
    )
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
        user_id="admin", email=None, phone=None, role="admin", raw_claims={},
    )
    return TestClient(app)


def _add(**fields) -> Customer:
    with Session(engine) as session:
        c = Customer(**fields)
        session.add(c)
        session.commit()
        session.refresh(c)
        return c


def _get(customer_id) -> Customer:
    with Session(engine) as session:
        return session.get(Customer, UUID(str(customer_id)))


def _get_all_linked():
    with Session(engine) as session:
        return list(session.exec(select(Customer).where(Customer.auth_user_id.is_not(None))).all())


def test_request_body_phone_cannot_claim_someone_elses_customer():
    victim = _add(name="Victim", phone="+15550001111")
    resp = _client(phone="15559998888").post(
        "/me/link-customer", json={"phone": "+15550001111", "email": "x@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["created"] is True
    assert resp.json()["customer_id"] != str(victim.id)
    assert _get(victim.id).auth_user_id is None


def test_request_body_identity_alone_is_not_enough():
    _add(name="Victim", phone="+15550001111")
    resp = _client().post("/me/link-customer", json={"phone": "+15550001111"})
    assert resp.status_code == 400
    assert _get_all_linked() == []


def test_sms_login_claims_its_own_customer_and_stores_e164():
    uid = uuid4()
    existing = _add(name="Ada", phone="15552010001")  # legacy spelling, no "+"
    resp = _client(uid=uid, phone="15552010001").post("/me/link-customer", json={})
    assert resp.json() == {"customer_id": str(existing.id), "linked": True, "created": False}
    row = _get(existing.id)
    assert row.auth_user_id == uid
    assert row.phone == "+15552010001"


def test_new_customer_gets_e164_and_no_synthetic_email():
    resp = _client(phone="15552010001", email="15552010001@phone.invalid").post(
        "/me/link-customer", json={"name": "Ada"},
    )
    row = _get(resp.json()["customer_id"])
    assert row.phone == "+15552010001"
    assert row.email is None
    assert row.name == "Ada"


def test_verified_email_matches_but_unverified_does_not():
    by_email = _add(name="Grace", email="grace@example.com")

    resp = _client(email="grace@example.com", meta={"email_verified": False}).post("/me/link-customer", json={})
    assert resp.status_code == 400
    assert _get(by_email.id).auth_user_id is None

    resp = _client(email="grace@example.com", meta={"email_verified": True}).post("/me/link-customer", json={})
    assert resp.json()["customer_id"] == str(by_email.id)


def test_email_match_keeps_a_different_phone_on_file():
    c = _add(email="grace@example.com", phone="+15550002222")
    _client(phone="15550003333", email="grace@example.com", meta={"email_verified": True}).post(
        "/me/link-customer", json={},
    )
    assert _get(c.id).phone == "+15550002222"


def test_customer_linked_to_another_login_is_refused():
    _add(phone="+15550001111", auth_user_id=uuid4())
    resp = _client(phone="15550001111").post("/me/link-customer", json={})
    assert resp.status_code == 409


def test_admin_customer_phone_is_stored_e164():
    client = _client()
    created = client.post("/admin/customers", json={"name": "Lin", "phone": "(555) 201-0003"}).json()
    assert created["phone"] == "+15552010003"

    updated = client.post(f"/admin/customers/{created['id']}", json={"phone": "555.201.0004"})
    assert updated.json()["phone"] == "+15552010004"


def test_admin_rejects_unparseable_phone():
    resp = _client().post("/admin/customers", json={"phone": "12345"})
    assert resp.status_code == 422


def test_verified_email_alone_cannot_start_a_new_customer():
    resp = _client(email="new@example.com", meta={"email_verified": True}).post("/me/link-customer", json={})
    assert resp.status_code == 400
    assert _get_all_linked() == []
