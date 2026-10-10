"""Brand logos: pick each big brand's logo from its own site.

The list is the brands with the most active listings, with the site to read (what
was saved, else a storefront catalog's own site) and the logo now shown. For one
brand, `candidates` reads its home page for the images it names as its logo; choosing
one, or uploading a file, stores it in the photos bucket (services/brand_logos.py)
and brand tiles and pages show it.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, func, select

from auth import SupabaseAuthUser
from database import get_session
from models import BrandCatalog, BrandLogo, Listing
from services import brand_logos as logos
from services import photo_store, response_cache

from .auth import require_admin

router = APIRouter()


def _who(user: SupabaseAuthUser) -> str:
    return user.email or user.phone or user.user_id


def _catalog_sites(session: Session) -> dict[str, str]:
    """brand key -> the home page of the brand's own site, from its storefront catalog."""
    out = {}
    for name, url, method in session.exec(
        select(BrandCatalog.brand_name, BrandCatalog.source_url, BrandCatalog.source_method)
    ).all():
        if url and method != "listings_bootstrap":
            parts = urllib.parse.urlsplit(url)
            if parts.scheme == "https" and parts.hostname:
                out[logos.brand_key(name)] = f"https://{parts.hostname}/"
    return out


@router.get("/brand-logos")
def list_brand_logos(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    limit: int = Query(default=60, ge=1, le=300),
    q: Optional[str] = Query(default=None),
):
    """The biggest brands by active listings, spellings of one brand counted together."""
    stmt = (
        select(Listing.scraped_brand, func.count(Listing.id))
        .where(Listing.is_active == True)  # noqa: E712
        .where(Listing.scraped_brand.is_not(None))
        .where(Listing.scraped_brand != "")
        .group_by(Listing.scraped_brand)
    )
    if q and q.strip():
        stmt = stmt.where(Listing.scraped_brand.ilike(f"%{q.strip()}%"))
    brands: dict[str, dict] = {}
    for name, count in session.exec(stmt).all():
        key = logos.brand_key(name)
        b = brands.setdefault(key, {"brand_key": key, "brand_name": name, "listing_count": 0, "_top": 0})
        b["listing_count"] += count
        if count > b["_top"]:
            b["brand_name"], b["_top"] = name, count
    top = sorted(brands.values(), key=lambda b: -b["listing_count"])[:limit]
    saved = {r.brand_key: r for r in session.exec(
        select(BrandLogo).where(BrandLogo.brand_key.in_([b["brand_key"] for b in top]))).all()}
    sites = _catalog_sites(session)
    out = []
    for b in top:
        row = saved.get(b["brand_key"])
        out.append({
            "brand_key": b["brand_key"], "brand_name": b["brand_name"],
            "listing_count": b["listing_count"],
            "logo_url": row.logo_url if row else None,
            "site_url": (row.site_url if row and row.site_url else None) or sites.get(b["brand_key"]),
            "chosen_by": row.chosen_by if row else None,
            "updated_at": row.updated_at.isoformat() if row else None,
        })
    return out


class CandidatesIn(BaseModel):
    site_url: str


@router.post("/brand-logos/{brand_key}/candidates")
def find_candidates(
    brand_key: str, body: CandidatesIn,
    _: SupabaseAuthUser = Depends(require_admin),
):
    """The images the brand's home page names as its logo, most likely first."""
    try:
        return {"site_url": body.site_url, "candidates": logos.candidates(body.site_url.strip())}
    except logos.UnsafeURL as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 — the site's problem, said plainly
        raise HTTPException(status_code=502, detail=f"Could not read that site: {e}")


def _save(session: Session, key: str, brand_name: str, data: bytes, source_url: Optional[str],
          site_url: Optional[str], user: SupabaseAuthUser) -> BrandLogo:
    if not photo_store.configured():
        raise HTTPException(status_code=503, detail="Photo storage is not configured on the API")
    try:
        url = logos.store_logo(key, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"That file can't be a logo: {e}")
    row = session.get(BrandLogo, key) or BrandLogo(brand_key=key, brand_name=brand_name)
    row.brand_name, row.logo_url, row.source_url = brand_name, url, source_url
    row.site_url = site_url or row.site_url
    row.chosen_by, row.updated_at = _who(user), datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    response_cache.clear()          # brand pages are cached; show the logo now
    return row


def _json(row: BrandLogo) -> dict:
    return {"brand_key": row.brand_key, "brand_name": row.brand_name, "logo_url": row.logo_url,
            "source_url": row.source_url, "site_url": row.site_url, "chosen_by": row.chosen_by,
            "updated_at": row.updated_at.isoformat()}


class ChooseIn(BaseModel):
    brand_name: str
    image_url: str
    site_url: Optional[str] = None


@router.post("/brand-logos/{brand_key}")
def choose_logo(
    brand_key: str, body: ChooseIn,
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
):
    """Use this image, fetched from the brand's site, as the brand's logo."""
    key = logos.brand_key(brand_key)
    try:
        data, _, _ = logos.fetch(body.image_url, logos.MAX_IMAGE_BYTES, "image/*")
    except logos.UnsafeURL as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not fetch that image: {e}")
    return _json(_save(session, key, body.brand_name, data, body.image_url, body.site_url, user))


@router.post("/brand-logos/{brand_key}/upload")
async def upload_logo(
    brand_key: str,
    brand_name: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
):
    """Use an uploaded file as the brand's logo, for a site whose logo can't be read."""
    data = await file.read(logos.MAX_IMAGE_BYTES + 1)
    if len(data) > logos.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Logos are at most 5 MB")
    return _json(_save(session, logos.brand_key(brand_key), brand_name, data, None, None, user))


@router.delete("/brand-logos/{brand_key}")
def remove_logo(
    brand_key: str,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Stop showing the logo; the brand goes back to its product photo or initial."""
    row = session.get(BrandLogo, logos.brand_key(brand_key))
    if row:
        row.logo_url, row.updated_at = None, datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        response_cache.clear()
    return {"ok": True}
