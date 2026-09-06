# models.py
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Index, LargeBinary, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, REAL
from sqlmodel import SQLModel, Field, Relationship


# ---------------------------
# Mixins / helpers
# ---------------------------

def utcnow() -> datetime:
    return datetime.utcnow()


class TimestampMixin:
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


# ---------------------------
# Customers
# ---------------------------

class CustomerBase(SQLModel):
    name: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=32, index=True, sa_column_kwargs={"unique": True})
    email: Optional[str] = Field(default=None, max_length=320, index=True, sa_column_kwargs={"unique": True})
    auth_user_id: Optional[UUID] = Field(default=None, index=True, sa_column_kwargs={"unique": True})
    marketing_opt_in: bool = Field(default=False, nullable=False)
    last_visit_at: Optional[datetime] = Field(default=None)


class Customer(CustomerBase, TimestampMixin, table=True):
    __tablename__ = "customers"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    purchases: list["Purchase"] = Relationship(back_populates="customer")


# ---------------------------
# Terpenes + Cannabinoids
# ---------------------------

class Terpene(SQLModel, TimestampMixin, table=True):
    __tablename__ = "terpenes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=120, index=True, sa_column_kwargs={"unique": True})
    description: Optional[str] = Field(default=None, max_length=1000)

    listing_links: list["ListingTerpene"] = Relationship(back_populates="terpene")


class CannabinoidFamily(str, Enum):
    thc = "thc"
    cbd = "cbd"
    cbg = "cbg"
    cbc = "cbc"
    other = "other"


class Cannabinoid(SQLModel, TimestampMixin, table=True):
    __tablename__ = "cannabinoids"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=120, index=True, sa_column_kwargs={"unique": True})
    family: CannabinoidFamily = Field(nullable=False, index=True)
    description: Optional[str] = Field(default=None, max_length=1000)

    listing_links: list["ListingCannabinoid"] = Relationship(back_populates="cannabinoid")


# ---------------------------
# Lab Reports (COA ingestion)
# ---------------------------

class LabReportStatus(str, Enum):
    pending   = "pending"
    extracted = "extracted"
    applied   = "applied"
    failed    = "failed"


class LabReport(SQLModel, TimestampMixin, table=True):
    __tablename__ = "lab_reports"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    listing_id: Optional[UUID] = Field(default=None, foreign_key="listings.id", index=True)

    lab_name:               Optional[str]   = Field(default=None, max_length=300)
    lab_license:            Optional[str]   = Field(default=None, max_length=100)
    test_date:              Optional[str]   = Field(default=None, max_length=50)
    batch_id:               Optional[str]   = Field(default=None, max_length=200)
    product_name_on_report: Optional[str]   = Field(default=None, max_length=300)
    total_terpenes:         Optional[float] = Field(default=None, ge=0.0, le=100.0)
    pass_fail:              Optional[str]   = Field(default=None, max_length=20)
    confidence:             Optional[int]   = Field(default=None, ge=1, le=5)

    pdf_bytes:              Optional[bytes] = Field(default=None, sa_column=Column("pdf_bytes", LargeBinary, nullable=True))
    raw_terpenes_json:      Optional[str]   = Field(default=None)
    raw_cannabinoids_json:  Optional[str]   = Field(default=None)

    status:        LabReportStatus = Field(default=LabReportStatus.pending)
    error_message: Optional[str]   = Field(default=None, max_length=1000)


# ---------------------------
# Brand catalogs
# ---------------------------

def utcnow_tz() -> datetime:
    """Timezone-aware UTC.

    The brand-catalog tables are `timestamptz`, unlike the older tables here, which
    are naive `timestamp`. A naive default would be read in the session timezone
    rather than as UTC, so these three tables get their own clock.
    """
    return datetime.now(timezone.utc)


class BrandCatalog(SQLModel, table=True):
    """A brand's real product list, as published by the brand itself.

    Enrichment extracts fields from a listing name with a model, so every quality
    number in this repo is computed from the same output it judges. A catalog is the
    first external referent: the products a brand says it makes, scraped from its own
    storefront (see evals/enrich/CATALOG.md).

    Postgres is the system of record. `data/catalogs/<brand_slug>.json` is a
    *generated export* of this table, and it — not this table — is what
    scripts/catalog_enricher.py and scripts/brand_prompt.py read. An edit made here
    is therefore invisible to enrichment until the export is regenerated;
    routes/admin/brand_catalogs.py owns that. (The export is a convenience for runs
    with no database to hand, not a boundary — enrich.py opens its own connection
    for the brand-examples nudge, best-effort. The catalog read path simply is not
    wired that way today.)

    These tables were created by scripts/migrate_add_brand_catalogs.py. This class is
    a mapping onto live tables, not a definition of them: change the migration first.
    """

    __tablename__ = "brand_catalogs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    brand_slug:    str           = Field(nullable=False, sa_type=Text, sa_column_kwargs={"unique": True})
    brand_name:    str           = Field(nullable=False, sa_type=Text)
    source_url:    Optional[str] = Field(default=None, sa_type=Text)
    # Which acquisition tier answered: shopify_products_json | ld_json |
    # rendered_page | manual. Recorded per catalog so coverage can be reported by
    # provenance rather than as one undifferentiated number.
    source_method: str           = Field(nullable=False, sa_type=Text)

    fetched_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column("fetched_at", DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow_tz,
        sa_column=Column("created_at", DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow_tz,
        sa_column=Column("updated_at", DateTime(timezone=True), nullable=False),
    )

    entries: list["BrandCatalogEntry"] = Relationship(back_populates="catalog")


class BrandCatalogEntry(SQLModel, table=True):
    """One (product, variant) pair the brand ships.

    The grain is the variant, not the product family, because that is the grain our
    listings are at — a listing is for a specific size, not for a product.

    **Never deleted.** `listings.catalog_entry_id` is a foreign key to this row, so a
    delete would dangle it and destroy the record of what was on the menu. A product
    that drops off the source gets `is_active = False` and keeps its `last_seen_at`:
    staleness is a state, not a deletion — the same rule the verification lapse model
    uses.

    `first_seen_at` and the `verified_*` columns are never rewritten by an update,
    whether that update comes from a re-fetch (scripts/brand_catalog.py `push`) or
    from the admin UI. A human sign-off, and the record of when we first saw a
    product, have to survive an edit.
    """

    __tablename__ = "brand_catalog_entries"
    __table_args__ = (
        # The source's own variant id is the upsert key, so a re-fetch updates in
        # place instead of duplicating.
        UniqueConstraint(
            "catalog_id", "external_id",
            name="brand_catalog_entries_catalog_id_external_id_key",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    catalog_id: UUID = Field(foreign_key="brand_catalogs.id", nullable=False)

    external_id:  Optional[str] = Field(default=None, sa_type=Text)
    name:         str           = Field(nullable=False, sa_type=Text)
    product_line: Optional[str] = Field(default=None, sa_type=Text)
    category:     Optional[str] = Field(default=None, sa_type=Text)
    subtype:      Optional[str] = Field(default=None, sa_type=Text)
    strain:       Optional[str] = Field(default=None, sa_type=Text)
    variant:      Optional[str] = Field(default=None, sa_type=Text)

    attributes: Optional[dict] = Field(
        default=None, sa_column=Column("attributes", JSONB, nullable=True)
    )
    # Normalised strings a listing name is matched against, in addition to `name`.
    match_terms: Optional[list[str]] = Field(
        default=None, sa_column=Column("match_terms", ARRAY(Text), nullable=True)
    )

    is_active: bool = Field(default=True, nullable=False)

    first_seen_at: datetime = Field(
        default_factory=utcnow_tz,
        sa_column=Column("first_seen_at", DateTime(timezone=True), nullable=False),
    )
    last_seen_at: datetime = Field(
        default_factory=utcnow_tz,
        sa_column=Column("last_seen_at", DateTime(timezone=True), nullable=False),
    )

    # Per-field human claims, same shape as listings.verified_fields — see
    # scripts/verification.py.
    verified_fields: Optional[dict] = Field(
        default=None, sa_column=Column("verified_fields", JSONB, nullable=True)
    )
    verified_by: Optional[str] = Field(default=None, sa_type=Text)
    verified_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column("verified_at", DateTime(timezone=True), nullable=True),
    )

    catalog: "BrandCatalog" = Relationship(back_populates="entries")


# ---------------------------
# Dispensaries + Listings
# ---------------------------

class PosType(str, Enum):
    none      = "none"
    alleaves  = "alleaves"
    leaflogix = "leaflogix"


class DispensaryBase(SQLModel):
    name: str = Field(max_length=200)
    slug: str = Field(max_length=100, index=True, sa_column_kwargs={"unique": True})
    website_url: Optional[str] = Field(default=None, max_length=500)
    location: Optional[str] = Field(default=None, max_length=200)
    address: Optional[str] = Field(default=None, max_length=500)
    lat: Optional[float] = Field(default=None)
    lng: Optional[float] = Field(default=None)
    is_active: bool = Field(default=True, nullable=False)
    pos_type: PosType = Field(default=PosType.none, nullable=False)
    pos_tenant_id: Optional[str] = Field(default=None, max_length=200)
    accepts_pickup: bool = Field(default=False, nullable=False)
    logo_url: Optional[str] = Field(default=None, max_length=1000)
    banner_url: Optional[str] = Field(default=None, max_length=1000)


class Dispensary(DispensaryBase, TimestampMixin, table=True):
    __tablename__ = "dispensaries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    listings: list["Listing"] = Relationship(back_populates="dispensary")


class ListingBase(SQLModel):
    dispensary_id: UUID = Field(foreign_key="dispensaries.id", index=True, nullable=False)
    sku:              Optional[str] = Field(default=None, max_length=200)
    batch_id:         Optional[str] = Field(default=None, max_length=200)
    price_cents:      Optional[int] = Field(default=None, ge=0)
    variant:          Optional[str] = Field(default=None, max_length=100)
    url:              Optional[str] = Field(default=None, max_length=1000)
    image_url:        Optional[str] = Field(default=None, max_length=1000)
    in_stock:         bool          = Field(default=True, nullable=False)
    is_active:        bool          = Field(default=True, nullable=False)
    scraped_at:       Optional[datetime] = Field(default=None)
    last_seen_at:     Optional[datetime] = Field(default=None)
    # Scraped identity fields
    scraped_name:     Optional[str] = Field(default=None, max_length=300)
    scraped_brand:    Optional[str] = Field(default=None, max_length=200)
    scraped_category: Optional[str] = Field(default=None, max_length=100)
    subtype:          Optional[str] = Field(default=None, max_length=100)
    strain:           Optional[str] = Field(default=None, max_length=200)
    # Enriched content
    classification:   Optional[str]   = Field(default=None, max_length=50)
    description:      Optional[str]   = Field(default=None, max_length=5000)
    product_line:     Optional[str]   = Field(default=None, max_length=200)


class Listing(ListingBase, TimestampMixin, table=True):
    __tablename__ = "listings"
    __table_args__ = (
        # One row per (dispensary, sku, variant): platforms like Dutchie and Tymber
        # reuse one SKU across weight/price tiers, so the variant is part of identity.
        # COALESCE folds NULL variants into '' — otherwise Postgres treats NULLs as
        # distinct and the upsert could never match a variant-less row.
        Index(
            "listings_dispensary_sku_variant_unique",
            "dispensary_id",
            "sku",
            text("COALESCE(variant, '')"),
            unique=True,
            postgresql_where=text("sku IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Resolution to the brand's own catalog, written by scripts/catalog_match.py.
    # `method` records which tier fired (exact | substring | token | model) so a
    # match can be judged by how it was made rather than taken on trust. All three
    # are NULL when the listing did not resolve — "no match" is a first-class
    # outcome, and the listing falls through to extraction.
    catalog_entry_id: Optional[UUID] = Field(
        default=None, foreign_key="brand_catalog_entries.id"
    )
    catalog_match_confidence: Optional[float] = Field(
        default=None,
        sa_column=Column("catalog_match_confidence", REAL, nullable=True),
    )
    catalog_match_method: Optional[str] = Field(default=None, sa_type=Text)

    dispensary:     Dispensary              = Relationship(back_populates="listings")
    purchase_items: list["PurchaseItem"]    = Relationship(back_populates="listing")
    terpene_links:  list["ListingTerpene"]  = Relationship(back_populates="listing")
    cannab_links:   list["ListingCannabinoid"] = Relationship(back_populates="listing")


class ListingTerpene(SQLModel, table=True):
    __tablename__ = "listing_terpenes"

    listing_id: UUID = Field(foreign_key="listings.id", primary_key=True)
    terpene_id: UUID = Field(foreign_key="terpenes.id", primary_key=True)
    percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    listing: Listing = Relationship(back_populates="terpene_links")
    terpene: Terpene = Relationship(back_populates="listing_links")


class ListingCannabinoid(SQLModel, table=True):
    __tablename__ = "listing_cannabinoids"

    listing_id:    UUID = Field(foreign_key="listings.id", primary_key=True)
    cannabinoid_id: UUID = Field(foreign_key="cannabinoids.id", primary_key=True)
    percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    listing:    Listing    = Relationship(back_populates="cannab_links")
    cannabinoid: Cannabinoid = Relationship(back_populates="listing_links")


# ---------------------------
# Purchases
# ---------------------------

class PurchaseSource(str, Enum):
    manual     = "manual"
    pos_import = "pos_import"
    pos_api    = "pos_api"


class Purchase(SQLModel, TimestampMixin, table=True):
    __tablename__ = "purchases"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    customer_id:         UUID              = Field(foreign_key="customers.id", index=True, nullable=False)
    purchased_at:        datetime          = Field(default_factory=utcnow, nullable=False)
    total_amount_cents:  int               = Field(default=0, ge=0, nullable=False)
    source:              PurchaseSource    = Field(default=PurchaseSource.manual, nullable=False)
    notes:               Optional[str]     = Field(default=None, max_length=2000)
    external_id:         Optional[str]     = Field(default=None, max_length=200, index=True)

    customer: Customer          = Relationship(back_populates="purchases")
    items:    list["PurchaseItem"] = Relationship(back_populates="purchase")


class ItemFeedback(str, Enum):
    like    = "like"
    dislike = "dislike"
    neutral = "neutral"


class PurchaseItem(SQLModel, table=True):
    __tablename__ = "purchase_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    purchase_id:       UUID           = Field(foreign_key="purchases.id", index=True, nullable=False)
    listing_id:        Optional[UUID] = Field(default=None, foreign_key="listings.id", index=True)
    quantity:          int            = Field(default=1, ge=1, nullable=False)
    line_amount_cents: Optional[int]  = Field(default=None, ge=0)
    feedback:          Optional[ItemFeedback] = Field(default=None, index=True)
    feedback_at:       Optional[datetime]     = Field(default=None)

    purchase: Purchase         = Relationship(back_populates="items")
    listing:  Optional[Listing] = Relationship(back_populates="purchase_items")


# ---------------------------
# Pickup orders
# ---------------------------

class OrderStatus(str, Enum):
    submitted = "submitted"   # customer placed it; the store has not acted yet
    ready     = "ready"       # staff set it aside, waiting at the counter
    completed = "completed"   # picked up and paid for in store
    cancelled = "cancelled"


# Terminal states never transition again; the API enforces this table.
ORDER_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.submitted: {OrderStatus.ready, OrderStatus.cancelled},
    OrderStatus.ready:     {OrderStatus.completed, OrderStatus.cancelled},
    OrderStatus.completed: set(),
    OrderStatus.cancelled: set(),
}


class Order(SQLModel, TimestampMixin, table=True):
    """A pickup order placed through the customer portal.

    Payment is not handled here and never will be by this table: the customer
    pays at the counter. `total_amount_cents` is therefore the quoted total at
    submission time, not a charge -- it exists so the customer and the store are
    looking at the same number, and so a later price change on the listing does
    not silently rewrite what was agreed.

    Distinct from `Purchase`, which records a completed transaction for the
    recommendation engine. An order only becomes purchase-like once it is picked
    up, and until then it must not feed recommendations.
    """

    __tablename__ = "orders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    customer_id:   UUID = Field(foreign_key="customers.id", index=True, nullable=False)
    dispensary_id: UUID = Field(foreign_key="dispensaries.id", index=True, nullable=False)

    status: OrderStatus = Field(default=OrderStatus.submitted, index=True, nullable=False)

    # Shown to the customer and read back at the counter. Short enough to say out
    # loud; scoped per order, not globally meaningful.
    pickup_code: str = Field(max_length=12, index=True, nullable=False)

    total_amount_cents: int = Field(default=0, ge=0, nullable=False)
    note:               Optional[str] = Field(default=None, max_length=500)

    submitted_at: datetime           = Field(default_factory=utcnow, index=True, nullable=False)
    ready_at:     Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    cancelled_at: Optional[datetime] = Field(default=None)

    customer:   "Customer"          = Relationship()
    dispensary: "Dispensary"        = Relationship()
    items:      list["OrderItem"]   = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class OrderItem(SQLModel, table=True):
    """One line of an order, with the product details copied in.

    Listings are re-scraped continuously -- prices move, rows go inactive, SKUs
    get rewritten. Rendering an order by joining live listing rows would let a
    scrape silently change what a customer sees they ordered, so the name, brand,
    variant and unit price are snapshotted at submission. `listing_id` stays for
    lineage but is nullable and is never the source of display data.
    """

    __tablename__ = "order_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    order_id:   UUID           = Field(foreign_key="orders.id", index=True, nullable=False)
    listing_id: Optional[UUID] = Field(default=None, foreign_key="listings.id", index=True)

    quantity:          int = Field(default=1, ge=1, nullable=False)
    unit_price_cents:  Optional[int] = Field(default=None, ge=0)
    line_amount_cents: int = Field(default=0, ge=0, nullable=False)

    # Snapshot of the listing at submission time.
    name:      str           = Field(max_length=300, nullable=False)
    brand:     Optional[str] = Field(default=None, max_length=200)
    variant:   Optional[str] = Field(default=None, max_length=100)
    image_url: Optional[str] = Field(default=None, max_length=1000)

    order: Order = Relationship(back_populates="items")


# ---------------------------
# Curation
# ---------------------------

class FeaturedListing(SQLModel, table=True):
    """A listing a store (or an admin) wants shown first.

    Curated rather than derived: "featured" is an editorial choice about what a
    store wants to push this week, which no amount of scraped data can infer.
    The other feed rails are computed -- new arrivals from `created_at`, deals
    from prices elsewhere, recommendations from the shopper -- and this is the
    one a person fills in.

    Keyed on the listing rather than the product because a store features a
    specific thing on its own shelf at a specific size. `dispensary_id` is
    denormalized from the listing so the feed can read a store's picks without
    joining, and so a removed listing cannot silently orphan the row.
    """

    __tablename__ = "featured_listings"

    dispensary_id: UUID = Field(foreign_key="dispensaries.id", primary_key=True)
    listing_id:    UUID = Field(foreign_key="listings.id", primary_key=True)

    # Ascending: 0 shows first. Gaps are fine -- nothing renumbers on removal.
    position: int = Field(default=0, nullable=False)

    # Who put it there, for the admin surface that will edit these.
    note:       Optional[str] = Field(default=None, max_length=200)
    created_at: datetime      = Field(default_factory=utcnow, nullable=False)


# ---------------------------
# Preferred dispensaries
# ---------------------------

class PreferredDispensary(SQLModel, table=True):
    """A dispensary the customer wants their home feed built from.

    A link table rather than a column on `customers` because the home feed is a
    multi-store view: a shopper follows the two or three stores they actually
    drive to, and the feed reads that set directly. `created_at` is the feed's
    section order -- first followed, first shown -- so the order is stable
    without a separate rank column to keep contiguous on removal.
    """

    __tablename__ = "customer_preferred_dispensaries"

    customer_id:   UUID = Field(foreign_key="customers.id", primary_key=True)
    dispensary_id: UUID = Field(foreign_key="dispensaries.id", primary_key=True)

    created_at: datetime = Field(default_factory=utcnow, nullable=False)


# ---------------------------
# Phone (SMS) login
# ---------------------------

class PhoneAuthIdentity(SQLModel, TimestampMixin, table=True):
    """Maps an E.164 number to its Supabase user.

    Our own source of truth for the mapping, so repeat logins never have to
    search Supabase's user list. See services/supabase_admin.py.
    """

    __tablename__ = "phone_auth_identities"

    phone:         str            = Field(primary_key=True, max_length=32)
    auth_user_id:  UUID           = Field(index=True, nullable=False)
    last_login_at: Optional[datetime] = Field(default=None)


class PhoneAuthChallenge(SQLModel, table=True):
    """One outstanding SMS code request.

    The code itself lives with the SMS provider and never touches this database;
    provider_ref is the handle we exchange for a verdict.
    """

    __tablename__ = "phone_auth_challenges"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    phone:        str  = Field(index=True, max_length=32, nullable=False)
    provider:     str  = Field(max_length=32, nullable=False)
    provider_ref: str  = Field(max_length=128, nullable=False)

    created_at:  datetime           = Field(default_factory=utcnow, index=True, nullable=False)
    expires_at:  datetime           = Field(nullable=False)
    attempts:    int                = Field(default=0, nullable=False)
    consumed_at: Optional[datetime] = Field(default=None)
    request_ip:  Optional[str]      = Field(default=None, max_length=64, index=True)
