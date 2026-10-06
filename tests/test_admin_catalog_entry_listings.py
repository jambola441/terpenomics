"""The listings under a catalog entry, as the admin catalog page's accordion shows them.

An entry's listing_count says how many listings resolve to it; the accordion shows
which: the store, what the store calls the product, the size its page groups on, and
how the match was made.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from auth import SupabaseAuthUser
from database import engine
from models import BrandCatalog, BrandCatalogEntry, Dispensary, Listing
from routes.admin import router as admin_router
from routes.admin.auth import require_admin


@pytest.fixture
def catalog():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for model in (Listing, BrandCatalogEntry, BrandCatalog, Dispensary):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
        camino = BrandCatalog(brand_slug="camino", brand_name="Camino", source_method="listings_bootstrap")
        other = BrandCatalog(brand_slug="wyld", brand_name="Wyld", source_method="listings_bootstrap")
        session.add_all([camino, other])
        session.commit()
        yuzu = BrandCatalogEntry(catalog_id=camino.id, name="Balance Yuzu Lemon", variant="20pk 100mg")
        pom = BrandCatalogEntry(catalog_id=camino.id, name="Pomegranate", variant="20pk 100mg")
        stores = [Dispensary(name=n, slug=n.lower()) for n in ("Court", "Atlantic")]
        session.add_all([yuzu, pom, *stores])
        session.commit()
        common = dict(scraped_brand="Camino", scraped_category="edible", in_stock=True)
        session.add_all([
            Listing(dispensary_id=stores[0].id, scraped_name="Camino Yuzu Lemon 20pk", variant="100mg",
                    price_cents=2200, catalog_entry_id=yuzu.id, catalog_match_method="exact",
                    catalog_match_confidence=1.0, **common),
            Listing(dispensary_id=stores[1].id, scraped_name="Balance | Yuzu Lemon | 20pk", variant="50mg",
                    size="100mg", price_cents=1800, catalog_entry_id=yuzu.id, catalog_match_method="jev",
                    catalog_match_confidence=0.97, **common),
            Listing(dispensary_id=stores[0].id, scraped_name="Yuzu Lemon (old)", variant="100mg",
                    is_active=False, catalog_entry_id=yuzu.id, catalog_match_method="exact", **common),
            Listing(dispensary_id=stores[1].id, scraped_name="Camino Pomegranate", variant="100mg",
                    catalog_entry_id=pom.id, catalog_match_method="exact", **common),
        ])
        session.commit()
        return {"catalog": str(camino.id), "other": str(other.id), "yuzu": str(yuzu.id)}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[require_admin] = lambda: SupabaseAuthUser(
        user_id="admin", email=None, phone=None, role="admin", raw_claims={},
    )
    return TestClient(app)


def test_an_entrys_listings_active_first_with_store_size_and_match(client, catalog):
    res = client.get(f"/admin/brand-catalogs/{catalog['catalog']}/entries/{catalog['yuzu']}/listings")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 3                                   # inactive counted, as listing_count does
    assert [(row["dispensary"]["name"], row["is_active"]) for row in body["listings"]] == [
        ("Atlantic", True), ("Court", True), ("Court", False)]
    typo = body["listings"][0]
    assert (typo["variant"], typo["size"]) == ("50mg", "100mg")   # the store's typo, the page's size
    assert (typo["match_method"], typo["match_confidence"]) == ("jev", pytest.approx(0.97))
    assert body["listings"][1]["size"] == "100mg"                 # no size stored: reads as the variant


def test_an_entry_from_another_catalog_is_not_served(client, catalog):
    res = client.get(f"/admin/brand-catalogs/{catalog['other']}/entries/{catalog['yuzu']}/listings")
    assert res.status_code == 404
