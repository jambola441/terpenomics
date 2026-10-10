"""Feature flags (services/flags.py): global defaults, per-customer overrides,
and where they surface — GET /me for the apps, /admin/customers/{id}/flags."""
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import ConsentEvent, Customer, CustomerFlag
from routes.admin.auth import require_admin
from routes.admin.customers import router as admin_customers_router
from routes_me import router as me_router
from services import flags

AUTH_UID = uuid4()


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    monkeypatch.delenv("PORTAL_FLAGS", raising=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (CustomerFlag, ConsentEvent, Customer):
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


def _resolve(customer_id):
    with Session(engine) as session:
        return flags.resolve(session, customer_id)


# --- resolution -------------------------------------------------------------

def test_everything_is_off_by_default(customer_id):
    resolved = _resolve(customer_id)
    assert set(resolved) == set(flags.FLAGS)
    assert not any(resolved.values())


def test_portal_flags_turns_a_flag_on_for_everyone(customer_id, monkeypatch):
    monkeypatch.setenv("PORTAL_FLAGS", "lines")
    resolved = _resolve(customer_id)
    assert resolved["lines"] is True
    assert resolved["line_passport"] is False


def test_unknown_and_malformed_entries_are_ignored(customer_id, monkeypatch):
    monkeypatch.setenv("PORTAL_FLAGS", " Lines , retired_flag, line_page:abc%, trip_planner:%, ")
    resolved = _resolve(customer_id)
    assert resolved["lines"] is True  # names are case-insensitive, whitespace trimmed
    assert resolved["line_page"] is False and resolved["trip_planner"] is False
    assert "retired_flag" not in resolved


def test_a_percentage_rolls_out_to_a_stable_share():
    ids = [uuid4() for _ in range(2000)]
    first = [flags._in_rollout("lines_grouped", i, 25) for i in ids]
    again = [flags._in_rollout("lines_grouped", i, 25) for i in ids]
    assert first == again  # the same person always gets the same answer
    assert 0.20 < sum(first) / len(ids) < 0.30
    # Each flag draws its own share, rather than the same people every time.
    other = [flags._in_rollout("trip_planner", i, 25) for i in ids]
    assert first != other
    assert not any(flags._in_rollout("lines", i, 0) for i in ids[:50])
    assert all(flags._in_rollout("lines", i, 100) for i in ids[:50])


def test_an_override_beats_the_default_either_way(customer_id, monkeypatch):
    monkeypatch.setenv("PORTAL_FLAGS", "lines")
    with Session(engine) as session:
        flags.set_override(session, customer_id, "lines", False)
        flags.set_override(session, customer_id, "line_passport", True)
    resolved = _resolve(customer_id)
    assert resolved["lines"] is False
    assert resolved["line_passport"] is True


def test_clearing_an_override_returns_to_the_default(customer_id, monkeypatch):
    monkeypatch.setenv("PORTAL_FLAGS", "lines")
    with Session(engine) as session:
        flags.set_override(session, customer_id, "lines", False)
        flags.set_override(session, customer_id, "lines", None)
        assert session.exec(select(CustomerFlag)).all() == []
    assert _resolve(customer_id)["lines"] is True


def test_an_unknown_flag_cannot_be_overridden(customer_id):
    with Session(engine) as session, pytest.raises(KeyError):
        flags.set_override(session, customer_id, "no_such_flag", True)


def test_passport_rewards_has_its_own_switch():
    # Passport progress and rewards for it are separate decisions.
    assert {"line_passport", "line_passport_rewards"} <= set(flags.FLAGS)


# --- where flags surface ----------------------------------------------------

def test_me_carries_the_customers_flags(client, customer_id, monkeypatch):
    monkeypatch.setenv("PORTAL_FLAGS", "lines")
    body = client.get("/me").json()
    assert body["flags"]["lines"] is True
    assert set(body["flags"]) == set(flags.FLAGS)


def test_saving_the_profile_keeps_the_flags(client, customer_id, monkeypatch):
    # The portal replaces its copy of the profile with what POST /me returns.
    monkeypatch.setenv("PORTAL_FLAGS", "lines")
    body = client.post("/me", json={"first_name": "Ada"}).json()
    assert body["flags"]["lines"] is True


def test_admin_sees_where_each_answer_comes_from(client, customer_id, monkeypatch):
    monkeypatch.setenv("PORTAL_FLAGS", "lines,lines_grouped:50%")
    client.post(f"/admin/customers/{customer_id}/flags/line_passport", json={"enabled": True})
    rows = {r["flag"]: r for r in client.get(f"/admin/customers/{customer_id}/flags").json()}
    assert rows["lines"]["source"] == "default" and rows["lines"]["enabled"] is True
    assert rows["lines_grouped"]["source"] == "rollout" and rows["lines_grouped"]["default_percent"] == 50
    assert rows["line_passport"]["source"] == "override" and rows["line_passport"]["override"] is True
    assert rows["trip_planner"]["source"] == "default" and rows["trip_planner"]["enabled"] is False


def test_admin_can_clear_an_override(client, customer_id):
    url = f"/admin/customers/{customer_id}/flags/lines"
    client.post(url, json={"enabled": True})
    rows = {r["flag"]: r for r in client.post(url, json={"enabled": None}).json()}
    assert rows["lines"]["override"] is None and rows["lines"]["enabled"] is False


def test_admin_unknown_flag_or_customer_is_404(client, customer_id):
    assert client.post(f"/admin/customers/{customer_id}/flags/nope", json={"enabled": True}).status_code == 404
    assert client.get(f"/admin/customers/{uuid4()}/flags").status_code == 404
