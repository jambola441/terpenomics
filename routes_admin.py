# routes_admin.py

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, List
from uuid import UUID
import os
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from pydantic import BaseModel, EmailStr
from pydantic import BaseModel, Field as PydField
from sqlmodel import Session, select, delete, func, or_

from auth import SupabaseAuthUser, get_current_user
from database import get_session
from models import (
    Customer,
    Product,
    ProductCategory,
    Purchase,
    PurchaseItem,
    PurchaseSource,
    Terpene,
    ProductTerpene,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------
# AuthZ: Admin gate (simple MVP)
# ---------------------------

def require_admin(user: SupabaseAuthUser = Depends(get_current_user)) -> SupabaseAuthUser:
    """
    MVP admin check:
    - expects Supabase JWT claim `role` == "admin"
    How to set:
    - easiest is Supabase custom claims / RLS policy approach later
    - for MVP, you can use a single admin user and manually set the claim,
      or replace this with an allowlist of admin user_ids in env.
    """
    # Option A: claim-based
    if user.role == "admin":
        return user

    # Option B: allowlist fallback
    allowlist = {
        x.strip() for x in (os.getenv("ADMIN_USER_IDS", "")).split(",") if x.strip()
    }
    print("user.user_id:", user.user_id, "allowlist:", allowlist)
    if allowlist and user.user_id in allowlist:
        return user

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


# ---------------------------
# Customers
# ---------------------------

class CustomerCreate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    marketing_opt_in: bool = False


@router.get("/customers")
def list_customers(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Customer)

    if q:
        qq = q.strip()
        like = f"%{qq}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(like),
                Customer.email.ilike(like),
                Customer.phone.ilike(like),
            )
        )

    stmt = stmt.order_by(Customer.created_at.desc()).offset(offset).limit(limit)
    customers = session.exec(stmt).all()

    return [
        {
            "id": str(c.id),
            "name": c.name,
            "phone": c.phone,
            "email": c.email,
            "marketing_opt_in": c.marketing_opt_in,
            "last_visit_at": c.last_visit_at.isoformat() if c.last_visit_at else None,
            "auth_user_id": str(c.auth_user_id) if getattr(c, "auth_user_id", None) else None,
        }
        for c in customers
    ]

@router.post("/customers")
def create_customer(
    payload: CustomerCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    c = Customer(
        id=uuid4(),
        name=payload.name.strip() if payload.name else None,
        phone=payload.phone.strip() if payload.phone else None,
        email=payload.email.strip() if payload.email else None,
        marketing_opt_in=payload.marketing_opt_in,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    return {
        "id": str(c.id),
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "marketing_opt_in": c.marketing_opt_in,
        "last_visit_at": c.last_visit_at.isoformat() if c.last_visit_at else None,
        "auth_user_id": str(c.auth_user_id) if getattr(c, "auth_user_id", None) else None,
    }


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    marketing_opt_in: Optional[bool] = None



@router.get("/customers/{customer_id}")
def get_customer_detail(
    customer_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    # One query: purchases + items + products + product_terpenes + terpenes
    rows = session.exec(
        select(Purchase, PurchaseItem, Product, ProductTerpene, Terpene)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id, isouter=True)
        .join(Product, Product.id == PurchaseItem.product_id, isouter=True)
        .join(ProductTerpene, ProductTerpene.product_id == Product.id, isouter=True)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id, isouter=True)
        .where(Purchase.customer_id == customer_id)
        .order_by(Purchase.purchased_at.desc())
    ).all()

    purchases_by_id = {}
    for purchase, item, product, link, terpene in rows:
        pur_id = str(purchase.id)
        if pur_id not in purchases_by_id:
            purchases_by_id[pur_id] = {
                "id": pur_id,
                "purchased_at": purchase.purchased_at.isoformat(),
                "total_amount_cents": purchase.total_amount_cents,
                "source": purchase.source,
                "notes": purchase.notes,
                "items": [],
            }

        if item is None or product is None:
            continue

        item_id = str(item.id)
        # find or create item entry within this purchase
        items = purchases_by_id[pur_id]["items"]
        item_entry = next((x for x in items if x["id"] == item_id), None)
        if item_entry is None:
            item_entry = {
                "id": item_id,
                "product_id": str(product.id),
                "product_name": product.name,
                "quantity": item.quantity,
                "line_amount_cents": item.line_amount_cents,
                "feedback": getattr(item, "feedback", None),
                "feedback_at": item.feedback_at.isoformat() if getattr(item, "feedback_at", None) else None,
                "terpenes": [],
            }
            items.append(item_entry)

        # append terpene if present
        if terpene is not None and link is not None:
            item_entry["terpenes"].append(
                {"name": terpene.name, "percent": link.percent}
            )

    return {
        "customer": {
            "id": str(c.id),
            "name": c.name,
            "phone": c.phone,
            "email": c.email,
            "marketing_opt_in": c.marketing_opt_in,
            "last_visit_at": c.last_visit_at.isoformat() if c.last_visit_at else None,
        },
        "purchases": list(purchases_by_id.values()),
    }

@router.post("/customers/{customer_id}")
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    if payload.name is not None:
        c.name = payload.name.strip() if payload.name else None
    if payload.phone is not None:
        c.phone = payload.phone.strip() if payload.phone else None
    if payload.email is not None:
        c.email = payload.email.strip() if payload.email else None
    if payload.marketing_opt_in is not None:
        c.marketing_opt_in = payload.marketing_opt_in

    session.add(c)
    session.commit()
    session.refresh(c)

    return {
        "id": str(c.id),
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "marketing_opt_in": c.marketing_opt_in,
        "last_visit_at": c.last_visit_at.isoformat() if c.last_visit_at else None,
    }


# ---------------------------
# Products + terpenes
# ---------------------------

class ProductTerpeneInput(BaseModel):
    name: str
    percent: Optional[float] = None


class ProductCreate(BaseModel):
    name: str
    brand: Optional[str] = None
    category: ProductCategory = ProductCategory.other
    is_active: bool = True
    terpenes: List[ProductTerpeneInput] = []


@router.get("/products")
def list_products(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    # One query: Product + (optional) ProductTerpene + (optional) Terpene
    rows = session.exec(
        select(Product, ProductTerpene, Terpene)
        .join(ProductTerpene, ProductTerpene.product_id == Product.id, isouter=True)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id, isouter=True)
        .order_by(Product.created_at.desc())
    ).all()

    by_id = {}

    for product, link, terpene in rows:
        pid = str(product.id)
        if pid not in by_id:
            by_id[pid] = {
                "id": pid,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "is_active": product.is_active,
                "terpenes": [],
            }

        if terpene is not None and link is not None:
            by_id[pid]["terpenes"].append(
                {"name": terpene.name, "percent": link.percent}
            )

    return list(by_id.values())


@router.post("/products")
def create_product(
    payload: ProductCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    p = Product(
        name=payload.name.strip(),
        brand=payload.brand.strip() if payload.brand else None,
        category=payload.category,
        is_active=payload.is_active,
    )
    session.add(p)
    session.commit()
    session.refresh(p)

    # attach terpenes
    for t_in in payload.terpenes:
        tname = t_in.name.strip()
        if not tname:
            continue
        terp = session.exec(select(Terpene).where(Terpene.name == tname)).first()
        if not terp:
            terp = Terpene(name=tname)
            session.add(terp)
            session.commit()
            session.refresh(terp)

        link = ProductTerpene(
            product_id=p.id,
            terpene_id=terp.id,
            percent=t_in.percent,
        )
        session.add(link)

    session.commit()
    return {"id": str(p.id)}


@router.get("/products/{product_id}")
def get_product(
    product_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")

    links = session.exec(select(ProductTerpene).where(ProductTerpene.product_id == product_id)).all()
    terpene_rows = []
    for link in links:
        terp = session.get(Terpene, link.terpene_id)
        if terp:
            terpene_rows.append({"name": terp.name, "percent": link.percent})

    return {
        "id": str(p.id),
        "name": p.name,
        "brand": p.brand,
        "category": p.category,
        "is_active": p.is_active,
        "terpenes": terpene_rows,
    }


class ProductTerpeneInput(BaseModel):
    name: str
    percent: Optional[float] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[ProductCategory] = None
    is_active: Optional[bool] = None
    terpenes: Optional[List[ProductTerpeneInput]] = None  # if provided, REPLACE


@router.post("/products/{product_id}")
def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")

    if payload.name is not None:
        p.name = payload.name.strip()
    if payload.brand is not None:
        p.brand = payload.brand.strip() if payload.brand else None
    if payload.category is not None:
        p.category = payload.category
    if payload.is_active is not None:
        p.is_active = payload.is_active

    # Replace terpenes if provided
    if payload.terpenes is not None:
        session.exec(delete(ProductTerpene).where(ProductTerpene.product_id == product_id))

        for t_in in payload.terpenes:
            tname = t_in.name.strip()
            if not tname:
                continue

            terp = session.exec(select(Terpene).where(Terpene.name == tname)).first()
            if not terp:
                terp = Terpene(name=tname)
                session.add(terp)
                session.flush()  # get terp.id without extra round trip

            session.add(
                ProductTerpene(
                    product_id=product_id,
                    terpene_id=terp.id,
                    percent=t_in.percent,
                )
            )

    session.add(p)
    session.commit()
    session.refresh(p)

    # return updated product (including terpenes)
    links = session.exec(select(ProductTerpene).where(ProductTerpene.product_id == product_id)).all()
    terps = []
    for link in links:
        t = session.get(Terpene, link.terpene_id)
        if t:
            terps.append({"name": t.name, "percent": link.percent})

    return {
        "id": str(p.id),
        "name": p.name,
        "brand": p.brand,
        "category": p.category,
        "is_active": p.is_active,
        "terpenes": terps,
    }


# ---------------------------
# Purchases (manual entry)
# ---------------------------


# ---------------------------
# Purchases: create + add items + finalize
# ---------------------------

@router.get("/purchases")
def list_purchases(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    source: Optional[Literal["manual", "pos_import"]] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(
            Purchase.id,
            Purchase.customer_id,
            Purchase.purchased_at,
            Purchase.total_amount_cents,
            Purchase.source,
            Purchase.external_id,  # REMOVE THIS LINE if you don't have the column
            Customer.name,
            Customer.phone,
            func.count(PurchaseItem.id).label("item_count"),
        )
        .select_from(Purchase)
        .join(Customer, Customer.id == Purchase.customer_id)
        .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id, isouter=True)
        .group_by(
            Purchase.id,
            Purchase.customer_id,
            Purchase.purchased_at,
            Purchase.total_amount_cents,
            Purchase.source,
            Purchase.external_id,  # REMOVE if column missing
            Customer.name,
            Customer.phone,
        )
        .order_by(Purchase.purchased_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if source:
        stmt = stmt.where(Purchase.source == source)

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Purchase.external_id.ilike(like),  # REMOVE if no column
            )
        )

    rows = session.exec(stmt).all()

    return [
        {
            "id": str(r[0]),
            "customer_id": str(r[1]),
            "purchased_at": r[2].isoformat(),
            "total_amount_cents": r[3],
            "source": r[4],
            "external_id": r[5],
            "customer_name": r[6],
            "customer_phone": r[7],
            "item_count": r[8],
        }
        for r in rows
    ]



class PurchaseCreate(BaseModel):
    customer_id: UUID
    purchased_at: Optional[datetime] = None
    source: Literal["manual", "pos_import"] = "manual"
    external_id: Optional[str] = None
    notes: Optional[str] = None


@router.post("/purchases")
def create_purchase(
    payload: PurchaseCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    customer = session.get(Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")

    purchased_at = payload.purchased_at or datetime.now(timezone.utc)

    p = Purchase(
        id=uuid4(),
        customer_id=payload.customer_id,
        purchased_at=purchased_at,
        total_amount_cents=0,
        source=payload.source,
        external_id=payload.external_id,
        notes=payload.notes,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session.add(p)
    session.commit()
    session.refresh(p)

    return {
        "id": str(p.id),
        "customer_id": str(p.customer_id),
        "purchased_at": p.purchased_at.isoformat(),
        "total_amount_cents": p.total_amount_cents,
        "source": p.source,
        "external_id": getattr(p, "external_id", None),
        "notes": p.notes,
    }


class PurchaseItemAdd(BaseModel):
    product_id: UUID
    quantity: int = PydField(default=1, ge=1, le=100)
    line_amount_cents: int = PydField(ge=0)
    # optional POS line key if you want idempotency on items later
    external_id: Optional[str] = None


@router.post("/purchases/{purchase_id}/items")
def add_purchase_item(
    purchase_id: UUID,
    payload: PurchaseItemAdd,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    purchase = session.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status_code=404, detail="purchase not found")

    product = session.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="product not found")

    # If you later add unique(purchase_id, external_id) you can enforce idempotency here.
    item = PurchaseItem(
        id=uuid4(),
        purchase_id=purchase_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        line_amount_cents=payload.line_amount_cents,
        external_id=payload.external_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session.add(item)
    session.commit()
    session.refresh(item)

    return {
        "id": str(item.id),
        "purchase_id": str(item.purchase_id),
        "product_id": str(item.product_id),
        "product_name": product.name,
        "quantity": item.quantity,
        "line_amount_cents": item.line_amount_cents,
        "feedback": getattr(item, "feedback", None),
        "feedback_at": item.feedback_at.isoformat() if getattr(item, "feedback_at", None) else None,
    }


@router.post("/purchases/{purchase_id}/finalize")
def finalize_purchase(
    purchase_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    purchase = session.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status_code=404, detail="purchase not found")

    total = session.exec(
        select(func.coalesce(func.sum(PurchaseItem.line_amount_cents), 0))
        .where(PurchaseItem.purchase_id == purchase_id)
    ).one()

    purchase.total_amount_cents = int(total)
    purchase.updated_at = datetime.now(timezone.utc)

    session.add(purchase)
    session.commit()
    session.refresh(purchase)

    return {
        "id": str(purchase.id),
        "customer_id": str(purchase.customer_id),
        "purchased_at": purchase.purchased_at.isoformat(),
        "total_amount_cents": purchase.total_amount_cents,
        "source": purchase.source,
        "external_id": getattr(purchase, "external_id", None),
        "notes": purchase.notes,
    }

class PurchaseItemFeedbackUpdate(BaseModel):
    feedback: Optional[Literal["like", "dislike", "neutral"]] = None  # null clears it

@router.post("/purchase-items/{purchase_item_id}/feedback")
def set_purchase_item_feedback(
    purchase_item_id: UUID,
    payload: PurchaseItemFeedbackUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    item = session.get(PurchaseItem, purchase_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="purchase_item not found")

    item.feedback = payload.feedback
    item.feedback_at = datetime.utcnow() if payload.feedback is not None else None

    session.add(item)
    session.commit()
    session.refresh(item)

    return {
        "id": str(item.id),
        "feedback": item.feedback,
        "feedback_at": item.feedback_at.isoformat() if item.feedback_at else None,
    }

@router.get("/customers/{customer_id}/terpene-scores")
def get_customer_terpene_scores(
    customer_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    window_days: int = 180,
):
    c = session.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")

    if window_days < 1 or window_days > 3650:
        raise HTTPException(status_code=400, detail="window_days must be between 1 and 3650")

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    # One query: purchase_items (with feedback) + purchase (for time/customer) + product_terpenes + terpene names
    rows = session.exec(
        select(PurchaseItem, ProductTerpene, Terpene)
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .join(ProductTerpene, ProductTerpene.product_id == PurchaseItem.product_id)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id)
        .where(Purchase.customer_id == customer_id)
        .where(Purchase.purchased_at >= cutoff)
    ).all()

    # scoring weights (tune later)
    def sign(feedback: str | None) -> float:
        if feedback == "like":
            return 1.0
        if feedback == "dislike":
            return -1.0
        if feedback == "neutral":
            return 0.0
        return 0.0  # no feedback = no signal (MVP)

    scores: dict[str, dict] = {}
    for item, link, terp in rows:
        fb = getattr(item, "feedback", None)
        w = sign(fb)
        if w == 0.0:
            continue

        pct = link.percent if link.percent is not None else 0.10  # default 0.10% if missing
        # keep pct in "percent units" so 0.62 stays 0.62; you can normalize later
        contrib = w * float(pct)

        tname = terp.name
        if tname not in scores:
            scores[tname] = {
                "terpene": tname,
                "score": 0.0,
                "likes": 0,
                "dislikes": 0,
                "neutrals": 0,
            }

        scores[tname]["score"] += contrib
        if fb == "like":
            scores[tname]["likes"] += 1
        elif fb == "dislike":
            scores[tname]["dislikes"] += 1
        elif fb == "neutral":
            scores[tname]["neutrals"] += 1

    # sort by score desc
    out = sorted(scores.values(), key=lambda x: x["score"], reverse=True)

    return {
        "customer_id": str(customer_id),
        "window_days": window_days,
        "cutoff": cutoff.isoformat(),
        "scores": out,
    }
