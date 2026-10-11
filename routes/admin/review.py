"""
review.py — The catalog review queue: one listing at a time, a person's call recorded.

The matcher (scripts/catalog_match.py) leaves a listing it could not settle with a
review reason in `catalog_match_method`:

  review_unsure   read against the catalog, but some step unsurely; catalog_entry_id
                  usually holds the suggested entry
  review_missing  the catalog most likely lacks the product
  review_near     one catalog entry is one attribute off (often a size it lacks)

and the importer (scripts/import_listings.py mark_unsure_category) leaves one more:

  review_category  Jev was unsure of the listing's category or subtype at enrichment
                   (under CATEGORY_REVIEW_BELOW) and the catalog did not settle it
                   (owner decision 2026-10-11)

For the catalog reasons a reviewer sees the store's listing beside up to four of its brand's catalog entries
and says which it is (`entry`), none of them (`none`), that the catalog is missing
the product or size (`missing`), or `skip`.

**`entry` is a transition to trusted, by review.** The listing becomes a manual
match to that entry (catalog_entry_id, catalog_match_method 'manual', confidence 1.0)
and takes the entry's identity at once, through the importer's own overlay
(import_listings.overlay_entry); every later import keeps a manual match and
overlays it again. That takes it out of the queue for good. The listing's previous
match is kept on the decision (reason, prev_entry_id, prev_confidence) and undo puts
it back.

**`category` settles a review_category listing.** Its card offers every category
and each one's subtypes (scripts/taxonomy.py) instead of catalog entries. The call
writes the chosen category and subtype to the listing and adds both to its
verified_fields, bound to its scraped name (scripts/verification.py), so every
later import keeps them and stops marking it; the listing's catalog_match_method is
cleared. The decision keeps what it replaced (reason, prev_category, prev_subtype,
prev_verified) and undo puts it back.

**Every other decision is recorded only.** `none`, `missing` and `skip` touch
neither the listing's match nor a catalog entry: catalog issues are fixed in the
catalog, and the review_decisions rows are what those fixes are proposed from. A
listing with a decision, skip included, is out of the queue; undo deletes the
reviewer's last decision and puts its listing back.

A listing's brand is matched to its catalog by catalog_store.brand_key (lowercase,
'&' as 'and', no punctuation): the key catalogs are filed under everywhere else, so
'Papa & Barkley' and 'papa and barkley' are one brand and one queue.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from auth import SupabaseAuthUser
from database import get_session
from models import (
    REVIEW_REASONS, BrandCatalog, BrandCatalogEntry, Dispensary, Listing, ReviewDecision, utcnow,
)
from .auth import require_admin

# scripts/ is not a package; reached by path as brand_catalogs.py does. Appended, so
# it can never shadow an installed package.
_SCRIPTS = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.append(_SCRIPTS)

from catalog_store import brand_key  # noqa: E402
import taxonomy  # noqa: E402
import verification  # noqa: E402

router = APIRouter(prefix="/review")

MAX_CANDIDATES = 4
DESCRIPTION_CHARS = 600
# Words too common to say two products are alike.
_STOP = {"the", "and", "with", "for", "pack", "pk", "mg", "thc", "cbd"}


def _reviewer(user: SupabaseAuthUser) -> str:
    return user.email or user.phone or user.user_id


def _in_queue():
    """Active listings the matcher left for review."""
    return (Listing.is_active == True) & col(Listing.catalog_match_method).in_(REVIEW_REASONS)  # noqa: E712


def _decided_ids():
    return select(ReviewDecision.listing_id)


def _entry_dict(e: BrandCatalogEntry) -> dict:
    """An entry in catalog_store's shape, for the importer's helpers."""
    return {"id": str(e.id), "name": e.name, "product_line": e.product_line, "category": e.category,
            "subtype": e.subtype, "strain": e.strain, "variant": e.variant, "is_active": e.is_active,
            "product_key": getattr(e, "product_key", None),
            "product_external_id": getattr(e, "product_external_id", None)}


# Listing columns overlay_entry may change.
_OVERLAID = ("scraped_category", "subtype", "strain", "product_line", "size")


def make_manual(session: Session, listing: Listing, entry: BrandCatalogEntry) -> None:
    """Make `listing` a manual match to `entry` and overlay the entry's identity as the
    importer does (import_listings.overlay_entry). Does not commit."""
    import import_listings  # noqa: E402  (scripts/, on sys.path above)

    entries = session.exec(select(BrandCatalogEntry)
                           .where(BrandCatalogEntry.catalog_id == entry.catalog_id)).all()
    catalog = {"entries": [_entry_dict(e) for e in entries]}
    entry_d = next(d for d in catalog["entries"] if d["id"] == str(entry.id))
    rec = {"scraped_name": listing.scraped_name, "scraped_category": listing.scraped_category,
           "subtype": listing.subtype, "strain": listing.strain, "product_line": listing.product_line,
           "variant": listing.variant, "size": listing.size, "description": listing.description}
    import_listings.overlay_entry(rec, catalog, entry_d)
    for k in _OVERLAID:
        setattr(listing, k, rec[k])
    listing.catalog_entry_id = entry.id
    listing.catalog_match_method = "manual"
    listing.catalog_match_confidence = 1.0
    session.add(listing)


def _catalogs(session: Session) -> dict[str, BrandCatalog]:
    return {brand_key(c.brand_name): c for c in session.exec(select(BrandCatalog)).all()}


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

def _empty_counts() -> dict:
    return {"total": 0, "decided": 0, "remaining": 0,
            "by_reason": {r: {"total": 0, "decided": 0} for r in REVIEW_REASONS}}


def _add(counts: dict, reason: str, total: int, decided: int) -> None:
    counts["total"] += total
    counts["decided"] += decided
    counts["remaining"] = counts["total"] - counts["decided"]
    counts["by_reason"][reason]["total"] += total
    counts["by_reason"][reason]["decided"] += decided


def _brand_groups(session: Session) -> list[dict]:
    """The queue per brand, largest remaining first. Each group carries the raw
    scraped_brand spellings it folds together (`names`), for filtering listings."""
    def counts(decided: bool):
        stmt = (select(Listing.scraped_brand, Listing.catalog_match_method, func.count())
                .where(_in_queue())
                .group_by(Listing.scraped_brand, Listing.catalog_match_method))
        if decided:
            stmt = stmt.where(col(Listing.id).in_(_decided_ids()))
        return {(b, m): n for b, m, n in session.exec(stmt).all()}

    totals, decided = counts(False), counts(True)
    catalogs = _catalogs(session)
    groups: dict[str, dict] = {}
    for (name, reason), total in totals.items():
        key = brand_key(name)
        g = groups.setdefault(key, {"key": key, "names": {}, **_empty_counts()})
        g["names"][name] = g["names"].get(name, 0) + total
        _add(g, reason, total, decided.get((name, reason), 0))
    out = []
    for key, g in groups.items():
        # The catalog's own spelling of the brand when there is one, else the one
        # most of its listings use.
        catalog = catalogs.get(key)
        label = catalog.brand_name if catalog else max(g["names"], key=lambda n: (g["names"][n], n or ""))
        out.append({**g, "brand": label or "(no brand)", "has_catalog": catalog is not None})
    out.sort(key=lambda g: (-g["remaining"], -g["total"], g["brand"].lower()))
    return out


def _local_midnight(now: datetime, tz_offset: int) -> datetime:
    """Midnight today where the reviewer is, in UTC. tz_offset is the browser's
    Date.getTimezoneOffset(): minutes behind UTC (240 in New York in summer)."""
    local = now - timedelta(minutes=tz_offset)
    return local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=tz_offset)


def _progress(session: Session, reviewer: str, brand: Optional[str] = None, tz_offset: int = 0) -> dict:
    groups = _brand_groups(session)
    totals = _empty_counts()
    for g in groups:
        for reason, c in g["by_reason"].items():
            _add(totals, reason, c["total"], c["decided"])
    if brand:
        groups = [g for g in groups if g["key"] == brand_key(brand)]

    now = utcnow()

    def mine_since(when: datetime) -> int:
        return session.exec(select(func.count()).select_from(ReviewDecision).where(
            ReviewDecision.reviewer == reviewer, ReviewDecision.created_at >= when)).one()

    return {
        "brands": [{k: g[k] for k in ("brand", "has_catalog", "total", "decided", "remaining", "by_reason")}
                   for g in groups],
        "totals": totals,
        "me": {"today": mine_since(_local_midnight(now, tz_offset)),
               "last_10_min": mine_since(now - timedelta(minutes=10))},
    }


# ---------------------------------------------------------------------------
# The card
# ---------------------------------------------------------------------------

def _words(*texts: Optional[str]) -> set[str]:
    out: set[str] = set()
    for s in texts:
        out.update(w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) >= 3 and w not in _STOP)
    return out


def _same(a: Optional[str], b: Optional[str]) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def _candidate(e: BrandCatalogEntry, suggested: bool = False) -> dict:
    return {"id": str(e.id), "name": e.name, "product_line": e.product_line, "strain": e.strain,
            "category": e.category, "subtype": e.subtype, "variant": e.variant,
            "image_url": e.image_url, "is_active": e.is_active, "suggested": suggested}


def _candidates(session: Session, listing: Listing, catalog: Optional[BrandCatalog]) -> list[dict]:
    """Up to four of the brand's entries, most likely first: the matcher's suggestion,
    then the reading's strain in other sizes and lines, then entries of the same
    category whose strain or name shares words with the listing's name."""
    if catalog is None:
        return []
    entries = session.exec(select(BrandCatalogEntry).where(BrandCatalogEntry.catalog_id == catalog.id)).all()
    reading = listing.reading or {}
    strain = reading.get("strain") or listing.strain
    category = reading.get("category") or listing.scraped_category
    line = reading.get("product_line") or listing.product_line

    picked: list[dict] = []
    seen: set[UUID] = set()

    def take(e: BrandCatalogEntry, suggested: bool = False) -> None:
        if len(picked) < MAX_CANDIDATES and e.id not in seen:
            seen.add(e.id)
            picked.append(_candidate(e, suggested))

    for e in entries:
        if e.id == listing.catalog_entry_id:
            take(e, suggested=True)

    active = [e for e in entries if e.is_active]
    same_strain = [e for e in active if _same(e.strain, strain)]
    # The reading's own line first, then the rest of that strain by name and size.
    same_strain.sort(key=lambda e: (not _same(e.product_line, line), e.name.lower(), e.variant or ""))
    for e in same_strain:
        take(e)

    if len(picked) < MAX_CANDIDATES:
        name_words = _words(listing.scraped_name) - _words(catalog.brand_name)
        scored = []
        for e in active:
            if category and e.category and not _same(e.category, category):
                continue
            shared = len(name_words & _words(e.strain, e.name))
            if shared:
                scored.append((-shared, e.name.lower(), e.variant or "", e))
        for *_, e in sorted(scored, key=lambda s: s[:3]):
            take(e)
    return picked


def _category_choice(listing: Listing) -> dict:
    """A review_category card's question: the listing's category and subtype now,
    Jev's probability for each (the enrichment reading's `p`), and every category with
    its subtypes to choose from (an empty list: the category keeps no subtype)."""
    p = (listing.reading or {}).get("p") or {}
    return {
        "category": listing.scraped_category,
        "subtype": listing.subtype,
        "p": {k: p[k] for k in ("category", "subtype") if k in p},
        "choices": [{"category": c, "subtypes": subs if taxonomy.keeps_subtype(c) else []}
                    for c, subs in taxonomy.rails().items()],
    }


def _card(session: Session, listing: Listing, dispensary: Dispensary, catalogs: dict[str, BrandCatalog]) -> dict:
    reading = listing.reading or {}
    catalog = catalogs.get(brand_key(listing.scraped_brand))
    description = (listing.description or "").strip()
    if len(description) > DESCRIPTION_CHARS:
        description = description[:DESCRIPTION_CHARS].rstrip() + "…"
    return {
        # The queue this card is in, as progress names it (the catalog's spelling).
        "brand": catalog.brand_name if catalog else listing.scraped_brand,
        "listing": {
            "id":          str(listing.id),
            "name":        listing.scraped_name,
            "brand":       listing.scraped_brand,
            "category":    listing.scraped_category,
            "store":       dispensary.name,
            "variant":     listing.variant,
            "size":        listing.product_size,
            "price_cents": listing.price_cents,
            "url":         listing.url,
            "image_url":   listing.image_url,
            "description": description or None,
        },
        "reason": listing.catalog_match_method,
        "reading": {k: reading.get(k) for k in
                    ("category", "subtype", "product_line", "strain", "size", "store_category", "by", "p")}
                   if reading else None,
        "candidates": [] if listing.catalog_match_method == "review_category"
                      else _candidates(session, listing, catalog),
        "category_choice": _category_choice(listing) if listing.catalog_match_method == "review_category"
                           else None,
    }


def _next_listing(session: Session, brand: Optional[str], reason: Optional[str],
                  exclude: list[UUID]) -> Optional[tuple[Listing, Dispensary]]:
    """The next undecided listing: brands with the largest queue left first, and
    within a brand by product, so like cards come in a row."""
    groups = [g for g in _brand_groups(session) if g["remaining"] > 0]
    if brand:
        groups = [g for g in groups if g["key"] == brand_key(brand)]
    for g in groups:
        stmt = (select(Listing, Dispensary)
                .join(Dispensary, Dispensary.id == Listing.dispensary_id)
                .where(_in_queue(), col(Listing.scraped_brand).in_(list(g["names"])),
                       col(Listing.id).not_in(_decided_ids())))
        if reason:
            stmt = stmt.where(Listing.catalog_match_method == reason)
        if exclude:
            stmt = stmt.where(col(Listing.id).not_in(exclude))
        stmt = stmt.order_by(
            func.lower(func.coalesce(Listing.product_line, "")),
            func.lower(func.coalesce(Listing.strain, "")),
            func.lower(func.coalesce(Listing.scraped_name, "")),
            func.coalesce(Listing.size, Listing.variant, ""),
            Listing.id,
        ).limit(1)
        row = session.exec(stmt).first()
        if row:
            return row
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/next")
def next_card(
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
    brand: Optional[str] = Query(default=None),
    reason: Optional[Literal["review_unsure", "review_missing", "review_near", "review_category"]] = Query(default=None),
    exclude: Optional[str] = Query(default=None, description="Comma-separated listing ids to pass over (the card on screen, when prefetching the one after it)"),
    tz_offset: int = Query(default=0, ge=-840, le=840),
):
    """The next card, with its candidates and the queue's progress; 204 when the
    queue (for this brand and reason) is done."""
    try:
        skip = [UUID(x) for x in (exclude or "").split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="exclude must be listing ids")
    row = _next_listing(session, brand, reason, skip)
    if row is None:
        return Response(status_code=204)
    card = _card(session, *row, _catalogs(session))
    card["progress"] = _progress(session, _reviewer(user), brand, tz_offset)
    return card


@router.get("/progress")
def progress(
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
    brand: Optional[str] = Query(default=None),
    tz_offset: int = Query(default=0, ge=-840, le=840),
):
    """Per brand (only `brand` when given): queue total, decided, remaining, by reason.
    `totals` is always the whole queue; `me` is the calling reviewer's pace."""
    return _progress(session, _reviewer(user), brand, tz_offset)


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: UUID
    decision: Literal["entry", "none", "missing", "skip", "category"]
    entry_id: Optional[UUID] = None
    # For the decision category: the listing's category and subtype (null when the
    # category keeps none).
    category: Optional[str] = None
    subtype: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/decisions")
def record_decision(
    body: DecisionIn,
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
    brand: Optional[str] = Query(default=None),
    tz_offset: int = Query(default=0, ge=-840, le=840),
):
    """Record a call on one listing. `entry` also makes the listing a manual match
    to the entry (make_manual), keeping its previous match on the decision for
    undo; `category` sets and verifies the listing's category and subtype, its
    previous ones kept on the decision; every other decision changes nothing but
    review_decisions."""
    listing = session.get(Listing, body.listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.catalog_match_method not in REVIEW_REASONS:
        raise HTTPException(status_code=409, detail="This listing is not in the review queue")
    if session.exec(select(ReviewDecision.id).where(ReviewDecision.listing_id == listing.id)).first():
        raise HTTPException(status_code=409, detail="This listing already has a decision")

    if listing.catalog_match_method == "review_category" and body.decision not in ("category", "skip"):
        raise HTTPException(status_code=422, detail="A review_category listing takes category or skip")
    if body.decision == "entry":
        if body.entry_id is None:
            raise HTTPException(status_code=422, detail="entry_id is required when the decision is entry")
        entry = session.get(BrandCatalogEntry, body.entry_id)
        catalog = _catalogs(session).get(brand_key(listing.scraped_brand))
        if entry is None or catalog is None or entry.catalog_id != catalog.id:
            raise HTTPException(status_code=422, detail="That entry is not in this listing's brand catalog")
    elif body.entry_id is not None:
        raise HTTPException(status_code=422, detail="entry_id is only for the decision entry")
    if body.decision == "category":
        if listing.catalog_match_method != "review_category":
            raise HTTPException(status_code=422, detail="category is only for a review_category listing")
        rails = taxonomy.rails()
        if body.category not in rails:
            raise HTTPException(status_code=422, detail="category must be one of " + ", ".join(rails))
        if taxonomy.keeps_subtype(body.category):
            if body.subtype not in rails[body.category]:
                raise HTTPException(status_code=422, detail=f"subtype must be one of {body.category}'s: "
                                                            + ", ".join(rails[body.category]))
        elif body.subtype is not None:
            raise HTTPException(status_code=422, detail=f"{body.category} keeps no subtype")
    elif body.category is not None or body.subtype is not None:
        raise HTTPException(status_code=422, detail="category and subtype are only for the decision category")

    reviewer = _reviewer(user)
    row = ReviewDecision(
        listing_id=listing.id, reviewer=reviewer, decision=body.decision, entry_id=body.entry_id,
        note=(body.note or "").strip() or None, reason=listing.catalog_match_method,
    )
    if body.decision == "entry":
        row.prev_entry_id = listing.catalog_entry_id
        row.prev_confidence = listing.catalog_match_confidence
        make_manual(session, listing, entry)
    elif body.decision == "category":
        row.category, row.subtype = body.category, body.subtype
        row.prev_category, row.prev_subtype = listing.scraped_category, listing.subtype
        row.prev_verified = listing.verified_fields
        listing.scraped_category, listing.subtype = body.category, body.subtype
        listing.verified_fields = verification.claim(
            {"category": body.category, "subtype": body.subtype}, listing.scraped_name or "", reviewer,
            existing=listing.verified_fields)
        listing.catalog_match_method = None
        session.add(listing)
    session.add(row)
    session.commit()
    return {"id": str(row.id), "progress": _progress(session, reviewer, brand, tz_offset)}


@router.post("/undo")
def undo(
    session: Session = Depends(get_session),
    user: SupabaseAuthUser = Depends(require_admin),
    brand: Optional[str] = Query(default=None),
    tz_offset: int = Query(default=0, ge=-840, le=840),
):
    """Delete this reviewer's most recent decision; its listing is back in the queue.
    For an `entry` decision the listing's previous match comes back (method from
    `reason`, entry and confidence from prev_entry_id / prev_confidence) if it is
    still the manual match the decision made; for a `category` decision the listing's
    category, subtype, verified_fields and reason come back while it still holds the
    call. The identity overlaid stays until the
    next import re-reads the listing. Returns the listing's card (null if it has since left the queue) so the screen
    can show it again."""
    reviewer = _reviewer(user)
    row = session.exec(select(ReviewDecision).where(ReviewDecision.reviewer == reviewer)
                       .order_by(col(ReviewDecision.created_at).desc()).limit(1)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Nothing to undo")
    listing_id = row.listing_id
    if row.decision == "entry":
        listing = session.get(Listing, listing_id)
        if (listing is not None and listing.catalog_match_method == "manual"
                and listing.catalog_entry_id == row.entry_id):
            listing.catalog_entry_id = row.prev_entry_id
            listing.catalog_match_method = row.reason
            listing.catalog_match_confidence = row.prev_confidence
            session.add(listing)
    elif row.decision == "category":
        listing = session.get(Listing, listing_id)
        # Only while the listing still holds the call (an import since keeps it, as a
        # verified field; a person's later edit is theirs).
        if (listing is not None and listing.scraped_category == row.category
                and listing.subtype == row.subtype):
            listing.scraped_category, listing.subtype = row.prev_category, row.prev_subtype
            listing.verified_fields = row.prev_verified
            listing.catalog_match_method = row.reason
            session.add(listing)
    session.delete(row)
    session.commit()

    card = None
    listing = session.get(Listing, listing_id)
    if listing is not None and listing.is_active and listing.catalog_match_method in REVIEW_REASONS:
        card = _card(session, listing, session.get(Dispensary, listing.dispensary_id), _catalogs(session))
    return {"listing_id": str(listing_id), "card": card,
            "progress": _progress(session, reviewer, brand, tz_offset)}
