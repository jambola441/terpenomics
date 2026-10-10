"""The catalog review queue (routes/admin/review.py).

Listings the matcher left for review come one at a time, the brand with the most
left first, like products in a row; a person's call is recorded and nothing else
changes; undo puts the last card back.
"""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser
from database import engine
from models import BrandCatalog, BrandCatalogEntry, Dispensary, Listing, ReviewDecision, utcnow
from routes.admin import router as admin_router
from routes.admin.auth import require_admin


@pytest.fixture
def queue():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (ReviewDecision, Listing, BrandCatalogEntry, BrandCatalog, Dispensary):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
        camino = BrandCatalog(brand_slug="camino", brand_name="Camino", source_method="listings_bootstrap")
        wyld = BrandCatalog(brand_slug="wyld", brand_name="Wyld", source_method="listings_bootstrap")
        session.add_all([camino, wyld])
        session.commit()
        E = lambda cat, name, **kw: BrandCatalogEntry(catalog_id=cat.id, name=name, category="edible", **kw)
        entries = {
            "yuzu20": E(camino, "Balance Yuzu Lemon", strain="Yuzu Lemon", product_line="Balance", variant="20pk 100mg"),
            "yuzu10": E(camino, "Balance Yuzu Lemon", strain="Yuzu Lemon", product_line="Balance", variant="10pk 50mg"),
            "yuzu_sleep": E(camino, "Sleep Yuzu Lemon", strain="Yuzu Lemon", product_line="Sleep", variant="20pk 100mg"),
            "yuzu_old": E(camino, "Yuzu Lemon (retired)", strain="Yuzu Lemon", variant="20pk", is_active=False),
            "pom": E(camino, "Pomegranate", strain="Pomegranate", variant="20pk 100mg"),
            "lemon_mint": E(camino, "Lemon Mint", strain="Lemon Mint", variant="20pk 100mg"),
            "lemon_vape": BrandCatalogEntry(catalog_id=camino.id, name="Lemon Haze", strain="Lemon Haze",
                                            category="vape", variant="1g"),
            "raspberry": E(wyld, "Raspberry", strain="Raspberry", variant="10pk"),
        }
        store = Dispensary(name="Court", slug="court")
        session.add_all([*entries.values(), store])
        session.commit()

        def L(name, brand, method, entry=None, **kw):
            return Listing(dispensary_id=store.id, scraped_name=name, scraped_brand=brand,
                           scraped_category="edible", catalog_match_method=method,
                           catalog_entry_id=entry.id if entry else None, **kw)

        listings = {
            # Camino: three in the queue (the bigger queue), one matched, one inactive.
            "c_yuzu": L("Camino Yuzu Lemon 40pk", "Camino", "review_near", product_line="Balance", strain="Yuzu Lemon",
                        variant="40pk", price_cents=3000, description="x" * 900,
                        reading={"category": "edible", "product_line": "Balance", "strain": "Yuzu Lemon",
                                 "size": None, "by": "catalog", "p": {"strain": 0.99, "size": 0.4}}),
            "c_alpha": L("Camino Apple 20pk", "camino", "review_missing", product_line="Balance", strain="Apple"),
            "c_unsure": L("Camino Lemon Sour Gummies", "Camino", "review_unsure", entry=entries["yuzu20"],
                          product_line="Sleep", strain="Lemon Sour",
                          reading={"category": "edible", "strain": "Yuzu Lemon", "by": "catalog",
                                   "p": {"strain": 0.7, "size": 0.95}}),
            "c_matched": L("Camino Pomegranate", "Camino", "exact", entry=entries["pom"]),
            "c_inactive": L("Camino Old", "Camino", "review_missing", is_active=False),
            # Wyld: one in the queue.
            "w_rasp": L("Wyld Raspberry 5pk", "Wyld", "review_near", strain="Raspberry"),
        }
        session.add_all(listings.values())
        session.commit()
        return {"entries": {k: str(v.id) for k, v in entries.items()},
                "listings": {k: str(v.id) for k, v in listings.items()}}


def _client(user_id="admin"):
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
        user_id=user_id, email=f"{user_id}@example.com", phone=None, role="admin", raw_claims={},
    )
    return TestClient(app)


@pytest.fixture
def client():
    return _client()


def _decide(client, listing_id, decision="skip", **kw):
    return client.post("/admin/review/decisions", json={"listing_id": listing_id, "decision": decision, **kw})


def test_cards_come_biggest_brand_first_then_by_product(client, queue):
    L = queue["listings"]
    res = client.get("/admin/review/next")
    assert res.status_code == 200, res.text
    card = res.json()
    # Camino (3 left) before Wyld (1); within Camino by line then strain: Balance/Apple,
    # Balance/Yuzu Lemon, Sleep/Lemon Sour. Brand spelled "camino" is the same queue.
    assert card["listing"]["id"] == L["c_alpha"]
    assert (card["brand"], card["listing"]["brand"]) == ("Camino", "camino")
    seen = []
    for _ in range(4):
        card = client.get("/admin/review/next").json()
        seen.append(card["listing"]["id"])
        assert _decide(client, card["listing"]["id"]).status_code == 200
    assert seen == [L["c_alpha"], L["c_yuzu"], L["c_unsure"], L["w_rasp"]]
    # Decided (skip included), matched and inactive listings never come.
    assert client.get("/admin/review/next").status_code == 204


def test_filters_and_exclude_for_prefetch(client, queue):
    L = queue["listings"]
    assert client.get("/admin/review/next", params={"brand": "WYLD"}).json()["listing"]["id"] == L["w_rasp"]
    assert client.get("/admin/review/next", params={"reason": "review_unsure"}).json()["listing"]["id"] == L["c_unsure"]
    # The card after the one on screen.
    res = client.get("/admin/review/next", params={"exclude": L["c_alpha"]})
    assert res.json()["listing"]["id"] == L["c_yuzu"]
    # Excluding all of a brand's moves on to the next brand.
    res = client.get("/admin/review/next", params={"exclude": ",".join([L["c_alpha"], L["c_yuzu"], L["c_unsure"]])})
    assert res.json()["listing"]["id"] == L["w_rasp"]


def test_card_shows_listing_reading_and_trimmed_description(client, queue):
    card = client.get("/admin/review/next", params={"exclude": queue["listings"]["c_alpha"]}).json()
    assert card["reason"] == "review_near"
    assert card["listing"]["store"] == "Court"
    assert card["listing"]["size"] == "40pk"
    assert card["listing"]["price_cents"] == 3000
    assert len(card["listing"]["description"]) <= 601
    assert card["reading"]["strain"] == "Yuzu Lemon"
    assert card["reading"]["p"] == {"strain": 0.99, "size": 0.4}
    assert card["progress"]["brands"][0]["brand"] == "Camino"


def test_candidates_suggested_first_then_same_strain_then_shared_words(client, queue):
    E = queue["entries"]
    card = client.get("/admin/review/next", params={"reason": "review_unsure"}).json()
    ids = [c["id"] for c in card["candidates"]]
    # The suggestion, then the reading's strain (active only), the listing's own
    # line (Sleep) first, capped at four.
    assert card["candidates"][0]["suggested"]
    assert ids[:3] == [E["yuzu20"], E["yuzu_sleep"], E["yuzu10"]]
    assert len(ids) == 4
    assert E["yuzu_old"] not in ids
    # Fourth: an edible sharing a word with "Lemon Sour Gummies" — not the vape.
    assert ids[3] == E["lemon_mint"]


def test_candidates_never_cross_brands(client, queue):
    card = client.get("/admin/review/next", params={"brand": "Wyld"}).json()
    assert [c["id"] for c in card["candidates"]] == [queue["entries"]["raspberry"]]


def test_decision_validation(client, queue):
    L, E = queue["listings"], queue["entries"]
    assert _decide(client, L["c_yuzu"], "entry").status_code == 422                       # no entry
    assert _decide(client, L["c_yuzu"], "entry", entry_id=E["raspberry"]).status_code == 422  # other brand
    assert _decide(client, L["c_yuzu"], "none", entry_id=E["yuzu20"]).status_code == 422      # entry not wanted
    assert _decide(client, L["c_yuzu"], "maybe").status_code == 422
    assert _decide(client, L["c_matched"]).status_code == 409                              # not in the queue
    res = _decide(client, L["c_yuzu"], "entry", entry_id=E["yuzu20"], note=" 40pk missing ")
    assert res.status_code == 200, res.text
    assert _decide(client, L["c_yuzu"], "none").status_code == 409                          # already decided

    with Session(engine) as session:
        row = session.exec(select(ReviewDecision)).one()
        assert (row.decision, str(row.entry_id), row.reason, row.reviewer, row.note) == (
            "entry", E["yuzu20"], "review_near", "admin@example.com", "40pk missing")
        # Recorded only: the listing's match is untouched.
        listing = session.get(Listing, row.listing_id)
        assert (listing.catalog_entry_id, listing.catalog_match_method) == (None, "review_near")


def test_undo_deletes_my_last_decision_and_returns_its_card(client, queue):
    L = queue["listings"]
    assert client.post("/admin/review/undo").status_code == 404
    _decide(client, L["c_alpha"], "missing")
    _decide(client, L["c_yuzu"], "none")
    # Someone else's later decision is not mine to undo.
    _decide(_client("other"), L["w_rasp"])

    res = client.post("/admin/review/undo")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["listing_id"] == L["c_yuzu"]
    assert body["card"]["listing"]["id"] == L["c_yuzu"]
    assert client.get("/admin/review/next").json()["listing"]["id"] == L["c_yuzu"]
    with Session(engine) as session:
        assert sorted(str(r.listing_id) for r in session.exec(select(ReviewDecision)).all()) == sorted(
            [L["c_alpha"], L["w_rasp"]])


def test_progress_counts(client, queue):
    L = queue["listings"]
    _decide(client, L["c_alpha"], "missing")
    _decide(client, L["c_yuzu"])
    _decide(_client("other"), L["w_rasp"])
    with Session(engine) as session:   # an old decision of mine: not today, not this minute
        row = session.exec(select(ReviewDecision).where(ReviewDecision.decision == "skip",
                                                        ReviewDecision.reviewer == "admin@example.com")).one()
        row.created_at = utcnow() - timedelta(days=2)
        session.add(row)
        session.commit()

    body = client.get("/admin/review/progress").json()
    camino, wyld = body["brands"]
    assert (camino["brand"], camino["total"], camino["decided"], camino["remaining"]) == ("Camino", 3, 2, 1)
    assert camino["by_reason"]["review_missing"] == {"total": 1, "decided": 1}
    assert camino["by_reason"]["review_unsure"] == {"total": 1, "decided": 0}
    assert (wyld["brand"], wyld["remaining"]) == ("Wyld", 0)
    assert (body["totals"]["total"], body["totals"]["decided"], body["totals"]["remaining"]) == (4, 3, 1)
    assert body["me"] == {"today": 1, "last_10_min": 1}

    only = client.get("/admin/review/progress", params={"brand": "wyld"}).json()
    assert [b["brand"] for b in only["brands"]] == ["Wyld"]
    assert only["totals"]["total"] == 4
