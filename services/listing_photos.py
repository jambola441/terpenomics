"""The photo a listing shows.

A store's photo of a product is whatever its point-of-sale system holds, so the
same product looked different from store to store: 2.5 photos per matched product
on 2026-10-09, some of them dead links. A brand's own site has one photo per
product and size, and a storefront catalog keeps it (brand_catalog_entries.
image_url, read by scripts/storefront.py).

A listing shows the catalog's photo when its match to the entry is trusted
(models.TRUSTED_MATCH_METHODS: the matches whose identity the import already
takes) and the entry has one. Otherwise, and for every listing of a brand without
a storefront catalog, it shows the store's.

    photo = listing_photos(session, listings)
    ... "image_url": photo(listing) ...

One query per response, whatever the number of listings. Anything with the
listing's catalog_entry_id, catalog_match_method and image_url works: a Listing,
or a row that selected those columns.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional
from uuid import UUID

from sqlmodel import Session, select

from models import TRUSTED_MATCH_METHODS, BrandCatalogEntry

# Postgres takes far more, but a few thousand ids a statement keeps each one small.
_CHUNK = 2000


def _trusted_entry(listing: Any) -> Optional[UUID]:
    entry_id = getattr(listing, "catalog_entry_id", None)
    if entry_id and getattr(listing, "catalog_match_method", None) in TRUSTED_MATCH_METHODS:
        return entry_id
    return None


def listing_photos(session: Session, listings: Iterable[Any]) -> Callable[[Any], Optional[str]]:
    """photo(listing): the catalog's photo for a trusted match that has one, else the
    store's. `listings` is every listing the caller will ask about."""
    entry_ids = list({e for e in (_trusted_entry(l) for l in listings) if e})
    by_entry: dict[UUID, str] = {}
    for i in range(0, len(entry_ids), _CHUNK):
        rows = session.exec(
            select(BrandCatalogEntry.id, BrandCatalogEntry.image_url)
            .where(BrandCatalogEntry.id.in_(entry_ids[i:i + _CHUNK]))
            .where(BrandCatalogEntry.image_url.is_not(None))
        ).all()
        by_entry.update({entry_id: url for entry_id, url in rows if url})

    def photo(listing: Any) -> Optional[str]:
        entry_id = _trusted_entry(listing)
        return (by_entry.get(entry_id) if entry_id else None) or listing.image_url

    return photo
