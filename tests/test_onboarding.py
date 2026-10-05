"""Sign-up: POST /me/onboarding and what GET /me reports as missing.

Consent records are the point of this feature, so the tests check the
consent_events trail, not just the columns on the customer.
"""
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import ConsentEvent, Customer
from routes.admin.auth import require_admin
from routes.admin.customers import router as admin_customers_router
from routes_me import router as me_router
from services import consent

AUTH_UID = uuid4()


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (ConsentEvent, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


@pytest.fixture
def customer_id():
    with Session(engine) as session:
        c = Customer(name="Ada Lovelace", phone="+15552010001", auth_user_id=AUTH_UID)
        session.add(c)
        session.commit()
        return c.id


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(me_router)
    app.include_router(admin_customers_router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
        user_id=str(AUTH_UID), email=None, phone="15552010001",
        role="authenticated", raw_claims={},
    )
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
        user_id="admin", email=None, phone=None, role="admin", raw_claims={},
    )
    return TestClient(app)


def _body(**overrides):
    body = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "age_21": True,
        "terms_version": consent.TERMS_VERSION,
        "marketing_sms_opt_in": False,
        "platform": "ios",
    }
    body.update(overrides)
    return body


def _events(customer_id):
    with Session(engine) as session:
        return list(session.exec(
            select(ConsentEvent).where(ConsentEvent.customer_id == customer_id)
            .order_by(ConsentEvent.created_at)
        ).all())


def test_new_customer_reports_everything_missing_with_disclosures(client, customer_id):
    me = client.get("/me").json()
    ob = me["onboarding"]
    assert ob["complete"] is False
    assert ob["missing"] == ["first_name", "age_21", "terms"]
    assert ob["prefill"]["first_name"] == "Ada"  # from the legacy display name
    assert ob["disclosures"]["marketing_sms"]["text"] == consent.MARKETING_SMS_TEXT
    assert ob["disclosures"]["terms"]["version"] == consent.TERMS_VERSION


def test_onboarding_completes_and_records_consent(client, customer_id):
    res = client.post("/me/onboarding", json=_body(
        marketing_sms_opt_in=True, marketing_sms_version=consent.MARKETING_SMS_VERSION,
    ), headers={"user-agent": "TerpTest/1.0", "x-forwarded-for": "203.0.113.9"})
    assert res.status_code == 200
    me = res.json()
    assert me["onboarding"]["complete"] is True
    assert me["onboarding"]["missing"] == []
    assert me["first_name"] == "Ada" and me["name"] == "Ada Lovelace"
    assert me["marketing_opt_in"] is True

    events = {e.kind: e for e in _events(customer_id)}
    assert set(events) == {"age_21", "terms", "marketing_sms"}
    sms = events["marketing_sms"]
    assert sms.granted and sms.text == consent.MARKETING_SMS_TEXT
    assert sms.version == consent.MARKETING_SMS_VERSION
    assert sms.phone == "+15552010001"
    assert sms.source == "onboarding:ios"
    assert sms.ip == "203.0.113.9" and sms.user_agent == "TerpTest/1.0"

    with Session(engine) as session:
        assert session.get(Customer, customer_id).onboarded_at is not None


def test_marketing_is_off_unless_asked_for(client, customer_id):
    client.post("/me/onboarding", json=_body())
    assert client.get("/me").json()["marketing_opt_in"] is False
    assert "marketing_sms" not in {e.kind for e in _events(customer_id)}


@pytest.mark.parametrize("override,status", [
    ({"first_name": "   "}, 422),
    ({"age_21": False}, 422),
    ({"terms_version": "2001-01-01"}, 409),
    ({"marketing_sms_opt_in": True}, 409),                                   # no version echoed
    ({"marketing_sms_opt_in": True, "marketing_sms_version": "old"}, 409),
])
def test_refusals_record_nothing(client, customer_id, override, status):
    res = client.post("/me/onboarding", json=_body(**override))
    assert res.status_code == status
    assert _events(customer_id) == []
    assert client.get("/me").json()["onboarding"]["complete"] is False


def test_resubmitting_writes_no_duplicate_events(client, customer_id):
    client.post("/me/onboarding", json=_body())
    client.post("/me/onboarding", json=_body(first_name="Augusta"))
    assert sorted(e.kind for e in _events(customer_id)) == ["age_21", "terms"]
    assert client.get("/me").json()["first_name"] == "Augusta"


def test_a_terms_change_sends_people_back(client, customer_id, monkeypatch):
    client.post("/me/onboarding", json=_body())
    monkeypatch.setattr(consent, "TERMS_VERSION", "2027-01-01")
    ob = client.get("/me").json()["onboarding"]
    assert ob["missing"] == ["terms"]

    client.post("/me/onboarding", json=_body(terms_version="2027-01-01"))
    terms = [e for e in _events(customer_id) if e.kind == "terms"]
    assert len(terms) == 2 and terms[1].version == "2027-01-01"
    assert terms[0].version != "2027-01-01"
    with Session(engine) as session:
        assert session.get(Customer, customer_id).terms_version == "2027-01-01"


def test_profile_opt_out_is_recorded_and_needs_no_version(client, customer_id):
    client.post("/me/onboarding", json=_body(
        marketing_sms_opt_in=True, marketing_sms_version=consent.MARKETING_SMS_VERSION,
    ))
    res = client.post("/me", json={"marketing_opt_in": False, "platform": "web"})
    assert res.json()["marketing_opt_in"] is False
    last = [e for e in _events(customer_id) if e.kind == "marketing_sms"][-1]
    assert last.granted is False and last.source == "profile:web"


def test_profile_first_name_edit_recomposes_display_name(client, customer_id):
    client.post("/me/onboarding", json=_body())
    me = client.post("/me", json={"first_name": "Augusta"}).json()
    assert me["name"] == "Augusta Lovelace"
    assert client.post("/me", json={"first_name": " "}).status_code == 422


def test_link_customer_cannot_opt_anyone_in(client):
    res = client.post("/me/link-customer", json={"marketing_opt_in": True})
    assert res.status_code == 200
    assert client.get("/me").json()["marketing_opt_in"] is False


def test_admin_opt_in_is_recorded_without_claimed_wording(client, customer_id):
    client.post(f"/admin/customers/{customer_id}", json={"marketing_opt_in": True})
    [event] = _events(customer_id)
    assert event.kind == "marketing_sms" and event.granted
    assert event.source == "admin" and event.text is None and event.version is None
