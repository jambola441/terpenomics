"""The partner portal (/partner/*) and admin partner-login management.

The properties worth a test each are the access rules: an invite is honoured only
for the verified email it names, it binds to the first Supabase user to claim it,
one partner's login never reaches another partner's data, and partners never see
who their Terpee shoppers are.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from connectors.oauth_state import read_state
from connectors.store import upsert_orders
from database import engine
from models import Customer, Partner, PartnerMember, PosConnection
from routes.admin.auth import require_admin
from routes.admin.partners import router as admin_partners_router
from routes.partner import router as partner_router
from routes.pos_common import connector_factory
from routes.pos_oauth import router as pos_oauth_router
from tests.test_pos_connectors import TABLES as POS_TABLES, FakeConnector, make_connection, norm

TABLES = POS_TABLES + [PartnerMember.__table__]

ALICE_ID = str(uuid4())


def user(user_id=ALICE_ID, email="alice@beanco.com", **meta):
    return SupabaseAuthUser(
        user_id=user_id, email=email, phone=None, role="authenticated",
        raw_claims={"user_metadata": meta},
    )


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.drop_all(engine, tables=list(reversed(TABLES)))
    SQLModel.metadata.create_all(engine, tables=TABLES)
    yield


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


@pytest.fixture
def client():
    fake = FakeConnector()
    app = FastAPI()
    app.include_router(admin_partners_router, prefix="/admin")
    app.include_router(partner_router)
    app.include_router(pos_oauth_router)
    current = {"user": user()}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[require_admin] = lambda: user(role="admin")
    app.dependency_overrides[connector_factory] = lambda: (lambda provider: fake)
    c = TestClient(app)
    c.fake = fake
    c.current = current
    return c


@pytest.fixture
def bean(session):
    """Bean Co with a live Square connection, and Alice invited to it."""
    conn = make_connection(session)
    session.add(PartnerMember(partner_id=conn.partner_id, email="alice@beanco.com"))
    session.commit()
    return conn


def other_partner(session):
    p = Partner(name="Other", slug="other")
    session.add(p)
    session.flush()
    c = PosConnection(partner_id=p.id, provider="square", external_merchant_id="M2", credentials="x")
    session.add(c)
    session.commit()
    return p, c


# ----------------------------------------------------------------------
# Who gets in
# ----------------------------------------------------------------------

def test_stranger_sees_no_partners(client, bean):
    client.current["user"] = user(user_id=str(uuid4()), email="mallory@example.com")
    assert client.get("/partner/me").json()["partners"] == []
    assert client.get(f"/partner/partners/{bean.partner_id}").status_code == 404


def test_invite_binds_to_first_sign_in_and_survives_an_email_change(client, bean, session):
    me = client.get("/partner/me").json()
    assert [p["id"] for p in me["partners"]] == [str(bean.partner_id)]
    member = session.exec(select(PartnerMember)).one()
    assert member.auth_user_id == UUID(ALICE_ID) and member.last_login_at is not None

    # Alice changes her Google address: the bound user id still gets her in.
    client.current["user"] = user(email="alice@new.com")
    assert client.get(f"/partner/partners/{bean.partner_id}").status_code == 200

    # Someone else who now holds alice@beanco.com does not.
    client.current["user"] = user(user_id=str(uuid4()))
    assert client.get(f"/partner/partners/{bean.partner_id}").status_code == 404


def test_email_matching_is_case_insensitive(client, bean):
    client.current["user"] = user(email="Alice@BeanCo.com")
    assert len(client.get("/partner/me").json()["partners"]) == 1


@pytest.mark.parametrize("claims", [
    {"email": "16465550101@phone.invalid"},                 # SMS-login placeholder
    {"email": "alice@beanco.com", "email_verified": False},  # unverified address
])
def test_placeholder_and_unverified_emails_never_match(client, session, claims):
    p = Partner(name="Bean", slug="bean")
    session.add(p)
    session.flush()
    session.add(PartnerMember(partner_id=p.id, email=claims["email"].lower()))
    session.commit()
    email = claims.pop("email")
    client.current["user"] = user(email=email, **claims)
    assert client.get("/partner/me").json()["partners"] == []


def test_one_partners_login_cannot_reach_another_partner(client, bean, session):
    other, other_conn = other_partner(session)
    assert client.get(f"/partner/partners/{other.id}").status_code == 404
    assert client.get(f"/partner/partners/{other.id}/orders").status_code == 404
    # Another partner's connection id through Alice's own partner path.
    path = f"/partner/partners/{bean.partner_id}/connections/{other_conn.id}"
    assert client.patch(path, json={"status": "disabled"}).status_code == 404
    assert client.delete(path).status_code == 404
    assert client.get(f"{path}/runs").status_code == 404
    session.refresh(other_conn)
    assert other_conn.status == "active"


# ----------------------------------------------------------------------
# What partners can do
# ----------------------------------------------------------------------

def test_partner_connects_and_lands_back_on_partner(client, session, monkeypatch):
    monkeypatch.setenv("POS_OAUTH_RETURN_URL", "https://admin.example/admin/partners")
    monkeypatch.delenv("POS_PARTNER_RETURN_URL", raising=False)
    p = Partner(name="Bean", slug="bean")
    session.add(p)
    session.flush()
    session.add(PartnerMember(partner_id=p.id, email="alice@beanco.com"))
    session.commit()

    url = client.get(f"/partner/partners/{p.id}/oauth/square/start").json()["authorize_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert read_state(state, "square") == (p.id, "partner")

    r = client.get("/pos/oauth/square/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://admin.example/partner?pos=connected")

    # A partner who clicks "deny" also goes back to /partner, not to admin.
    r = client.get("/pos/oauth/square/callback", params={"state": state, "error": "access_denied"},
                   follow_redirects=False)
    assert r.headers["location"].startswith("https://admin.example/partner?pos=error")


def test_admin_connect_still_returns_to_admin(client, session, monkeypatch):
    monkeypatch.setenv("POS_OAUTH_RETURN_URL", "https://admin.example/admin/partners")
    pid = client.post("/admin/partners", json={"name": "A", "slug": "a"}).json()["id"]
    url = client.get("/admin/pos-connections/oauth/square/start", params={"partner_id": pid}).json()["authorize_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    r = client.get("/pos/oauth/square/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert r.headers["location"].startswith("https://admin.example/admin/partners?pos=connected")


def test_partner_pauses_resumes_and_disconnects(client, bean):
    path = f"/partner/partners/{bean.partner_id}/connections/{bean.id}"
    assert client.patch(path, json={"status": "disabled"}).json()["status"] == "disabled"
    assert client.patch(path, json={"status": "active"}).json()["status"] == "active"
    gone = client.delete(path).json()
    assert gone["status"] == "revoked" and not gone["has_credentials"]
    assert len(client.fake.revoked) == 1
    assert client.patch(path, json={"status": "active"}).status_code == 409


def test_partner_sees_member_flag_never_member_identity(client, bean, session):
    session.add(Customer(name="Ada", phone="+16465550101"))
    session.commit()
    rows, _, _ = upsert_orders(session, bean, [norm("O1", phone="+16465550101"), norm("O2")], {})
    from connectors.matching import match_orders
    match_orders(session, rows)
    session.commit()

    body = client.get(f"/partner/partners/{bean.partner_id}/orders").json()
    assert body["total"] == 2
    flags = {o["external_order_id"]: o["is_member"] for o in body["items"]}
    assert flags == {"O1": True, "O2": False}
    for o in body["items"]:
        assert not {"customer_id", "matched_via", "has_contact", "contact_purged_at"} & set(o)
    assert "+16465550101" not in r_text(client, bean) and "Ada" not in r_text(client, bean)

    members_only = client.get(f"/partner/partners/{bean.partner_id}/orders", params={"members_only": True}).json()
    assert [o["external_order_id"] for o in members_only["items"]] == ["O1"]


def r_text(client, bean):
    return client.get(f"/partner/partners/{bean.partner_id}/orders").text


def test_partner_detail_has_no_logins_or_credentials(client, bean):
    body = client.get(f"/partner/partners/{bean.partner_id}").json()
    assert "members" not in body
    assert "credentials" not in body["connections"][0]


# ----------------------------------------------------------------------
# Admin: managing partner logins
# ----------------------------------------------------------------------

def test_admin_invites_and_removes_logins(client, session):
    pid = client.post("/admin/partners", json={"name": "A", "slug": "a"}).json()["id"]
    r = client.post(f"/admin/partners/{pid}/members", json={"email": " Owner@Shop.COM "})
    assert r.status_code == 201 and r.json()["email"] == "owner@shop.com" and not r.json()["signed_in"]
    assert client.post(f"/admin/partners/{pid}/members", json={"email": "owner@shop.com"}).status_code == 409
    assert client.post(f"/admin/partners/{pid}/members", json={"email": "not-an-email"}).status_code == 422
    assert client.post(f"/admin/partners/{pid}/members",
                       json={"email": "16465550101@phone.invalid"}).status_code == 422

    members = client.get(f"/admin/partners/{pid}").json()["members"]
    assert [m["email"] for m in members] == ["owner@shop.com"]

    # Once removed, the login stops working.
    client.current["user"] = user(email="owner@shop.com")
    assert client.get(f"/partner/partners/{pid}").status_code == 200
    assert client.delete(f"/admin/partner-members/{members[0]['id']}").json() == {"ok": True}
    assert client.get(f"/partner/partners/{pid}").status_code == 404
