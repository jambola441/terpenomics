import os
import tempfile

import pytest

# Point the app at a throwaway SQLite file before anything imports database.py,
# which builds its engine at import time.
_TEST_DB = os.path.join(tempfile.gettempdir(), "terpenomics_test.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)

# Assigned, not setdefault: these must win over whatever the surrounding
# environment already has. A real DATABASE_URL in the environment (Render, a
# shell that sourced .env, CI) would otherwise silently point the whole suite
# at production, and the Supabase keys at a live project.
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-key"
# With the keys above, catalog_reading would read its brand examples over the network
# (READING_EXAMPLES=auto); tests read the checked-in file unless they say otherwise.
os.environ["READING_EXAMPLES"] = "file"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: makes real HTTP requests to dispensary APIs")


@pytest.fixture(autouse=True)
def _fresh_response_cache():
    """Catalogue answers are cached in-process (services/response_cache.py);
    each test builds its own data, so each starts with nothing cached."""
    from services import response_cache

    response_cache.clear()
    yield
    response_cache.clear()


# ---------------------------------------------------------------------------
# Shop listings: customer surfaces show only trusted listings and read the product's
# identity from the matched catalog entry (services/shop_listings.py). Most API tests
# describe a listing by its own columns, so a listing saved with no match at all
# (catalog_entry_id and catalog_match_method both unset) is given an entry that
# mirrors those columns and an 'attributes' match — as if the import had trusted it.
# A test about untrusted listings sets catalog_match_method itself and is left alone.
# Later edits to a mirrored listing's identity follow it onto its entry.
# ---------------------------------------------------------------------------

_MIRRORED: dict = {}      # listing id -> entry id


def _mirror(session, listing):
    from models import BrandCatalog, BrandCatalogEntry
    from sqlmodel import select
    catalog = session.exec(select(BrandCatalog).where(BrandCatalog.brand_slug == "__test_shop__")).first() \
        or next((o for o in session.new if isinstance(o, BrandCatalog)
                 and o.brand_slug == "__test_shop__"), None)
    if catalog is None:
        catalog = BrandCatalog(brand_slug="__test_shop__", brand_name="test", source_method="test")
        session.add(catalog)
    entry = BrandCatalogEntry(catalog_id=catalog.id, name=listing.scraped_name or "x")
    session.add(entry)
    return entry


def _copy(entry, listing):
    entry.category, entry.subtype = listing.scraped_category, listing.subtype
    entry.product_line, entry.strain = listing.product_line, listing.strain
    entry.variant = listing.size if listing.size is not None else listing.variant


@pytest.fixture(autouse=True)
def _trusted_by_default():
    from sqlalchemy import event
    from sqlalchemy.orm import Session as OrmSession
    from models import BrandCatalogEntry, Listing

    def before_flush(session, ctx, instances):
        for obj in list(session.new):
            if isinstance(obj, Listing) and obj.catalog_entry_id is None and obj.catalog_match_method is None:
                entry = _mirror(session, obj)
                _copy(entry, obj)
                obj.catalog_entry_id, obj.catalog_match_method = entry.id, "attributes"
                _MIRRORED[obj.id] = entry.id
        for obj in list(session.dirty):
            if isinstance(obj, Listing) and obj.id in _MIRRORED and _MIRRORED[obj.id] == obj.catalog_entry_id:
                entry = session.get(BrandCatalogEntry, obj.catalog_entry_id)
                if entry is not None:
                    _copy(entry, obj)

    event.listen(OrmSession, "before_flush", before_flush)
    yield
    event.remove(OrmSession, "before_flush", before_flush)
    _MIRRORED.clear()
