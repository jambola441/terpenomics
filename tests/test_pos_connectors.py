"""Partner POS connectors: Square normalization and HTTP, storage, matching, sync, API.

No test reaches a real POS: Square is driven through httpx.MockTransport, and the
sync and API tests use FakeConnector.

Only the tables these tests need are created, because the full metadata includes
Postgres-only columns (brand_catalog_entries) that SQLite cannot build.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

os.environ["POS_CREDENTIALS_KEY"] = Fernet.generate_key().decode()

from auth import SupabaseAuthUser  # noqa: E402
from connectors import matching, sync  # noqa: E402
from connectors.base import AuthError, ConnectorError, ExternalLocation, NormalizedOrder, OAuthGrant  # noqa: E402
from connectors.crypto import CredentialsKeyError, decrypt_credentials, encrypt_credentials  # noqa: E402
from connectors.oauth_state import InvalidState, sign_state, verify_state  # noqa: E402
from connectors.square import SquareConnector  # noqa: E402
from connectors.store import as_utc, upsert_orders  # noqa: E402
from database import engine  # noqa: E402
from models import (  # noqa: E402
    Customer,
    Partner,
    PartnerLocation,
    PosConnection,
    PosCustomerLink,
    PosOrder,
    PosOrderItem,
    PosSyncRun,
)
from routes.admin.auth import require_admin  # noqa: E402
from routes.admin.partners import connector_factory, router as partners_router  # noqa: E402
from routes.pos_oauth import router as pos_oauth_router  # noqa: E402

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)

TABLES = [
    Customer.__table__, Partner.__table__, PosConnection.__table__, PartnerLocation.__table__,
    PosOrder.__table__, PosOrderItem.__table__, PosCustomerLink.__table__, PosSyncRun.__table__,
]


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.drop_all(engine, tables=list(reversed(TABLES)))
    SQLModel.metadata.create_all(engine, tables=TABLES)
    yield


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


# ----------------------------------------------------------------------
# Fakes and builders
# ----------------------------------------------------------------------

def norm(ext_id, *, updated=NOW, phone=None, cust=None, kind="sale", source=None,
         total=1000, state="completed", location="L1", ordered=None) -> NormalizedOrder:
    return NormalizedOrder(
        external_order_id=ext_id, state=state, kind=kind, source_external_order_id=source,
        ordered_at=ordered or updated, external_updated_at=updated, external_location_id=location,
        total_cents=total, customer_phone=phone, external_customer_id=cust,
        raw={"id": ext_id},
    )


class FakeConnector:
    provider = "square"

    def __init__(self, orders=None, merchant="M1", fail=None):
        self.orders = orders or []
        self.merchant = merchant
        self.fail = fail
        self.since_seen = []
        self.refreshed = 0
        self.revoked = []

    def authorize_url(self, state):
        return f"https://pos.example/authorize?state={state}"

    def exchange_code(self, code):
        if code == "bad":
            raise AuthError("bad code")
        return OAuthGrant(self.merchant, {"access_token": "at", "refresh_token": "rt"},
                          NOW + timedelta(days=30), "ORDERS_READ")

    def refresh(self, credentials):
        self.refreshed += 1
        return OAuthGrant(self.merchant, {"access_token": "at2", "refresh_token": "rt"}, NOW + timedelta(days=30))

    def revoke(self, credentials):
        self.revoked.append(credentials)

    def list_locations(self, credentials):
        return [ExternalLocation("L1", "Main St"), ExternalLocation("L2", "Pier", is_active=False)]

    def fetch_orders(self, credentials, location_ids, since):
        self.since_seen.append(since)
        for i, o in enumerate(self.orders):
            if self.fail is not None and i == self.fail:
                raise ConnectorError("boom")
            yield o


def make_connection(session, *, cursor=NOW - timedelta(days=1), expires=NOW + timedelta(days=30)):
    partner = Partner(name="Bean Co", slug="bean-co")
    session.add(partner)
    session.flush()
    conn = PosConnection(
        partner_id=partner.id, provider="square", external_merchant_id="M1",
        credentials=encrypt_credentials({"access_token": "at", "refresh_token": "rt"}),
        token_expires_at=expires, sync_cursor=cursor,
    )
    session.add(conn)
    session.commit()
    return conn


# ----------------------------------------------------------------------
# Square: normalization
# ----------------------------------------------------------------------

SALE = {
    "id": "O1", "location_id": "L1", "state": "COMPLETED", "customer_id": "C1",
    "created_at": "2026-10-01T15:00:00.000Z", "updated_at": "2026-10-01T15:05:00Z",
    "closed_at": "2026-10-01T15:05:00Z",
    "total_money": {"amount": 1250, "currency": "USD"},
    "total_tax_money": {"amount": 100, "currency": "USD"},
    "total_tip_money": {"amount": 150, "currency": "USD"},
    "total_discount_money": {"amount": 0, "currency": "USD"},
    "line_items": [
        {"uid": "li1", "name": "Latte", "variation_name": "Large", "quantity": "2",
         "catalog_object_id": "V1", "total_money": {"amount": 1000, "currency": "USD"}},
        {"uid": "li2", "quantity": "1", "total_money": {"amount": 100, "currency": "USD"}},
    ],
    "refunds": [
        {"id": "R1", "status": "APPROVED", "amount_money": {"amount": 300}},
        {"id": "R2", "status": "REJECTED", "amount_money": {"amount": 999}},
    ],
}


def test_normalize_sale():
    o = SquareConnector.normalize(SALE, {"C1": {"phone_number": "(646) 555-0101", "email_address": " A@B.com "}})
    assert (o.kind, o.state, o.total_cents, o.tax_cents, o.tip_cents) == ("sale", "completed", 1250, 100, 150)
    assert o.refunded_cents == 300  # rejected refunds do not count
    assert o.customer_phone == "+16465550101"
    assert o.customer_email == "a@b.com"
    assert o.ordered_at == datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
    assert [line.name for line in o.lines] == ["Latte", "Custom amount"]
    assert o.lines[0].quantity == "2" and o.lines[0].external_sku == "V1"


def test_normalize_return_order_points_at_its_sale():
    ret = {
        "id": "O2", "location_id": "L1", "state": "COMPLETED",
        "created_at": "2026-10-02T10:00:00Z", "updated_at": "2026-10-02T10:00:00Z",
        "returns": [{"source_order_id": "O1", "return_line_items": [
            {"uid": "r1", "name": "Latte", "quantity": "1", "total_money": {"amount": 500}}]}],
        "return_amounts": {"total_money": {"amount": 500, "currency": "USD"}},
    }
    o = SquareConnector.normalize(ret)
    assert (o.kind, o.source_external_order_id, o.total_cents) == ("return", "O1", 500)
    assert o.lines[0].name == "Latte"


def test_tender_customer_used_when_order_has_none():
    order = {**SALE, "customer_id": None, "tenders": [{"customer_id": "C9"}]}
    assert SquareConnector.normalize(order).external_customer_id == "C9"


# ----------------------------------------------------------------------
# Square: HTTP
# ----------------------------------------------------------------------

def square(handler, environment="production"):
    return SquareConnector("app-id", "app-secret", environment=environment,
                           transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_authorize_url():
    url = square(lambda r: httpx.Response(200)).authorize_url("ST")
    assert url.startswith("https://connect.squareup.com/oauth2/authorize?")
    assert "state=ST" in url and "session=false" in url and "ORDERS_READ" in url
    sandbox = square(lambda r: httpx.Response(200), "sandbox").authorize_url("ST")
    assert sandbox.startswith("https://connect.squareupsandbox.com/") and "session" not in sandbox


def test_exchange_code_and_refresh_keep_refresh_token():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/oauth2/token"
        assert body["client_secret"] == "app-secret"
        if body["grant_type"] == "authorization_code":
            return httpx.Response(200, json={"access_token": "A1", "refresh_token": "R1",
                                             "merchant_id": "M1", "expires_at": "2026-11-03T12:00:00Z"})
        return httpx.Response(200, json={"access_token": "A2", "expires_at": "2026-12-03T12:00:00Z"})

    sq = square(handler)
    grant = sq.exchange_code("code")
    assert grant.merchant_id == "M1" and grant.credentials["refresh_token"] == "R1"
    assert grant.expires_at == datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    again = sq.refresh(grant.credentials)
    assert again.credentials == {"access_token": "A2", "refresh_token": "R1", "merchant_id": "M1"}


def test_bad_code_is_an_auth_error():
    sq = square(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(AuthError):
        sq.exchange_code("used")


def test_fetch_orders_pages_and_looks_up_customers():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        body = json.loads(request.content) if request.content else {}
        assert request.headers["Authorization"] == "Bearer AT"
        assert request.headers["Square-Version"]
        if request.url.path == "/v2/orders/search":
            assert body["query"]["sort"] == {"sort_field": "UPDATED_AT", "sort_order": "ASC"}
            assert body["query"]["filter"]["date_time_filter"]["updated_at"]["start_at"] == "2026-10-01T00:00:00.000000Z"
            if "cursor" not in body:
                return httpx.Response(200, json={"orders": [SALE, {**SALE, "id": "D", "state": "DRAFT"}],
                                                 "cursor": "next"})
            return httpx.Response(200, json={"orders": [{**SALE, "id": "O3", "customer_id": "C2"}]})
        if request.url.path == "/v2/customers/bulk-retrieve":
            ids = body["customer_ids"]
            return httpx.Response(200, json={"responses": {
                cid: ({"customer": {"phone_number": "+16465550101"}} if cid == "C1" else {"errors": [{}]})
                for cid in ids}})
        raise AssertionError(request.url.path)

    orders = list(square(handler).fetch_orders({"access_token": "AT"}, ["L1"],
                                                datetime(2026, 10, 1, tzinfo=timezone.utc)))
    assert [o.external_order_id for o in orders] == ["O1", "O3"]  # draft dropped
    assert orders[0].customer_phone == "+16465550101"
    assert orders[1].customer_phone is None  # profile lookup failed, order still arrives
    assert calls.count("/v2/customers/bulk-retrieve") == 2  # once per page, only for new ids


def test_location_ids_are_chunked_by_ten():
    seen = []

    def handler(request):
        seen.append(len(json.loads(request.content)["location_ids"]))
        return httpx.Response(200, json={"orders": []})

    list(square(handler).fetch_orders({"access_token": "AT"}, [f"L{i}" for i in range(23)], NOW))
    assert seen == [10, 10, 3]


def test_retries_rate_limits_then_gives_up():
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(429, headers={"Retry-After": "1"})

    with pytest.raises(ConnectorError):
        square(handler).list_locations({"access_token": "AT"})
    assert len(attempts) == 4


def test_401_is_an_auth_error():
    sq = square(lambda r: httpx.Response(401, json={"errors": [{"code": "UNAUTHORIZED", "detail": "revoked"}]}))
    with pytest.raises(AuthError, match="revoked"):
        sq.list_locations({"access_token": "AT"})


def test_list_locations():
    sq = square(lambda r: httpx.Response(200, json={"locations": [
        {"id": "L1", "name": "Main", "status": "ACTIVE", "timezone": "America/New_York",
         "address": {"address_line_1": "1 Main St", "locality": "Brooklyn"}},
        {"id": "L2", "name": "Old", "status": "INACTIVE"},
    ]}))
    locs = sq.list_locations({"access_token": "AT"})
    assert locs[0].address == "1 Main St, Brooklyn" and locs[0].is_active
    assert not locs[1].is_active


# ----------------------------------------------------------------------
# Credentials and OAuth state
# ----------------------------------------------------------------------

def test_credentials_round_trip_and_rotation(monkeypatch):
    token = encrypt_credentials({"access_token": "secret"})
    assert "secret" not in token
    assert decrypt_credentials(token) == {"access_token": "secret"}

    old = os.environ["POS_CREDENTIALS_KEY"]
    monkeypatch.setenv("POS_CREDENTIALS_KEY", f"{Fernet.generate_key().decode()},{old}")
    assert decrypt_credentials(token) == {"access_token": "secret"}  # old key still decrypts

    monkeypatch.setenv("POS_CREDENTIALS_KEY", Fernet.generate_key().decode())
    with pytest.raises(CredentialsKeyError):
        decrypt_credentials(token)


def test_oauth_state():
    pid = uuid4()
    state = sign_state(pid, "square", now=1000)
    assert verify_state(state, "square", now=1001) == pid
    with pytest.raises(InvalidState, match="expired"):
        verify_state(state, "square", now=1000 + 16 * 60)
    with pytest.raises(InvalidState, match="provider"):
        verify_state(state, "clover", now=1001)
    body, sig = state.split(".")
    with pytest.raises(InvalidState, match="signature"):
        verify_state(body + "x." + sig, "square", now=1001)


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------

def test_upsert_is_idempotent_and_replaces_lines(session):
    conn = make_connection(session)
    o = norm("O1")
    o.lines = []
    from connectors.base import NormalizedLine
    o.lines = [NormalizedLine("Latte"), NormalizedLine("Scone")]
    _, inserted, updated = upsert_orders(session, conn, [o], {})
    session.commit()
    assert (inserted, updated) == (1, 0)

    o.lines = [NormalizedLine("Latte")]
    o.refunded_cents = 400
    _, inserted, updated = upsert_orders(session, conn, [o], {})
    session.commit()
    assert (inserted, updated) == (0, 1)
    rows = session.exec(select(PosOrder)).all()
    assert len(rows) == 1 and rows[0].refunded_cents == 400
    assert [i.name for i in session.exec(select(PosOrderItem)).all()] == ["Latte"]


def test_refetch_does_not_restore_purged_contact(session):
    conn = make_connection(session)
    upsert_orders(session, conn, [norm("O1", phone="+16465550101", ordered=NOW - timedelta(days=40))], {})
    session.commit()
    assert matching.purge_expired_contacts(session, NOW) == 1
    session.commit()

    upsert_orders(session, conn, [norm("O1", phone="+16465550101", ordered=NOW - timedelta(days=40))], {})
    session.commit()
    row = session.exec(select(PosOrder)).one()
    assert row.customer_phone is None and row.raw is None


# ----------------------------------------------------------------------
# Matching
# ----------------------------------------------------------------------

def add_customer(session, phone):
    c = Customer(name="Ada", phone=phone)
    session.add(c)
    session.commit()
    return c


def test_phone_match_writes_a_link_that_matches_later_orders(session):
    conn = make_connection(session)
    ada = add_customer(session, "+16465550101")
    rows, _, _ = upsert_orders(session, conn, [
        norm("O1", phone="+16465550101", cust="C1"),
        norm("O2", cust="C1"),            # same POS profile, no phone on this one
        norm("O3", phone="+19995550000"),  # not a member
    ], {})
    assert matching.match_orders(session, rows, NOW) == 2
    session.commit()

    by_id = {o.external_order_id: o for o in session.exec(select(PosOrder)).all()}
    assert (by_id["O1"].customer_id, by_id["O1"].matched_via) == (ada.id, "phone")
    assert (by_id["O2"].customer_id, by_id["O2"].matched_via) == (ada.id, "link")
    assert by_id["O3"].customer_id is None
    assert session.exec(select(PosCustomerLink)).one().customer_id == ada.id


def test_return_inherits_the_sales_customer(session):
    conn = make_connection(session)
    ada = add_customer(session, "+16465550101")
    rows, _, _ = upsert_orders(session, conn, [norm("O1", phone="+16465550101")], {})
    matching.match_orders(session, rows, NOW)
    rows, _, _ = upsert_orders(session, conn, [norm("R1", kind="return", source="O1")], {})
    assert matching.match_orders(session, rows, NOW) == 1
    ret = session.exec(select(PosOrder).where(PosOrder.external_order_id == "R1")).one()
    assert (ret.customer_id, ret.matched_via) == (ada.id, "sale")


def test_signup_after_purchase_matches_inside_the_window_only(session):
    conn = make_connection(session)
    upsert_orders(session, conn, [
        norm("recent", phone="+16465550101", ordered=NOW - timedelta(days=5)),
        norm("old", phone="+16465550101", ordered=NOW - timedelta(days=31)),
    ], {})
    session.commit()
    ada = add_customer(session, "+16465550101")

    assert matching.rematch_window(session, NOW) == 1
    assert matching.purge_expired_contacts(session, NOW) == 1
    session.commit()
    by_id = {o.external_order_id: o for o in session.exec(select(PosOrder)).all()}
    assert by_id["recent"].customer_id == ada.id
    assert by_id["old"].customer_id is None and by_id["old"].customer_phone is None


def test_claim_order_rules(session):
    conn = make_connection(session)
    ada = add_customer(session, "+16465550101")
    bob = add_customer(session, "+16465550102")
    rows, _, _ = upsert_orders(session, conn, [
        norm("O1", cust="C7", ordered=NOW - timedelta(days=3)),
        norm("old", ordered=NOW - timedelta(days=31)),
        norm("R1", kind="return", source="O1"),
    ], {})
    o1, old, ret = rows

    matching.claim_order(session, o1, ada.id, NOW)
    assert (o1.customer_id, o1.matched_via) == (ada.id, "receipt")
    assert matching.claim_order(session, o1, ada.id, NOW) is o1  # repeat is a no-op
    with pytest.raises(matching.ClaimError, match="another customer"):
        matching.claim_order(session, o1, bob.id, NOW)
    with pytest.raises(matching.ClaimError, match="30 days"):
        matching.claim_order(session, old, ada.id, NOW)
    with pytest.raises(matching.ClaimError, match="sales"):
        matching.claim_order(session, ret, ada.id, NOW)
    # The claim linked the POS profile, so that shopper's next order matches itself.
    rows, _, _ = upsert_orders(session, conn, [norm("O9", cust="C7")], {})
    assert matching.match_orders(session, rows, NOW) == 1


# ----------------------------------------------------------------------
# Sync
# ----------------------------------------------------------------------

def test_first_sync_backfills_and_advances_cursor(session):
    conn = make_connection(session, cursor=None)
    later = NOW + timedelta(minutes=5)
    fake = FakeConnector([norm("O1", updated=NOW - timedelta(days=2)), norm("O2", updated=later, location="L2")])

    run = sync.sync_connection(session, fake, conn, NOW)
    assert run.status == "ok" and (run.orders_fetched, run.orders_inserted) == (2, 2)
    assert as_utc(fake.since_seen[0]) == NOW - timedelta(days=7) - sync.OVERLAP

    session.refresh(conn)
    assert as_utc(conn.sync_cursor) == later
    assert conn.sync_locked_at is None
    locs = {loc.external_location_id: loc for loc in session.exec(select(PartnerLocation)).all()}
    assert set(locs) == {"L1", "L2"} and not locs["L2"].is_active
    o2 = session.exec(select(PosOrder).where(PosOrder.external_order_id == "O2")).one()
    assert o2.partner_location_id == locs["L2"].id


def test_failed_sync_keeps_cursor_and_counts_failures(session):
    cursor = NOW - timedelta(hours=1)
    conn = make_connection(session, cursor=cursor)
    fake = FakeConnector([norm("O1"), norm("O2")], fail=1)

    run = sync.sync_connection(session, fake, conn, NOW)
    session.refresh(conn)
    assert run.status == "error" and "boom" in run.error
    assert as_utc(conn.sync_cursor) == cursor
    assert (conn.status, conn.consecutive_failures, conn.sync_locked_at) == ("active", 1, None)

    for _ in range(sync.MAX_FAILURES - 1):
        sync.sync_connection(session, fake, conn, NOW)
    session.refresh(conn)
    assert conn.status == "error"
    assert sync.sync_connection(session, fake, conn, NOW) is None  # errored connections are skipped


def test_auth_failure_errors_the_connection_at_once(session):
    conn = make_connection(session)

    class Revoked(FakeConnector):
        def list_locations(self, credentials):
            raise AuthError("revoked by merchant")

    run = sync.sync_connection(session, Revoked(), conn, NOW)
    session.refresh(conn)
    assert run.status == "error" and conn.status == "error"


def test_held_lease_skips_and_stale_lease_is_taken_over(session):
    conn = make_connection(session)
    conn.sync_locked_at = NOW - timedelta(minutes=5)
    session.add(conn)
    session.commit()
    assert sync.sync_connection(session, FakeConnector(), conn, NOW) is None

    conn.sync_locked_at = NOW - timedelta(hours=1)
    session.add(conn)
    session.commit()
    assert sync.sync_connection(session, FakeConnector(), conn, NOW).status == "ok"


def test_token_refreshed_when_close_to_expiry(session):
    conn = make_connection(session, expires=NOW + timedelta(days=2))
    fake = FakeConnector()
    sync.sync_connection(session, fake, conn, NOW)
    session.refresh(conn)
    assert fake.refreshed == 1
    assert decrypt_credentials(conn.credentials)["access_token"] == "at2"


def test_sync_matches_members(session):
    conn = make_connection(session)
    ada = add_customer(session, "+16465550101")
    run = sync.sync_connection(session, FakeConnector([norm("O1", phone="+16465550101")]), conn, NOW)
    assert run.orders_matched == 1
    assert session.exec(select(PosOrder)).one().customer_id == ada.id


# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------

@pytest.fixture
def api():
    fake = FakeConnector()
    app = FastAPI()
    app.include_router(partners_router, prefix="/admin")
    app.include_router(pos_oauth_router)
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(user_id=str(uuid4()), email=None, phone=None, role="admin", raw_claims={})
    app.dependency_overrides[connector_factory] = lambda: (lambda provider: fake)
    client = TestClient(app)
    client.fake = fake
    return client


def test_partner_crud(api):
    r = api.post("/admin/partners", json={"name": "Bean Co", "slug": "bean-co"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert api.post("/admin/partners", json={"name": "Dup", "slug": "bean-co"}).status_code == 409
    assert api.post("/admin/partners", json={"name": "Bad", "slug": "Bad Slug"}).status_code == 422
    assert api.patch(f"/admin/partners/{pid}", json={"is_active": False}).json()["is_active"] is False
    assert api.get(f"/admin/partners/{pid}").json()["connections"] == []


def test_oauth_round_trip(api, monkeypatch):
    monkeypatch.delenv("POS_OAUTH_RETURN_URL", raising=False)
    pid = api.post("/admin/partners", json={"name": "Bean Co", "slug": "bean-co"}).json()["id"]

    url = api.get("/admin/pos-connections/oauth/square/start", params={"partner_id": pid}).json()["authorize_url"]
    state = url.split("state=")[1]

    r = api.get("/pos/oauth/square/callback", params={"state": state, "code": "good"})
    assert r.status_code == 200 and r.json()["pos"] == "connected"
    cid = r.json()["connection_id"]

    conn = api.get(f"/admin/pos-connections/{cid}").json()
    assert conn["status"] == "active" and conn["has_credentials"]
    assert "credentials" not in conn
    strings = set(json.dumps(conn).split('"'))
    assert not strings & {"at", "rt"}  # neither token appears anywhere in the response
    assert {loc["external_location_id"] for loc in conn["locations"]} == {"L1", "L2"}
    cursor = datetime.fromisoformat(conn["sync_cursor"])
    assert timedelta(days=6, hours=23) < datetime.now(timezone.utc) - cursor < timedelta(days=7, hours=1)


def test_callback_rejects_bad_state_denial_and_foreign_merchant(api, monkeypatch):
    monkeypatch.setenv("POS_OAUTH_RETURN_URL", "https://admin.example/partners")
    a = api.post("/admin/partners", json={"name": "A", "slug": "a"}).json()["id"]
    b = api.post("/admin/partners", json={"name": "B", "slug": "b"}).json()["id"]

    r = api.get("/pos/oauth/square/callback", params={"state": "x.y", "code": "c"}, follow_redirects=False)
    assert r.status_code == 302 and "pos=error" in r.headers["location"]

    r = api.get("/pos/oauth/square/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert "access_denied" in r.headers["location"]

    ok = api.get("/pos/oauth/square/callback", params={"state": sign_state(a, "square"), "code": "c"},
                 follow_redirects=False)
    assert "pos=connected" in ok.headers["location"]
    clash = api.get("/pos/oauth/square/callback", params={"state": sign_state(b, "square"), "code": "c"},
                    follow_redirects=False)
    assert "another+partner" in clash.headers["location"]


def test_connection_pause_and_disconnect(api):
    pid = api.post("/admin/partners", json={"name": "A", "slug": "a"}).json()["id"]
    from uuid import UUID
    cid = api.get("/pos/oauth/square/callback",
                  params={"state": sign_state(UUID(pid), "square"), "code": "c"}).json()["connection_id"]

    assert api.patch(f"/admin/pos-connections/{cid}", json={"status": "disabled"}).json()["status"] == "disabled"
    assert api.patch(f"/admin/pos-connections/{cid}", json={"status": "revoked"}).status_code == 422

    gone = api.delete(f"/admin/pos-connections/{cid}").json()
    assert gone["status"] == "revoked" and not gone["has_credentials"]
    assert api.fake.revoked == [{"access_token": "at", "refresh_token": "rt"}]
    assert api.patch(f"/admin/pos-connections/{cid}", json={"status": "active"}).status_code == 409


def test_pos_orders_listing(api, session):
    conn = make_connection(session)
    upsert_orders(session, conn, [
        norm("O1", phone="+16465550101", ordered=NOW),
        norm("O2", ordered=NOW - timedelta(hours=1)),
    ], {})
    session.commit()
    body = api.get("/admin/pos-orders", params={"unmatched": True}).json()
    assert body["total"] == 2
    assert [(o["external_order_id"], o["has_contact"]) for o in body["items"]] == [("O1", True), ("O2", False)]
    assert "+16465550101" not in json.dumps(body)  # contact details stay out of the listing
