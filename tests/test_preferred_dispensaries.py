"""Followed stores and the home feed they build.

The feed is the portal's landing screen, so the properties worth pinning are the
ones a shopper would notice immediately: it shows the stores they follow, in the
order they followed them, and it shows nobody else's.
"""
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser, get_current_user
from database import engine
from models import (
    Customer,
    Dispensary,
    FeaturedListing,
    Listing,
    PosType,
    PreferredDispensary,
)
from routes_me import router as me_router

AUTH_UID = uuid4()
OTHER_UID = uuid4()


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (FeaturedListing, PreferredDispensary, Listing, Dispensary, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


@pytest.fixture
def world():
    """Two customers and three stores, one of them retired."""
    with Session(engine) as session:
        customer = Customer(name="Ada", phone="+15552020001", auth_user_id=AUTH_UID)
        other = Customer(name="Grace", phone="+15552020002", auth_user_id=OTHER_UID)
        bergen = Dispensary(
            name="Bergen Botanics", slug="bergen", accepts_pickup=True,
            pos_type=PosType.alleaves, address="623 Bergen St",
        )
        atlantic = Dispensary(name="Atlantic Leaf", slug="atlantic", accepts_pickup=False)
        retired = Dispensary(name="Closed Co", slug="closed", is_active=False)
        session.add_all([customer, other, bergen, atlantic, retired])
        session.commit()

        session.add_all([
            # As a store actually publishes it: brand repeated, potency,
            # classification, size, format and the scraper's own debris.
            Listing(
                dispensary_id=bergen.id,
                scraped_name="Sunset Sherbet -Indica- 88.5% THC | 3.5g Flower | Aeris  -ii3 front",
                scraped_brand="Aeris", scraped_category="flower", variant="3.5g",
                strain="Sunset Sherbet",
                price_cents=4500, in_stock=True, is_active=True,
            ),
            Listing(
                dispensary_id=bergen.id, scraped_name="Blue Dream Cart",
                scraped_brand="Aeris", scraped_category="cart", variant="1g",
                price_cents=6000, in_stock=True, is_active=True,
            ),
            # Out of stock: real row, but nothing a shopper can act on today.
            Listing(
                dispensary_id=bergen.id, scraped_name="Sold Out Gummies",
                scraped_category="edible", price_cents=2000,
                in_stock=False, is_active=True,
            ),
            Listing(
                dispensary_id=atlantic.id, scraped_name="Northern Lights",
                scraped_category="flower", price_cents=5000,
                in_stock=True, is_active=True,
            ),
        ])
        session.commit()

        return {
            "customer_id": customer.id,
            "bergen_id": bergen.id,
            "atlantic_id": atlantic.id,
            "retired_id": retired.id,
        }


def _client(auth_uid=AUTH_UID) -> TestClient:
    app = FastAPI()
    app.include_router(me_router)
    app.dependency_overrides[get_current_user] = lambda: SupabaseAuthUser(
        user_id=str(auth_uid), email=None, phone=None,
        role="authenticated", raw_claims={},
    )
    return TestClient(app)


# ---------------------------
# Following stores
# ---------------------------

def test_starts_empty(world):
    res = _client().get("/me/preferred-dispensaries")
    assert res.status_code == 200
    assert res.json() == []


def test_follow_returns_the_updated_set(world):
    client = _client()
    res = client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    assert res.status_code == 200
    assert [d["name"] for d in res.json()] == ["Bergen Botanics"]


def test_follow_order_is_preserved(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['atlantic_id']}")
    res = client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    # Followed second, so it comes second -- the feed reads this order directly.
    assert [d["name"] for d in res.json()] == ["Atlantic Leaf", "Bergen Botanics"]


def test_following_twice_is_idempotent(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    res = client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_cannot_follow_an_inactive_store(world):
    res = _client().post(f"/me/preferred-dispensaries/{world['retired_id']}")
    assert res.status_code == 404


def test_cannot_follow_a_store_that_does_not_exist(world):
    res = _client().post(f"/me/preferred-dispensaries/{uuid4()}")
    assert res.status_code == 404


def test_unfollow_removes_it(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    res = client.delete(f"/me/preferred-dispensaries/{world['bergen_id']}")
    assert res.status_code == 200
    assert res.json() == []


def test_unfollowing_something_you_never_followed_is_not_an_error(world):
    res = _client().delete(f"/me/preferred-dispensaries/{world['bergen_id']}")
    assert res.status_code == 200
    assert res.json() == []


def test_preferences_are_per_customer(world):
    _client().post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    # Grace follows nothing, and Ada's choice must not leak into her feed.
    assert _client(OTHER_UID).get("/me/preferred-dispensaries").json() == []
    assert _client(OTHER_UID).get("/me/feed").json()["sections"] == []


# ---------------------------
# The feed
# ---------------------------
#
# What each rail *contains* is covered in test_feed_rails.py; these are about
# the endpoint's contract -- the two views, and the fact that it only ever shows
# the caller their own stores.

def test_feed_is_empty_before_following_anything(world):
    body = _client().get("/me/feed").json()
    assert body["sections"] == []
    assert body["combined"] is None


def test_the_store_view_has_one_section_per_followed_store(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    client.post(f"/me/preferred-dispensaries/{world['atlantic_id']}")

    body = client.get("/me/feed").json()
    assert body["view"] == "store"
    assert [s["dispensary"]["name"] for s in body["sections"]] == ["Bergen Botanics", "Atlantic Leaf"]
    assert set(body["sections"][0]["rails"]) == {"featured", "new", "recommended", "deals"}


def test_the_combined_view_pools_the_stores_instead(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    client.post(f"/me/preferred-dispensaries/{world['atlantic_id']}")

    body = client.get("/me/feed", params={"view": "combined"}).json()
    assert body["view"] == "combined"
    assert body["sections"] == []
    assert set(body["combined"]) == {"featured", "new", "recommended", "deals"}
    # Every card says which store it is at, because the rail mixes them.
    for items in body["combined"].values():
        assert all("dispensary_id" in item for item in items)
    # And the stores themselves come along, so the client can name them.
    assert {d["name"] for d in body["dispensaries"]} == {"Bergen Botanics", "Atlantic Leaf"}


def test_the_combined_view_shows_a_product_once(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    client.post(f"/me/preferred-dispensaries/{world['atlantic_id']}")

    # Both stores carry Northern Lights -- same product identity, and Atlantic
    # (from the fixture) is dearer at 5000.
    with Session(engine) as session:
        session.add(Listing(
            dispensary_id=world["bergen_id"], scraped_name="Northern Lights",
            scraped_category="flower", price_cents=3000, in_stock=True, is_active=True,
        ))
        session.commit()

    rail = client.get("/me/feed", params={"view": "combined"}).json()["combined"]["new"]
    northern = [item for item in rail if item["display_name"] == "Northern Lights"]
    assert len(northern) == 1
    assert northern[0]["price_cents"] == 3000
    assert northern[0]["other_store_count"] == 2


def test_the_feed_shows_only_stock_you_can_buy(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")

    rails = client.get("/me/feed").json()["sections"][0]["rails"]
    names = {item["display_name"] for items in rails.values() for item in items}
    assert "Sold Out Gummies" not in names


def test_the_feed_names_listings_for_a_shopper_not_a_catalogue(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")

    rail = client.get("/me/feed").json()["sections"][0]["rails"]["new"]
    dirty = next(i for i in rail if i["scraped_name"].startswith("Sunset Sherbet -Indica-"))
    assert dirty["display_name"] == "Sunset Sherbet"
    # The raw string stays on the payload: it is what search matches against and
    # the only provenance for what the store actually published.
    assert dirty["scraped_name"] == "Sunset Sherbet -Indica- 88.5% THC | 3.5g Flower | Aeris  -ii3 front"


def test_the_feed_filters_by_category(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")
    client.post(f"/me/preferred-dispensaries/{world['atlantic_id']}")

    sections = client.get("/me/feed", params={"category": "cart"}).json()["sections"]
    assert [i["display_name"] for i in sections[0]["rails"]["new"]] == ["Blue Dream Cart"]
    # Atlantic stocks no carts, but the shopper still follows it, so the empty
    # section stays rather than the store vanishing from their feed.
    assert sections[1]["rails"]["new"] == []
    assert sections[1]["total"] == 0


def test_each_rail_is_capped(world):
    client = _client()
    client.post(f"/me/preferred-dispensaries/{world['bergen_id']}")

    rails = client.get("/me/feed", params={"per_rail": 1}).json()["sections"][0]["rails"]
    assert all(len(items) <= 1 for items in rails.values())
    # The cap trims what is shown, not what the count reports.
    assert client.get("/me/feed", params={"per_rail": 1}).json()["sections"][0]["total"] == 2


# ---------------------------
# Profile
# ---------------------------

def test_profile_edit_changes_name_and_opt_in(world):
    client = _client()
    res = client.post("/me", json={"name": "Ada L.", "marketing_opt_in": True})
    assert res.status_code == 200
    assert res.json()["name"] == "Ada L."
    assert res.json()["marketing_opt_in"] is True
    assert client.get("/me").json()["name"] == "Ada L."


def test_profile_edit_leaves_omitted_fields_alone(world):
    client = _client()
    client.post("/me", json={"name": "Ada L.", "marketing_opt_in": True})
    res = client.post("/me", json={"name": "Ada Lovelace"})
    assert res.json()["marketing_opt_in"] is True


def test_profile_edit_cannot_change_identity(world):
    client = _client()
    before = client.get("/me").json()
    # phone and email are how sign-in and walk-in matching find this person, so
    # the endpoint ignores them rather than letting a profile edit rewrite them.
    client.post("/me", json={"phone": "+15559999999", "email": "someone@else.test"})
    after = client.get("/me").json()
    assert after["phone"] == before["phone"]
    assert after["email"] == before["email"]


def test_blank_name_clears_it(world):
    client = _client()
    client.post("/me", json={"name": "Ada L."})
    assert client.post("/me", json={"name": "   "}).json()["name"] is None
