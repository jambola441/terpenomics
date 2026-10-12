# services/shop_listings.py
"""The listings a shopper sees, and what they say about the product.

Owner, 2026-10-12: customer surfaces show only trusted listings — a catalog entry
matched by the attribute join or by a reviewer (SHOP_TRUSTED_METHODS) — and what a
listing IS (category, subtype, product line, strain, size) comes from that joined
brand_catalog_entries row, never from the listing's own columns. The listing still
says what the store says about selling it: price, stock, store, url, photo, its
scraped name.

`shop_listing()` is `Listing` mapped onto a subquery with that join and filter, its
identity columns replaced by the entry's under the listing's own column names, so a
customer route written against `Listing` reads the same attributes
(`l.scraped_category`, `l.product_line`, `l.product_size`...) and gets the entry's.
Each call is a fresh alias, so a query can self-join two (services.market). Rows it
returns are read-only views: a customer route never writes a listing.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from models import BrandCatalogEntry, Listing

# The match methods a shopper's listing has: the attribute join and a reviewer.
SHOP_TRUSTED_METHODS = ("attributes", "manual")


def _subquery(name: str):
    L = Listing.__table__
    E = BrandCatalogEntry.__table__
    from_entry = {
        "scraped_category": E.c.category,
        "subtype": E.c.subtype,
        "product_line": E.c.product_line,
        "strain": E.c.strain,
        # the entry's size; a catalog row without one falls back to the store's
        "size": func.coalesce(E.c.variant, L.c.variant),
    }
    cols = [from_entry.get(c.name, c).label(c.name) for c in L.c]
    return (
        select(*cols)
        .select_from(L.join(E, E.c.id == L.c.catalog_entry_id))
        .where(L.c.catalog_entry_id.isnot(None))
        .where(L.c.catalog_match_method.in_(SHOP_TRUSTED_METHODS))
        .subquery(name)
    )


_n = 0


def shop_listing():
    """A fresh alias of the shop's listings (see the module docstring)."""
    global _n
    _n += 1
    return aliased(Listing, _subquery(f"shop_listings_{_n}"), name=f"shop_listings_{_n}",
                   adapt_on_names=True)


def is_shop_listing(listing) -> bool:
    return bool(getattr(listing, "catalog_entry_id", None)) \
        and getattr(listing, "catalog_match_method", None) in SHOP_TRUSTED_METHODS
