"""The four rails the home feed is built from.

Each answers a different question, and the tests are about the ranking rather
than the plumbing: which product a shopper sees first is the whole feature.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, select

from database import engine
from models import (
    Customer,
    Dispensary,
    FeaturedListing,
    ItemFeedback,
    Listing,
    Purchase,
    PurchaseItem,
)
from services import feed


@pytest.fixture(autouse=True)
def fresh_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (FeaturedListing, PurchaseItem, Purchase, Listing, Dispensary, Customer):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
    yield


def _listing(dispensary, **kwargs):
    defaults = dict(
        scraped_category="flower",
        subtype=None,
        product_line=None,
        strain="Blue Dream",
        variant="3.5g",
        scraped_brand="Aeris",
        scraped_name="Blue Dream 3.5g",
        price_cents=4000,
        in_stock=True,
        is_active=True,
    )
    defaults.update(kwargs)
    return Listing(dispensary_id=dispensary.id, **defaults)


@pytest.fixture
def world():
    """Two followed stores and two the shopper does not follow, so the market
    comparison has somewhere to compare against."""
    with Session(engine) as session:
        customer = Customer(name="Ada", phone="+15552030001", auth_user_id=uuid4())
        mine = Dispensary(name="Bergen Botanics", slug="bergen")
        also_mine = Dispensary(name="Atlantic Leaf", slug="atlantic")
        elsewhere = Dispensary(name="Far Away", slug="far")
        pricey = Dispensary(name="Pricey Co", slug="pricey")
        session.add_all([customer, mine, also_mine, elsewhere, pricey])
        session.commit()

        now = datetime.utcnow()
        rows = {
            # Carried at four stores; cheapest at Bergen, so it is a deal there.
            "bargain": _listing(mine, strain="Blue Dream", price_cents=3000),
            "bargain_far": _listing(elsewhere, strain="Blue Dream", price_cents=5000),
            "bargain_pricey": _listing(pricey, strain="Blue Dream", price_cents=5500),
            "bargain_atlantic": _listing(also_mine, strain="Blue Dream", price_cents=5200),
            # Carried nowhere else: no comparison, so never a deal.
            "exclusive": _listing(mine, strain="House Special", price_cents=1000),
            # Dearer here than elsewhere.
            "overpriced": _listing(mine, strain="Gelato", price_cents=9000),
            "overpriced_far": _listing(elsewhere, strain="Gelato", price_cents=4000),
            # The newest thing on Bergen's shelf.
            "arrival": _listing(mine, strain="Fresh Drop", price_cents=4400),
            # Something the shopper has bought before, by brand.
            "familiar": _listing(mine, scraped_brand="Botanica", strain="Wedding Cake", price_cents=4600),
            # Same brand, but a strain they thumbed down.
            "disliked": _listing(mine, scraped_brand="Botanica", strain="Sour Diesel", price_cents=4700),
        }
        session.add_all(rows.values())
        session.commit()

        # created_at is set on insert; age them explicitly so "newest" is unambiguous.
        ages_in_days = {
            "arrival": 0, "familiar": 2, "disliked": 4,
            "bargain": 10, "exclusive": 20, "overpriced": 30,
        }
        for name, days in ages_in_days.items():
            rows[name].created_at = now - timedelta(days=days)
            session.add(rows[name])
        session.commit()

        ids = {name: row.id for name, row in rows.items()}
        return {
            "customer_id": customer.id,
            "mine": mine.id,
            "also_mine": also_mine.id,
            "listings": ids,
        }


def _names(items):
    return [item.listing.strain for item in items]


# ---------------------------
# Featured
# ---------------------------

def test_featured_is_whatever_the_store_picked_in_its_order(world):
    with Session(engine) as session:
        session.add_all([
            FeaturedListing(dispensary_id=world["mine"], listing_id=world["listings"]["overpriced"], position=1),
            FeaturedListing(dispensary_id=world["mine"], listing_id=world["listings"]["exclusive"], position=0),
        ])
        session.commit()

        rail = feed.featured(session, [world["mine"]], limit=8)
        assert _names(rail) == ["House Special", "Gelato"]


def test_a_pick_that_sold_out_drops_off(world):
    with Session(engine) as session:
        session.add(FeaturedListing(dispensary_id=world["mine"], listing_id=world["listings"]["exclusive"]))
        listing = session.get(Listing, world["listings"]["exclusive"])
        listing.in_stock = False
        session.add(listing)
        session.commit()

        assert feed.featured(session, [world["mine"]], limit=8) == []


def test_featured_is_empty_until_someone_picks_something(world):
    with Session(engine) as session:
        assert feed.featured(session, [world["mine"]], limit=8) == []


# ---------------------------
# New arrivals
# ---------------------------

def test_new_arrivals_are_newest_first(world):
    with Session(engine) as session:
        rail = feed.new_arrivals(session, [world["mine"]], limit=3)
        assert rail[0].listing.strain == "Fresh Drop"
        # The rest follow in descending age, not in menu order.
        assert _names(rail) == ["Fresh Drop", "Wedding Cake", "Sour Diesel"]


def test_new_arrivals_only_covers_the_stores_asked_for(world):
    with Session(engine) as session:
        rail = feed.new_arrivals(session, [world["also_mine"]], limit=8)
        assert {item.listing.dispensary_id for item in rail} == {world["also_mine"]}


# ---------------------------
# Deals
# ---------------------------

def test_a_deal_is_cheaper_than_the_average_elsewhere(world):
    with Session(engine) as session:
        rail = feed.deals(session, [world["mine"]], limit=8)
        assert "Blue Dream" in _names(rail)

        deal = next(item for item in rail if item.listing.strain == "Blue Dream")
        # 5000, 5500 and 5200 elsewhere average 5233; Bergen sells it for 3000.
        assert deal.other_store_count == 3
        assert deal.other_avg_cents == 5233
        assert deal.saving_cents == 2233


def test_something_no_one_else_carries_is_not_a_deal(world):
    with Session(engine) as session:
        assert "House Special" not in _names(feed.deals(session, [world["mine"]], limit=8))


def test_something_dearer_here_is_not_a_deal(world):
    with Session(engine) as session:
        assert "Gelato" not in _names(feed.deals(session, [world["mine"]], limit=8))


def test_deals_lead_with_the_biggest_saving(world):
    with Session(engine) as session:
        rail = feed.deals(session, [world["mine"], world["also_mine"]], limit=8)
        savings = [item.saving_cents for item in rail]
        assert savings == sorted(savings, reverse=True)


def test_out_of_stock_rows_do_not_set_the_comparison_price(world):
    with Session(engine) as session:
        # If the expensive stores stop carrying it, there is nothing to beat.
        for name in ("bargain_far", "bargain_pricey", "bargain_atlantic"):
            listing = session.get(Listing, world["listings"][name])
            listing.in_stock = False
            session.add(listing)
        session.commit()

        assert "Blue Dream" not in _names(feed.deals(session, [world["mine"]], limit=8))


# ---------------------------
# Recommended
# ---------------------------

def _buy(session, customer_id, listing_id, feedback=None):
    purchase = Purchase(customer_id=customer_id, purchased_at=datetime.utcnow())
    session.add(purchase)
    session.commit()
    session.add(PurchaseItem(purchase_id=purchase.id, listing_id=listing_id, feedback=feedback))
    session.commit()


def test_a_shopper_we_know_nothing_about_gets_what_the_market_carries_most(world):
    with Session(engine) as session:
        rail = feed.recommended(session, [world["mine"]], world["customer_id"], limit=8)
        # Blue Dream is at three other stores; nothing else is at more than one.
        assert rail[0].listing.strain == "Blue Dream"
        assert rail[0].other_store_count == 3


def test_a_liked_brand_pulls_its_other_products_up(world):
    with Session(engine) as session:
        _buy(session, world["customer_id"], world["listings"]["familiar"], ItemFeedback.like)

        rail = feed.recommended(session, [world["mine"]], world["customer_id"], limit=8)
        assert rail[0].listing.scraped_brand == "Botanica"


def test_a_thumbs_down_outweighs_the_purchase_it_followed(world):
    with Session(engine) as session:
        _buy(session, world["customer_id"], world["listings"]["disliked"], ItemFeedback.dislike)

        profile = feed.taste_profile(session, world["customer_id"])
        # Bought once (+1) then disliked (-4): the strain is not a preference.
        assert "Sour Diesel" not in profile.strains
        assert "Botanica" not in profile.brands


def test_an_unrated_purchase_still_counts_as_a_choice(world):
    with Session(engine) as session:
        _buy(session, world["customer_id"], world["listings"]["familiar"])

        profile = feed.taste_profile(session, world["customer_id"])
        assert profile.brands["Botanica"] == 1
        assert profile.strains["Wedding Cake"] == 1


def test_recommendations_stay_within_the_stores_asked_for(world):
    with Session(engine) as session:
        _buy(session, world["customer_id"], world["listings"]["familiar"], ItemFeedback.like)

        rail = feed.recommended(session, [world["also_mine"]], world["customer_id"], limit=8)
        assert all(item.listing.dispensary_id == world["also_mine"] for item in rail)


# ---------------------------
# Seeding defaults
# ---------------------------

def test_the_seed_gives_a_store_a_starting_set(world):
    from scripts.seed_featured import pick_for

    with Session(engine) as session:
        # Only presentable rows are eligible, so give a few of them a photo.
        for name in ("bargain", "exclusive", "arrival"):
            listing = session.get(Listing, world["listings"][name])
            listing.image_url = "https://example.test/x.jpg"
            session.add(listing)
        session.commit()

        picks = pick_for(session, world["mine"], per_store=4)
        assert {p.strain for p in picks} <= {"Blue Dream", "House Special", "Fresh Drop"}
        assert all(p.image_url and p.price_cents for p in picks)


def test_the_seed_spreads_across_categories_before_doubling_up(world):
    from scripts.seed_featured import pick_for

    with Session(engine) as session:
        for name, category in (("bargain", "flower"), ("exclusive", "flower"), ("arrival", "edible")):
            listing = session.get(Listing, world["listings"][name])
            listing.image_url = "https://example.test/x.jpg"
            listing.scraped_category = category
            session.add(listing)
        session.commit()

        picks = pick_for(session, world["mine"], per_store=2)
        assert {p.scraped_category for p in picks} == {"flower", "edible"}
