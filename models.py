# models.py
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, LargeBinary, text
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
        Index(
            "listings_dispensary_sku_unique",
            "dispensary_id",
            "sku",
            unique=True,
            postgresql_where=text("sku IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

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
