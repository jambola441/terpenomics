"""What customers are told about partner stores: who, where, and how points work.

The properties worth pinning: Square's coordinates, phone and hours come through
the sync and a blank never erases what someone entered; the POS only fills a
partner's description while it's blank; the admin and the partner can edit what
customers read, the partner only their own text; a store without a POS can be
added by hand and put on the map; and customers see only active partners and
stores, with the program's real numbers, changes showing at once.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from connectors.base import ExternalLocation
from connectors.store import import_locations
from database import engine
from models import Partner, PartnerLocation, PartnerMember
from routes.admin.auth import require_admin
from routes.admin.partners import router as admin_partners_router
from routes.customer import router as customer_router
from routes.partner import router as partner_router
from services import places
from tests.test_pos_connectors import TABLES as POS_TABLES, make_connection, square

TABLES = POS_TABLES + [PartnerMember.__table__]


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.drop_all(engine, tables=list(reversed(TABLES)))
    SQLModel.metadata.create_all(engine, tables=TABLES)
    yield


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


def user(email="alice@beanco.com", role="authenticated"):
    return SupabaseAuthUser(user_id=str(uuid4()), email=email, phone=None, role=role,
                            raw_claims={"user_metadata": {}})


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(admin_partners_router, prefix="/admin")
    app.include_router(partner_router)
    app.include_router(customer_router)
    app.dependency_overrides[get_current_user] = lambda: user()
    app.dependency_overrides[require_admin] = lambda: user("ops@terpee.example", "admin")
    return TestClient(app)


# --------------------------------------------------------------------------- Square


def test_square_sends_where_a_store_is_and_when_it_is_open():
    sq = square(lambda r: httpx.Response(200, json={"locations": [{
        "id": "L1", "name": "Main", "status": "ACTIVE",
        "address": {"address_line_1": "1 Main St", "locality": "Brooklyn"},
        "coordinates": {"latitude": 40.6782, "longitude": -73.9442},
        "phone_number": " +1 718-555-0100 ",
        "business_hours": {"periods": [
            {"day_of_week": "SAT", "start_local_time": "10:00:00", "end_local_time": "16:00:00"},
            {"day_of_week": "MON", "start_local_time": "08:30:00", "end_local_time": "18:00:00"},
            {"day_of_week": "FRI", "start_local_time": "18:00:00", "end_local_time": "02:00:00"},
        ]},
        "description": "Coffee and pastries.", "website_url": "https://beanco.example",
        "logo_url": "https://sq.example/logo-small.png", "full_format_logo_url": "https://sq.example/logo.png",
    }, {"id": "L2", "name": "Truck", "status": "ACTIVE"}]}))
    main, truck = sq.list_locations({"access_token": "AT"})
    assert (main.lat, main.lng, main.phone) == (40.6782, -73.9442, "+1 718-555-0100")
    assert main.hours == [{"day": "MON", "open": "08:30", "close": "18:00"},
                          {"day": "FRI", "open": "18:00", "close": "02:00"},
                          {"day": "SAT", "open": "10:00", "close": "16:00"}]
    assert (main.description, main.website_url, main.logo_url) == (
        "Coffee and pastries.", "https://beanco.example", "https://sq.example/logo.png")
    assert (truck.lat, truck.phone, truck.hours, truck.description) == (None, None, None, None)


def test_the_sync_keeps_what_square_sends_and_never_erases_what_someone_entered(session):
    conn = make_connection(session)
    full = ExternalLocation("L1", "Main", address="1 Main St", lat=40.1, lng=-73.9, phone="555-0100",
                            hours=[{"day": "MON", "open": "09:00", "close": "17:00"}],
                            description="Coffee and pastries.", website_url="https://beanco.example")
    import_locations(session, conn, [full])
    session.commit()
    loc = session.exec(select(PartnerLocation)).one()
    partner = session.get(Partner, conn.partner_id)
    assert (loc.lat, loc.lng, loc.phone, loc.hours[0]["day"]) == (40.1, -73.9, "555-0100", "MON")
    assert (partner.description, partner.website_url) == ("Coffee and pastries.", "https://beanco.example")

    # Someone writes their own description; Square later sends nothing for the store.
    partner.description = "Our own words."
    session.add(partner)
    session.commit()
    import_locations(session, conn, [ExternalLocation("L1", "Main", address="1 Main St",
                                                      description="Square's words.")])
    session.commit()
    session.refresh(loc)
    session.refresh(partner)
    assert (loc.lat, loc.lng, loc.phone, loc.hours is not None) == (40.1, -73.9, "555-0100", True)
    assert partner.description == "Our own words."


# --------------------------------------------------------------------------- admin and partner


def test_the_admin_writes_what_customers_read(session, client):
    conn = make_connection(session)
    pid = str(conn.partner_id)
    got = client.patch(f"/admin/partners/{pid}", json={
        "description": "  Coffee and pastries, roasted in Peekskill.  ", "category": "Café",
        "website_url": "beanco.example"}).json()
    assert (got["description"], got["category"], got["website_url"]) == (
        "Coffee and pastries, roasted in Peekskill.", "Café", "https://beanco.example")
    assert client.patch(f"/admin/partners/{pid}", json={"website_url": "not a site"}).status_code == 422
    assert client.patch(f"/admin/partners/{pid}", json={"description": "x" * 401}).status_code == 422
    assert client.patch(f"/admin/partners/{pid}", json={"description": ""}).json()["description"] is None


def test_a_store_without_a_pos_is_added_by_hand_and_put_on_the_map(session, client, monkeypatch):
    partner = Partner(name="Leaf Café", slug="leaf-cafe")
    session.add(partner)
    session.commit()
    monkeypatch.setattr(places, "search", lambda q: [
        {"label": "279 Lake Dr, Lake Peekskill, NY", "lat": 41.338, "lng": -73.882}])
    [hit] = client.get("/admin/geocode", params={"q": "279 Lake Dr, Lake Peekskill"}).json()

    loc = client.post(f"/admin/partners/{partner.id}/locations", json={
        "name": "Lake Peekskill", "address": "279 Lake Dr, Lake Peekskill, NY 10537",
        "lat": hit["lat"], "lng": hit["lng"], "phone": "845-555-0100"}).json()
    assert (loc["lat"], loc["lng"], loc["connection_id"]) == (41.338, -73.882, None)

    assert client.patch(f"/admin/partner-locations/{loc['id']}", json={"lat": 41.0}).status_code == 422
    moved = client.patch(f"/admin/partner-locations/{loc['id']}", json={"lat": None, "lng": None}).json()
    assert (moved["lat"], moved["lng"], moved["name"]) == (None, None, "Lake Peekskill")
    assert client.delete(f"/admin/partner-locations/{loc['id']}").json() == {"ok": True}


def test_a_store_from_the_pos_is_turned_off_not_deleted(session, client):
    conn = make_connection(session)
    import_locations(session, conn, [ExternalLocation("L1", "Main")])
    session.commit()
    loc = session.exec(select(PartnerLocation)).one()
    assert client.delete(f"/admin/partner-locations/{loc.id}").status_code == 409


def test_a_partner_writes_their_own_description_and_nothing_else(session, client):
    conn = make_connection(session)
    session.add(PartnerMember(partner_id=conn.partner_id, email="alice@beanco.com"))
    other = Partner(name="Other", slug="other")
    session.add(other)
    session.commit()
    got = client.patch(f"/partner/partners/{conn.partner_id}", json={
        "description": "Fresh coffee daily.", "website_url": "https://beanco.example",
        "name": "Renamed", "category": "Bank"}).json()
    assert (got["description"], got["website_url"], got["name"], got["category"]) == (
        "Fresh coffee daily.", "https://beanco.example", "Bean Co", None)
    assert client.patch(f"/partner/partners/{other.id}", json={"description": "x"}).status_code in (403, 404)


# --------------------------------------------------------------------------- customers


def test_customers_see_active_partners_and_stores_with_the_programs_numbers(session, client):
    bean = Partner(name="Bean Co", slug="bean-co", description="Coffee.", category="Café")
    gone = Partner(name="Gone", slug="gone", is_active=False)
    session.add_all([bean, gone])
    session.flush()
    session.add_all([
        PartnerLocation(partner_id=bean.id, name="Main", address="1 Main St", lat=40.1, lng=-73.9,
                        hours=[{"day": "MON", "open": "09:00", "close": "17:00"}]),
        PartnerLocation(partner_id=bean.id, name="Closed", is_active=False),
        PartnerLocation(partner_id=gone.id, name="Somewhere"),
    ])
    session.commit()

    got = client.get("/customer/partners").json()
    assert got["program"] == {"points_per_dollar": 1, "pending_days": 7, "claim_window_days": 30, "rewards": None}
    [p] = got["partners"]
    assert (p["name"], p["slug"], p["category"], p["description"]) == ("Bean Co", "bean-co", "Café", "Coffee.")
    assert [(loc["name"], loc["lat"], loc["hours"][0]["day"]) for loc in p["locations"]] == [("Main", 40.1, "MON")]

    page = client.get("/customer/partners/bean-co").json()
    assert page["name"] == "Bean Co" and page["program"]["pending_days"] == 7 and len(page["locations"]) == 1
    assert client.get("/customer/partners/gone").status_code == 404
    assert client.get("/customer/partners/nope").status_code == 404


def test_an_edit_shows_to_customers_at_once(session, client):
    bean = Partner(name="Bean Co", slug="bean-co")
    session.add(bean)
    session.commit()
    assert client.get("/customer/partners/bean-co").json()["description"] is None   # now cached
    client.patch(f"/admin/partners/{bean.id}", json={"description": "Coffee."})
    assert client.get("/customer/partners/bean-co").json()["description"] == "Coffee."
    assert client.get("/customer/partners").json()["partners"][0]["description"] == "Coffee."


def test_what_points_are_for_is_said_once_rewards_are_set_up(session, client, monkeypatch):
    monkeypatch.setenv("POINTS_REWARDS", "  100 points = $5 off at any partner store.  ")
    assert client.get("/customer/partners").json()["program"]["rewards"] == "100 points = $5 off at any partner store."
