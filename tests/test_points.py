"""Terpee points from partner orders (connectors/points.py).

The ledger is append-only and reconcile_points writes differences, so most tests
check two things: the balance a customer ends up with, and that re-running
writes nothing new.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, select

from connectors import points
from connectors.points import PENDING_DAYS, balance, eligible_cents, reconcile_points
from connectors.store import as_utc, upsert_orders
from database import engine
from models import Customer, Partner, PartnerLocation, PartnerMember, PointsEntry, PosOrder
from tests.test_pos_connectors import NOW, TABLES as POS_TABLES, make_connection, norm

TABLES = POS_TABLES + [PartnerMember.__table__, PointsEntry.__table__]


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
    ada = Customer(name="Ada", phone="+16465550101")
    session.add(ada)
    session.commit()
    return conn, ada


def sale(session, conn, customer, ext="O1", total=1450, tax=120, tip=200, state="completed",
         refunded=0, location_id=None, closed=NOW - timedelta(days=1)):
    o = norm(ext, total=total, state=state)
    o.tax_cents, o.tip_cents, o.refunded_cents = tax, tip, refunded
    o.closed_at = closed
    rows, _, _ = upsert_orders(session, conn, [o], {})
    row = rows[0]
    row.customer_id = customer.id if customer else None
    row.partner_location_id = location_id
    session.add(row)
    session.commit()
    return row


def entries(session):
    return list(session.exec(select(PointsEntry).order_by(PointsEntry.created_at)).all())


# ----------------------------------------------------------------------
# The amount
# ----------------------------------------------------------------------

def test_eligible_is_total_minus_tax_and_tip(session, world):
    conn, ada = world
    o = sale(session, conn, ada)                      # $14.50 incl. $1.20 tax, $2.00 tip
    assert eligible_cents(o) == 1130                   # $11.30
    assert points.points_for(1130, 1) == 11            # rounds down


def test_refunds_and_returns_remove_their_share(session, world):
    conn, ada = world
    o = sale(session, conn, ada, total=2000, tax=0, tip=0, refunded=500)
    assert eligible_cents(o) == 1500
    ret = PosOrder(connection_id=conn.id, partner_id=conn.partner_id, external_order_id="R1",
                   kind="return", source_external_order_id="O1", state="completed",
                   total_cents=500, ordered_at=NOW, external_updated_at=NOW)
    assert eligible_cents(o, [ret]) == 1000


@pytest.mark.parametrize("state", ["open", "canceled"])
def test_only_completed_sales_earn(session, world, state):
    conn, ada = world
    sale(session, conn, ada, state=state)
    assert reconcile_points(session, NOW) == 0


def test_unmatched_orders_earn_nothing(session, world):
    conn, _ = world
    sale(session, conn, None)
    assert reconcile_points(session, NOW) == 0


# ----------------------------------------------------------------------
# Earning, pending, idempotency
# ----------------------------------------------------------------------

def test_earn_is_pending_for_seven_days_then_available(session, world):
    conn, ada = world
    o = sale(session, conn, ada, closed=NOW - timedelta(days=1))
    assert reconcile_points(session, NOW) == 1
    session.commit()
    (e,) = entries(session)
    assert (e.kind, e.points, e.eligible_cents, e.points_per_dollar) == ("earn", 11, 1130, 1)
    assert as_utc(e.available_at) == as_utc(o.closed_at) + timedelta(days=PENDING_DAYS)

    assert balance(session, ada.id, NOW) == points.Balance(available=0, pending=11)
    later = as_utc(o.closed_at) + timedelta(days=PENDING_DAYS, seconds=1)
    assert balance(session, ada.id, later) == points.Balance(available=11, pending=0)


def test_an_old_order_synced_late_is_available_at_once(session, world):
    conn, ada = world
    sale(session, conn, ada, closed=NOW - timedelta(days=10))
    reconcile_points(session, NOW)
    session.commit()
    assert balance(session, ada.id, NOW).available == 11


def test_reconcile_is_idempotent(session, world):
    conn, ada = world
    sale(session, conn, ada)
    assert reconcile_points(session, NOW) == 1
    session.commit()
    assert reconcile_points(session, NOW) == 0
    assert reconcile_points(session, NOW + timedelta(days=30)) == 0
    assert len(entries(session)) == 1


# ----------------------------------------------------------------------
# Refunds
# ----------------------------------------------------------------------

def test_refund_while_pending_cancels_without_touching_available(session, world):
    conn, ada = world
    o = sale(session, conn, ada, closed=NOW - timedelta(days=1))
    reconcile_points(session, NOW)
    session.commit()

    o.refunded_cents = 725                         # half of $14.50
    session.add(o)
    session.commit()
    assert reconcile_points(session, NOW + timedelta(days=2)) == 1
    session.commit()
    earn, refund = entries(session)
    assert (refund.kind, refund.points) == ("refund", -6)   # 11 earned -> 5 kept
    assert as_utc(refund.available_at) == as_utc(earn.available_at)

    assert balance(session, ada.id, NOW + timedelta(days=2)) == points.Balance(available=0, pending=5)


def test_refund_after_points_are_available_takes_them_back_now(session, world):
    conn, ada = world
    o = sale(session, conn, ada, closed=NOW - timedelta(days=10))
    reconcile_points(session, NOW)
    session.commit()

    o.refunded_cents = o.total_cents               # full refund
    session.add(o)
    session.commit()
    reconcile_points(session, NOW)
    session.commit()
    assert balance(session, ada.id, NOW) == points.Balance(available=0, pending=0)
    assert [e.kind for e in entries(session)] == ["earn", "refund"]


def test_return_order_reduces_the_sale(session, world):
    conn, ada = world
    sale(session, conn, ada, total=2000, tax=0, tip=0)
    reconcile_points(session, NOW)
    session.commit()

    ret = norm("R1", kind="return", source="O1", total=1000)
    upsert_orders(session, conn, [ret], {})
    session.commit()
    reconcile_points(session, NOW)
    session.commit()
    assert sum(e.points for e in entries(session)) == 10   # 20 earned, 10 returned


def test_points_follow_the_order_if_its_customer_goes_away(session, world):
    conn, ada = world
    o = sale(session, conn, ada)
    reconcile_points(session, NOW)
    session.commit()
    o.customer_id = None
    session.add(o)
    session.commit()
    reconcile_points(session, NOW)
    session.commit()
    assert sum(e.points for e in entries(session)) == 0
    assert entries(session)[-1].kind == "adjust"


# ----------------------------------------------------------------------
# Rules fixed at first earn
# ----------------------------------------------------------------------

def test_rate_is_fixed_by_the_first_earn(session, world, monkeypatch):
    conn, ada = world
    sale(session, conn, ada, ext="O1")
    reconcile_points(session, NOW)
    session.commit()

    monkeypatch.setenv("POINTS_PER_DOLLAR", "10")
    assert reconcile_points(session, NOW) == 0                     # O1 keeps its rate
    sale(session, conn, ada, ext="O2")
    reconcile_points(session, NOW)
    session.commit()
    by_order = {e.pos_order_id: (e.points, e.points_per_dollar) for e in entries(session)}
    assert sorted(by_order.values()) == [(11, 1), (113, 10)]


def test_location_that_does_not_earn(session, world):
    conn, ada = world
    loc = PartnerLocation(partner_id=conn.partner_id, connection_id=conn.id, name="Pop-up", is_active=False)
    session.add(loc)
    session.commit()
    sale(session, conn, ada, location_id=loc.id)
    assert reconcile_points(session, NOW) == 0


def test_turning_a_location_off_later_keeps_points_already_earned(session, world):
    conn, ada = world
    loc = PartnerLocation(partner_id=conn.partner_id, connection_id=conn.id, name="Main", is_active=True)
    session.add(loc)
    session.commit()
    sale(session, conn, ada, location_id=loc.id)
    reconcile_points(session, NOW)
    session.commit()

    loc.is_active = False
    session.add(loc)
    session.commit()
    assert reconcile_points(session, NOW) == 0
    assert balance(session, ada.id, NOW).total == 11


def test_inactive_partner_does_not_earn(session, world):
    conn, ada = world
    partner = session.get(Partner, conn.partner_id)
    partner.is_active = False
    session.add(partner)
    session.commit()
    sale(session, conn, ada)
    assert reconcile_points(session, NOW) == 0


# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------

from uuid import uuid4  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from auth import SupabaseAuthUser, get_current_user  # noqa: E402
from routes.admin.auth import require_admin  # noqa: E402
from routes.admin.partners import router as admin_partners_router  # noqa: E402
from routes_me import router as me_router  # noqa: E402


@pytest.fixture
def client(world, session):
    conn, ada = world
    ada.auth_user_id = uuid4()
    session.add(ada)
    session.commit()
    app = FastAPI()
    app.include_router(me_router)
    app.include_router(admin_partners_router, prefix="/admin")
    user = SupabaseAuthUser(user_id=str(ada.auth_user_id), email=None, phone=ada.phone,
                            role="authenticated", raw_claims={})
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: user
    return TestClient(app)


def test_customer_sees_balance_and_history(client, session, world):
    conn, ada = world
    # The route and reconcile_points read the real clock, so date these sales from it:
    # a sale a day before the fixed NOW stopped being pending 7 days after NOW.
    now = datetime.now(timezone.utc)
    sale(session, conn, ada, ext="O1", closed=now - timedelta(days=30))   # available
    sale(session, conn, ada, ext="O2", closed=now - timedelta(days=1))    # still pending
    reconcile_points(session)
    session.commit()

    body = client.get("/me/points").json()
    assert (body["available"], body["pending"]) == (11, 11)
    assert (body["points_per_dollar"], body["pending_days"]) == (1, 7)
    assert len(body["entries"]) == 2
    e = body["entries"][0]
    assert e["partner_name"] == "Bean Co" and e["kind"] == "earn" and e["points"] == 11
    assert {x["pending"] for x in body["entries"]} == {True, False}


def test_customer_with_no_points_gets_zero(client):
    body = client.get("/me/points").json()
    assert (body["available"], body["pending"], body["entries"]) == (0, 0, [])


def test_admin_sees_a_customers_ledger_and_points_per_order(client, session, world):
    conn, ada = world
    o = sale(session, conn, ada, closed=datetime.now(timezone.utc) - timedelta(days=1))   # still pending
    reconcile_points(session)
    session.commit()

    assert client.get(f"/admin/customers/{ada.id}/points").json()["pending"] == 11
    assert client.get(f"/admin/customers/{uuid4()}/points").status_code == 404
    orders = client.get("/admin/pos-orders").json()["items"]
    assert [(x["id"], x["points"]) for x in orders] == [(str(o.id), 11)]
