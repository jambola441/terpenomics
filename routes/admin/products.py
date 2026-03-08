from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, delete, or_
from sqlalchemy import cast, String

from auth import SupabaseAuthUser
from database import get_session
from models import Product, ProductCategory, ProductTerpene, Terpene, Cannabinoid, ProductCannabinoid, CannabinoidFamily
from .auth import require_admin
from .serializers import serialize_product


router = APIRouter()


class ProductTerpeneInput(BaseModel):
    name: str
    percent: Optional[float] = None


class ProductCannabinoidInput(BaseModel):
    name: str
    family: CannabinoidFamily
    percent: Optional[float] = None


class ProductCreate(BaseModel):
    name: str
    brand: Optional[str] = None
    category: ProductCategory = ProductCategory.other
    is_active: bool = True
    terpenes: List[ProductTerpeneInput] = []
    cannabinoids: List[ProductCannabinoidInput] = []


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[ProductCategory] = None
    is_active: Optional[bool] = None
    terpenes: Optional[List[ProductTerpeneInput]] = None  # if provided, REPLACE
    cannabinoids: Optional[List[ProductCannabinoidInput]] = None  # if provided, REPLACE


def _load_product_terpenes(session: Session, product_id: UUID) -> list:
    rows = session.exec(
        select(ProductTerpene, Terpene)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id)
        .where(ProductTerpene.product_id == product_id)
    ).all()
    return [{"name": terp.name, "percent": link.percent} for link, terp in rows]


def _load_product_cannabinoids(session: Session, product_id: UUID) -> list:
    rows = session.exec(
        select(ProductCannabinoid, Cannabinoid)
        .join(Cannabinoid, Cannabinoid.id == ProductCannabinoid.cannabinoid_id)
        .where(ProductCannabinoid.product_id == product_id)
    ).all()
    return [{"name": c.name, "family": c.family, "percent": link.percent} for link, c in rows]


@router.get("/products")
def list_products(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    # Step 1: select product ids for this page (so pagination doesn't truncate terpene rows)
    id_stmt = select(Product.id)

    if q:
        like = f"%{q.strip()}%"
        id_stmt = id_stmt.where(
            or_(
                Product.name.ilike(like),
                Product.brand.ilike(like),
                cast(Product.category, String).ilike(like),
            )
        )

    id_stmt = id_stmt.order_by(Product.created_at.desc()).offset(offset).limit(limit)
    product_ids = session.exec(id_stmt).all()

    if not product_ids:
        return []

    # Step 2: fetch full rows (product + terpenes) for only these ids
    rows = session.exec(
        select(Product, ProductTerpene, Terpene)
        .join(ProductTerpene, ProductTerpene.product_id == Product.id, isouter=True)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id, isouter=True)
        .where(Product.id.in_(product_ids))
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
                "cannabinoids": [],
            }

        if terpene is not None and link is not None:
            by_id[pid]["terpenes"].append({"name": terpene.name, "percent": link.percent})

    # Batch load cannabinoids for the same product ids
    cannab_rows = session.exec(
        select(ProductCannabinoid, Cannabinoid)
        .join(Cannabinoid, Cannabinoid.id == ProductCannabinoid.cannabinoid_id)
        .where(ProductCannabinoid.product_id.in_(product_ids))
    ).all()

    for link, c in cannab_rows:
        pid = str(link.product_id)
        if pid in by_id:
            by_id[pid]["cannabinoids"].append({"name": c.name, "family": c.family, "percent": link.percent})

    # Preserve the original ordering from product_ids
    order = {str(pid): i for i, pid in enumerate(product_ids)}
    return sorted(by_id.values(), key=lambda x: order.get(x["id"], 10**9))


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
    session.flush()

    for t_in in payload.terpenes:
        tname = t_in.name.strip()
        if not tname:
            continue
        terp = session.exec(select(Terpene).where(Terpene.name == tname)).first()
        if not terp:
            terp = Terpene(name=tname)
            session.add(terp)
            session.flush()

        link = ProductTerpene(
            product_id=p.id,
            terpene_id=terp.id,
            percent=t_in.percent,
        )
        session.add(link)

    for c_in in payload.cannabinoids:
        cname = c_in.name.strip()
        if not cname:
            continue
        cannab = session.exec(select(Cannabinoid).where(Cannabinoid.name == cname)).first()
        if not cannab:
            cannab = Cannabinoid(name=cname, family=c_in.family)
            session.add(cannab)
            session.flush()

        session.add(ProductCannabinoid(
            product_id=p.id,
            cannabinoid_id=cannab.id,
            percent=c_in.percent,
        ))

    session.commit()
    session.refresh(p)
    return {"id": str(p.id)}


@router.get("/products/cannabinoids")
def get_products_cannabinoids_batch(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    product_ids: Optional[str] = Query(default=None, description="Comma-separated list of product UUIDs"),
):
    # No product_ids → return flat list of all cannabinoids for autocomplete
    if product_ids is None:
        rows = session.exec(select(Cannabinoid).order_by(Cannabinoid.name)).all()
        return [{"name": c.name, "family": c.family} for c in rows]

    try:
        ids = [UUID(pid.strip()) for pid in product_ids.split(",") if pid.strip()]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid product_id format: {e}")

    if not ids:
        return {}

    if len(ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 product IDs allowed")

    rows = session.exec(
        select(ProductCannabinoid, Cannabinoid)
        .join(Cannabinoid, Cannabinoid.id == ProductCannabinoid.cannabinoid_id)
        .where(ProductCannabinoid.product_id.in_(ids))
    ).all()

    result = {str(pid): [] for pid in ids}
    for link, c in rows:
        pid_str = str(link.product_id)
        if pid_str in result:
            result[pid_str].append({"name": c.name, "family": c.family, "percent": link.percent})

    return result


@router.get("/products/terpenes")
def get_products_terpenes_batch(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    product_ids: Optional[str] = Query(default=None, description="Comma-separated list of product UUIDs"),
):
    # No product_ids → return flat list of all terpenes for autocomplete
    if product_ids is None:
        rows = session.exec(select(Terpene).order_by(Terpene.name)).all()
        return [{"name": t.name} for t in rows]

    # Parse comma-separated UUIDs
    try:
        ids = [UUID(pid.strip()) for pid in product_ids.split(",") if pid.strip()]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid product_id format: {e}")

    if not ids:
        return {}

    if len(ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 product IDs allowed")

    # Fetch all product-terpene links for these products
    rows = session.exec(
        select(ProductTerpene, Terpene)
        .join(Terpene, Terpene.id == ProductTerpene.terpene_id)
        .where(ProductTerpene.product_id.in_(ids))
    ).all()

    # Build mapping
    result = {str(pid): [] for pid in ids}
    for link, terpene in rows:
        pid_str = str(link.product_id)
        if pid_str in result:
            result[pid_str].append({
                "name": terpene.name,
                "percent": link.percent,
            })
    
    return result


@router.get("/products/{product_id}")
def get_product(
    product_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    p = session.get(Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")

    terpenes = _load_product_terpenes(session, product_id)
    cannabinoids = _load_product_cannabinoids(session, product_id)
    return serialize_product(p, terpenes, cannabinoids)


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
                session.flush()

            session.add(
                ProductTerpene(
                    product_id=product_id,
                    terpene_id=terp.id,
                    percent=t_in.percent,
                )
            )

    if payload.cannabinoids is not None:
        session.exec(delete(ProductCannabinoid).where(ProductCannabinoid.product_id == product_id))

        for c_in in payload.cannabinoids:
            cname = c_in.name.strip()
            if not cname:
                continue

            cannab = session.exec(select(Cannabinoid).where(Cannabinoid.name == cname)).first()
            if not cannab:
                cannab = Cannabinoid(name=cname, family=c_in.family)
                session.add(cannab)
                session.flush()

            session.add(
                ProductCannabinoid(
                    product_id=product_id,
                    cannabinoid_id=cannab.id,
                    percent=c_in.percent,
                )
            )

    session.add(p)
    session.commit()
    session.refresh(p)

    terpenes = _load_product_terpenes(session, product_id)
    cannabinoids = _load_product_cannabinoids(session, product_id)
    return serialize_product(p, terpenes, cannabinoids)
