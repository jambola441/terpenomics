# models.py
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

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

    # Postgres allows multiple NULLs under UNIQUE, which is what we want here.
    phone: Optional[str] = Field(default=None, max_length=32, index=True, sa_column_kwargs={"unique": True})
    email: Optional[str] = Field(default=None, max_length=320, index=True, sa_column_kwargs={"unique": True})

    # Supabase auth.users.id from JWT sub
    auth_user_id: Optional[UUID] = Field(default=None, index=True, sa_column_kwargs={"unique": True})

    marketing_opt_in: bool = Field(default=False, nullable=False)
    last_visit_at: Optional[datetime] = Field(default=None)


class Customer(CustomerBase, TimestampMixin, table=True):
    __tablename__ = "customers"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    purchases: list["Purchase"] = Relationship(back_populates="customer")


# ---------------------------
# Products + Terpenes
# ---------------------------

class ProductCategory(str, Enum):
    flower = "flower"
    cart = "cart"
    edible = "edible"
    concentrate = "concentrate"
    preroll = "preroll"
    tincture = "tincture"
    topical = "topical"
    merch = "merch"
    other = "other"


class ProductBase(SQLModel):
    name: str = Field(max_length=200, index=True)
    brand: Optional[str] = Field(default=None, max_length=200)
    category: ProductCategory = Field(default=ProductCategory.other, nullable=False)
    is_active: bool = Field(default=True, nullable=False)


class Product(ProductBase, TimestampMixin, table=True):
    __tablename__ = "products"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    purchase_items: list["PurchaseItem"] = Relationship(back_populates="product")
    terpene_links: list["ProductTerpene"] = Relationship(back_populates="product")


class Terpene(SQLModel, TimestampMixin, table=True):
    __tablename__ = "terpenes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=120, index=True, sa_column_kwargs={"unique": True})
    description: Optional[str] = Field(default=None, max_length=1000)

    product_links: list["ProductTerpene"] = Relationship(back_populates="terpene")


class ProductTerpene(SQLModel, table=True):
    """
    Join table: Product <-> Terpene
    percent is optional (many packages list it; many don't).
    """
    __tablename__ = "product_terpenes"

    product_id: UUID = Field(foreign_key="products.id", primary_key=True)
    terpene_id: UUID = Field(foreign_key="terpenes.id", primary_key=True)

    percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    product: Product = Relationship(back_populates="terpene_links")
    terpene: Terpene = Relationship(back_populates="product_links")


# ---------------------------
# Purchases (Orders)
# ---------------------------

class PurchaseSource(str, Enum):
    manual = "manual"
    pos_import = "pos_import"
    pos_api = "pos_api"


class Purchase(SQLModel, TimestampMixin, table=True):
    __tablename__ = "purchases"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    customer_id: UUID = Field(foreign_key="customers.id", index=True, nullable=False)
    purchased_at: datetime = Field(default_factory=utcnow, nullable=False)

    # store money as integer cents to avoid float issues
    total_amount_cents: int = Field(default=0, ge=0, nullable=False)

    source: PurchaseSource = Field(default=PurchaseSource.manual, nullable=False)
    notes: Optional[str] = Field(default=None, max_length=2000)

    customer: Customer = Relationship(back_populates="purchases")
    items: list["PurchaseItem"] = Relationship(back_populates="purchase")

class ItemFeedback(str, Enum):
    like = "like"
    dislike = "dislike"
    neutral = "neutral"

class PurchaseItem(SQLModel, table=True):
    __tablename__ = "purchase_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    purchase_id: UUID = Field(foreign_key="purchases.id", index=True, nullable=False)
    product_id: UUID = Field(foreign_key="products.id", index=True, nullable=False)

    quantity: int = Field(default=1, ge=1, nullable=False)
    line_amount_cents: Optional[int] = Field(default=None, ge=0)

    purchase: Purchase = Relationship(back_populates="items")
    product: Product = Relationship(back_populates="purchase_items")
    
    feedback: Optional[ItemFeedback] = Field(default=None, index=True)
    feedback_at: Optional[datetime] = Field(default=None)

