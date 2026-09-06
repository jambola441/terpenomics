"""
brand_catalogs.py — Admin CRUD over a brand's own product list, plus the export.

A brand catalog is the products a brand says it makes, acquired from its storefront
(scripts/brand_catalog.py) and held in Postgres, which is the system of record. See
evals/enrich/CATALOG.md for why it exists at all: enrichment extracts fields from a
listing name with a model, so every quality number in the repo is computed from the
same output it judges, and the catalog is the first external referent.

Two rules shape almost every handler here, and neither is a preference:

**Entries are never deleted.** `listings.catalog_entry_id` is a foreign key to
`brand_catalog_entries`, so a delete would dangle it and destroy the record of what
was on the menu. "Remove" means `is_active = False`, with `last_seen_at` left where
it was — a human hiding a row is not evidence about when the source last showed it.
Staleness is a state, not a deletion.

**`first_seen_at` and the `verified_*` columns are never rewritten by an edit.** A
human sign-off, and the record of when we first saw a product, survive a re-fetch
(see `push` in scripts/brand_catalog.py) and must equally survive an admin edit. The
update payloads simply do not carry those fields, and `extra="forbid"` turns an
attempt to send them into a 422 rather than a silent no-op.

The export
----------
`data/catalogs/<brand_slug>.json` is a generated artifact, and it — not this table —
is what scripts/catalog_enricher.py and scripts/brand_prompt.py read. **An edit made
through this API is invisible to enrichment until the export is regenerated.** That
is the one piece of hidden state in this feature, so it is surfaced rather than
hidden: every catalog response carries an `export` block saying whether the file
agrees with the database and, if not, how many entries differ.
`POST /brand-catalogs/{id}/export` rewrites it.

The file is not a hard boundary — enrich.py already opens its own psycopg2
connection for the brand-examples nudge, best-effort, degrading to {} when
DATABASE_URL is unset. It is that the catalog read path is file-based today, which
makes the export the thing that has to be kept honest.

Regeneration is a merge, not a dump. `product_external_id` and `source_tags` live in
the file but have no column in the table, and `product_external_id` is load-bearing —
catalog_match.py and brand_prompt.py both group variants by it, and Ayrloom sells
'honeycrisp' as a vape, a beverage and a canned drink, so grouping by name instead
would merge distinct products. So those two keys are carried across from the file
being replaced, keyed on `external_id`, and only the columns the table actually owns
are taken from the database.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlmodel import Session, col, or_, select

from auth import SupabaseAuthUser
from database import get_session
from models import BrandCatalog, BrandCatalogEntry, Listing, utcnow_tz
from .auth import require_admin

# scripts/ is not a package; everything in the repo reaches it by path. Imported
# rather than reimplemented: `catalog_path`/`save` decide where the export lives and
# how it is written, `norm_name` is the normalisation matching runs over on both
# sides, and `verification.claim` owns the sign-off shape used on listings. Appended,
# not prepended, so scripts/ can never shadow an installed package.
_SCRIPTS = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.append(_SCRIPTS)

import brand_catalog  # noqa: E402
import verification  # noqa: E402
from scraper_common import slugify  # noqa: E402

router = APIRouter()


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------
#
# `extra="forbid"` everywhere: these tables carry columns an edit must never touch
# (first_seen_at, verified_fields, verified_by, verified_at) and one it must only
# touch through a named action (is_active). A rejected request is a much better
# outcome than a field silently dropped, because the caller would otherwise believe
# the sign-off had been cleared or preserved when neither happened.


class CatalogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str
    # Defaults to slugify(brand_name). It names the export file, so it is part of
    # the catalog's identity rather than a display detail.
    brand_slug: Optional[str] = None
    source_url: Optional[str] = None
    # Tier 4 of the acquisition ladder in CATALOG.md: a catalog created here is
    # hand-curated by definition, since the automated tiers go through
    # scripts/brand_catalog.py.
    source_method: str = "manual"


class CatalogUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: Optional[str] = None
    brand_slug: Optional[str] = None
    source_url: Optional[str] = None
    source_method: Optional[str] = None


class EntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # Left NULL unless the caller has a real source id, and that is deliberate:
    # `push` deactivates every entry whose external_id is not in the fetched set
    # (`external_id <> ALL(seen)`), and NULL <> ALL(...) is NULL rather than TRUE,
    # so a hand-added entry with no external_id survives the next re-fetch. Inventing
    # a synthetic id here would get the entry deactivated the next time the brand is
    # scraped.
    external_id: Optional[str] = None
    product_line: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    strain: Optional[str] = None
    variant: Optional[str] = None
    attributes: Optional[dict] = None
    match_terms: Optional[list[str]] = None


class EntryUpdate(BaseModel):
    """A field edit. Absent key = leave alone; explicit null = clear the column.

    dispensaries.py uses `if payload.x is not None` for this, which cannot express
    "set this back to NULL". Here it has to: `product_line` being present on some
    stores and absent on others is the split defect the catalog exists to fix
    (1,374 spurious product rows, CATALOG.md §1), so clearing a wrongly-extracted
    line is a normal edit, not an edge case. Handlers read `model_dump(
    exclude_unset=True)` to tell the two apart.
    """

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    product_line: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    strain: Optional[str] = None
    variant: Optional[str] = None
    external_id: Optional[str] = None
    attributes: Optional[dict] = None
    match_terms: Optional[list[str]] = None


class EntryActive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool = False


class EntryVerify(BaseModel):
    """A human sign-off on specific fields of an entry.

    Same shape as listings.verified_fields (scripts/verification.py): per-field,
    because fields are checked at different times by different people, and each claim
    records the name it was checked against so a rename lapses it rather than letting
    a stale claim vouch for a product that has become something else.
    """

    model_config = ConfigDict(extra="forbid")

    # {field: value}, restricted to verification.VERIFIABLE.
    fields: dict[str, Any]
    verified_by: str
    # Fields to withdraw a claim on. Withdrawal is explicit; `fields` merges.
    clear: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _serialize_catalog(c: BrandCatalog, counts: Optional[dict] = None) -> dict:
    counts = counts or {}
    return {
        "id": str(c.id),
        "brand_slug": c.brand_slug,
        "brand_name": c.brand_name,
        "source_url": c.source_url,
        "source_method": c.source_method,
        "fetched_at": _iso(c.fetched_at),
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
        "entry_count": counts.get("entry_count", 0),
        "active_entry_count": counts.get("active_entry_count", 0),
        # How many listings currently resolve to one of this catalog's entries.
        # Also the reason nothing here is ever deleted.
        "listing_count": counts.get("listing_count", 0),
    }


def _serialize_entry(e: BrandCatalogEntry, listing_count: Optional[int] = None) -> dict:
    # A claim is about a (row, name) pair. Renaming an entry lapses its claims rather
    # than silently carrying them onto text nobody read — verification.py's rule,
    # applied here by hashing against this entry's own name.
    row = {"verified_fields": e.verified_fields, "name": e.name}
    return {
        "id": str(e.id),
        "catalog_id": str(e.catalog_id),
        "external_id": e.external_id,
        "name": e.name,
        "product_line": e.product_line,
        "category": e.category,
        "subtype": e.subtype,
        "strain": e.strain,
        "variant": e.variant,
        "attributes": e.attributes,
        "match_terms": list(e.match_terms or []),
        "is_active": e.is_active,
        "first_seen_at": _iso(e.first_seen_at),
        "last_seen_at": _iso(e.last_seen_at),
        "verified_by": e.verified_by,
        "verified_at": _iso(e.verified_at),
        # Live claims; a claim whose name_hash no longer matches shows up in
        # `lapsed_fields` instead and must not be read as verified.
        "verified_fields": verification.verified_fields(row),
        "lapsed_fields": sorted(verification.lapsed_fields(row)),
        "listing_count": listing_count,
    }


# ---------------------------------------------------------------------------
# The generated export, and whether it still agrees with the database
# ---------------------------------------------------------------------------

# Columns the table owns, and therefore the only ones an export takes from the
# database. `product_external_id` and `source_tags` are file-only and are carried
# across from the file being replaced.
_EXPORT_DB_FIELDS = ("external_id", "name", "product_line", "category", "subtype",
                     "strain", "variant", "attributes", "match_terms")


def _entry_key(entry: dict) -> str:
    """Identity of an entry for diffing file against database.

    `external_id` when there is one — it is the source's own variant id and the key
    `push` upserts on. Hand-added entries deliberately have none (see EntryCreate),
    so they fall back to name+variant, which is what distinguishes them in the UI too.
    """
    ext = entry.get("external_id")
    if ext:
        return f"ext:{ext}"
    return f"nv:{brand_catalog.norm_name(entry.get('name') or '')}|" \
           f"{brand_catalog.norm_name(entry.get('variant') or '')}"


def _comparable(entry: dict) -> tuple:
    """The part of an entry the database is authoritative about, order-insensitive."""
    return tuple(
        tuple(sorted(entry.get(f) or [])) if f == "match_terms"
        else json.dumps(entry.get(f), sort_keys=True) if f == "attributes"
        else entry.get(f)
        for f in _EXPORT_DB_FIELDS
    )


def _rel(path: Path) -> str:
    """Repo-relative path for display, falling back to the absolute one.

    `Path.relative_to` raises rather than degrading when the target is outside the
    root, and a display string is not worth a 500.
    """
    try:
        return str(path.relative_to(brand_catalog.ROOT))
    except ValueError:
        return str(path)


def _read_export(brand_slug: str) -> Optional[dict]:
    """The export file as it stands, or None when it is missing or unreadable.

    Unreadable is treated as missing rather than raised, for the same reason
    catalog_enricher skips a malformed catalog: a bad file must not take out the
    admin screen that exists to fix it.
    """
    path = brand_catalog.catalog_path(brand_slug)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_export(session: Session, catalog: BrandCatalog) -> dict:
    """The export document this catalog's rows imply, without writing anything.

    Only active entries are exported. A deactivated entry is a product the brand has
    stopped selling or a human has taken out; the row stays for the foreign key and
    the history, but offering it to the model as a real product would be wrong.
    """
    entries = session.exec(
        select(BrandCatalogEntry)
        .where(BrandCatalogEntry.catalog_id == catalog.id)
        .where(BrandCatalogEntry.is_active == True)  # noqa: E712
        .order_by(col(BrandCatalogEntry.name), col(BrandCatalogEntry.variant))
    ).all()

    previous = _read_export(catalog.brand_slug) or {}
    prev_entries = previous.get("entries") or []
    # Keyed for carry-over, and indexed for ordering: keeping the file's existing
    # order means a regeneration after a field edit produces a one-line diff rather
    # than a reshuffle of several hundred.
    carried: dict[str, dict] = {}
    position: dict[str, int] = {}
    for i, fe in enumerate(prev_entries):
        if isinstance(fe, dict):
            key = _entry_key(fe)
            carried[key] = fe
            position.setdefault(key, i)

    out: list[dict] = []
    for e in entries:
        row = {
            "external_id": e.external_id,
            "name": e.name,
            "product_line": e.product_line,
            "category": e.category,
            "subtype": e.subtype,
            "strain": e.strain,
            "variant": e.variant,
            "attributes": e.attributes,
            "match_terms": list(e.match_terms or []),
        }
        prev = carried.get(_entry_key(row)) or {}
        out.append({
            "external_id": row["external_id"],
            # File-only, and load-bearing: catalog_match.py and brand_prompt.py both
            # group a product's variants by it. Nothing in the table holds it, so it
            # can only be carried across.
            "product_external_id": prev.get("product_external_id"),
            "name": row["name"],
            "product_line": row["product_line"],
            "category": row["category"],
            "subtype": row["subtype"],
            "strain": row["strain"],
            "variant": row["variant"],
            "attributes": row["attributes"],
            "match_terms": row["match_terms"],
            "source_tags": prev.get("source_tags"),
        })

    out.sort(key=lambda r: (position.get(_entry_key(r), len(prev_entries)),
                            r["name"] or "", r["variant"] or ""))

    # Source products, not variants — the same grouping catalog_match.py and
    # brand_prompt.py use: by product id, falling back to name. Note this can differ
    # from the number a `fetch` wrote: `fetch` counts what the storefront returned,
    # including products it then dropped from `entries` (a promotional
    # "Beverage (100% off)" placeholder, a product with no variants), whereas this
    # counts products actually present. Ayrloom is 65 fetched, 63 present.
    product_count = len({e.get("product_external_id") or f"name:{e['name']}" for e in out})

    return {
        "brand_slug": catalog.brand_slug,
        "brand_name": catalog.brand_name,
        "source_url": catalog.source_url,
        "source_method": catalog.source_method,
        "fetched_at": _iso(catalog.fetched_at),
        "product_count": product_count,
        "entries": out,
    }


def export_status(session: Session, catalog: BrandCatalog) -> dict:
    """Whether data/catalogs/<slug>.json still says what the database says.

    This is the whole point of the block: an edit here does not reach enrichment,
    which reads the file. Anything other than `in_sync: true` means the model is
    still being shown the old catalog.
    """
    path = brand_catalog.catalog_path(catalog.brand_slug)
    doc = build_export(session, catalog)
    on_disk = _read_export(catalog.brand_slug)

    base = {
        "path": _rel(path),
        "file_exists": path.is_file(),
        "file_readable": on_disk is not None,
        "file_generated_at": (
            datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
            if path.is_file() else None
        ),
        "db_entry_count": len(doc["entries"]),
    }

    if on_disk is None:
        return {
            **base,
            "in_sync": False,
            "file_entry_count": None,
            "metadata_changed": True,
            "added": len(doc["entries"]),
            "removed": 0,
            "changed": 0,
            "sample": [{"kind": "added", "name": e["name"], "variant": e["variant"]}
                       for e in doc["entries"][:10]],
        }

    file_entries = [e for e in (on_disk.get("entries") or []) if isinstance(e, dict)]
    db_by_key = {_entry_key(e): e for e in doc["entries"]}
    file_by_key = {_entry_key(e): e for e in file_entries}

    added = [k for k in db_by_key if k not in file_by_key]
    removed = [k for k in file_by_key if k not in db_by_key]
    changed = [k for k in db_by_key
               if k in file_by_key and _comparable(db_by_key[k]) != _comparable(file_by_key[k])]

    metadata_changed = any(
        doc[f] != on_disk.get(f)
        for f in ("brand_slug", "brand_name", "source_url", "source_method", "fetched_at")
    )

    sample = (
        [{"kind": "added", "name": db_by_key[k]["name"], "variant": db_by_key[k]["variant"]}
         for k in added[:4]]
        + [{"kind": "removed", "name": file_by_key[k]["name"], "variant": file_by_key[k].get("variant")}
           for k in removed[:4]]
        + [{"kind": "changed", "name": db_by_key[k]["name"], "variant": db_by_key[k]["variant"]}
           for k in changed[:4]]
    )

    return {
        **base,
        "file_entry_count": len(file_entries),
        "added": len(added),
        "removed": len(removed),
        "changed": len(changed),
        "metadata_changed": metadata_changed,
        "in_sync": not (added or removed or changed or metadata_changed),
        "sample": sample,
    }


# ---------------------------------------------------------------------------
# Shared queries
# ---------------------------------------------------------------------------


def _get_catalog(session: Session, catalog_id: UUID) -> BrandCatalog:
    catalog = session.get(BrandCatalog, catalog_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="catalog not found")
    return catalog


def _get_entry(session: Session, catalog_id: UUID, entry_id: UUID) -> BrandCatalogEntry:
    entry = session.get(BrandCatalogEntry, entry_id)
    # Checked against the path's catalog rather than trusted: an entry id from one
    # catalog arriving on another's URL is a bug somewhere, not a request to serve.
    if not entry or entry.catalog_id != catalog_id:
        raise HTTPException(status_code=404, detail="catalog entry not found")
    return entry


def _catalog_counts(session: Session, catalog_ids: list[UUID]) -> dict[UUID, dict]:
    """Entry and resolved-listing counts, one grouped query each."""
    counts: dict[UUID, dict] = {
        cid: {"entry_count": 0, "active_entry_count": 0, "listing_count": 0}
        for cid in catalog_ids
    }
    if not catalog_ids:
        return counts

    rows = session.exec(
        select(
            BrandCatalogEntry.catalog_id,
            func.count().label("total"),
            func.count().filter(BrandCatalogEntry.is_active == True).label("active"),  # noqa: E712
        )
        .where(col(BrandCatalogEntry.catalog_id).in_(catalog_ids))
        .group_by(col(BrandCatalogEntry.catalog_id))
    ).all()
    for cid, total, active in rows:
        counts[cid]["entry_count"] = total
        counts[cid]["active_entry_count"] = active

    rows = session.exec(
        select(BrandCatalogEntry.catalog_id, func.count())
        .join(Listing, col(Listing.catalog_entry_id) == col(BrandCatalogEntry.id))
        .where(col(BrandCatalogEntry.catalog_id).in_(catalog_ids))
        .group_by(col(BrandCatalogEntry.catalog_id))
    ).all()
    for cid, total in rows:
        counts[cid]["listing_count"] = total

    return counts


def _entry_listing_counts(session: Session, entry_ids: list[UUID]) -> dict[UUID, int]:
    if not entry_ids:
        return {}
    rows = session.exec(
        select(Listing.catalog_entry_id, func.count())
        .where(col(Listing.catalog_entry_id).in_(entry_ids))
        .group_by(col(Listing.catalog_entry_id))
    ).all()
    return {eid: n for eid, n in rows}


def _query_entries(
    session: Session,
    catalog_id: UUID,
    q: Optional[str],
    category: Optional[str],
    is_active: Optional[bool],
    limit: int,
    offset: int,
) -> dict:
    """One page of entries plus the unpaginated total.

    A catalog runs to hundreds of entries (Ayrloom: 172), so the total is a separate
    count rather than len(rows) — the UI needs to say "48 of 172" while showing 50.
    """
    conditions = [BrandCatalogEntry.catalog_id == catalog_id]
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                col(BrandCatalogEntry.name).ilike(like),
                col(BrandCatalogEntry.strain).ilike(like),
                col(BrandCatalogEntry.product_line).ilike(like),
                col(BrandCatalogEntry.variant).ilike(like),
                col(BrandCatalogEntry.external_id).ilike(like),
            )
        )
    if category:
        if category == "__null__":
            conditions.append(col(BrandCatalogEntry.category).is_(None))
        else:
            conditions.append(BrandCatalogEntry.category == category)
    if is_active is not None:
        conditions.append(BrandCatalogEntry.is_active == is_active)

    total = session.exec(
        select(func.count()).select_from(BrandCatalogEntry).where(*conditions)
    ).one()

    rows = session.exec(
        select(BrandCatalogEntry)
        .where(*conditions)
        .order_by(col(BrandCatalogEntry.name), col(BrandCatalogEntry.variant))
        .offset(offset)
        .limit(limit)
    ).all()

    listing_counts = _entry_listing_counts(session, [r.id for r in rows])
    return {
        "total": total,
        "entries": [_serialize_entry(r, listing_counts.get(r.id, 0)) for r in rows],
    }


def _categories(session: Session, catalog_id: UUID) -> list[str]:
    rows = session.exec(
        select(BrandCatalogEntry.category)
        .where(BrandCatalogEntry.catalog_id == catalog_id)
        .where(col(BrandCatalogEntry.category).is_not(None))
        .distinct()
    ).all()
    return sorted(r for r in rows if r)


# ---------------------------------------------------------------------------
# Catalogs
# ---------------------------------------------------------------------------


@router.get("/brand-catalogs")
def list_brand_catalogs(
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(BrandCatalog)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                col(BrandCatalog.brand_name).ilike(like),
                col(BrandCatalog.brand_slug).ilike(like),
            )
        )
    catalogs = session.exec(
        stmt.order_by(col(BrandCatalog.brand_name)).offset(offset).limit(limit)
    ).all()

    counts = _catalog_counts(session, [c.id for c in catalogs])
    return [
        {
            **_serialize_catalog(c, counts.get(c.id)),
            # Cheap enough to include per row: the file is read once and diffed in
            # memory, and a list that does not say which catalogs are stale would
            # hide the one thing an operator needs to see before trusting them.
            "export": export_status(session, c),
        }
        for c in catalogs
    ]


@router.post("/brand-catalogs")
def create_brand_catalog(
    payload: CatalogCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Create an empty catalog by hand — tier 4 of the acquisition ladder.

    The automated tiers go through `scripts/brand_catalog.py fetch`, which creates the
    catalog as a side effect of the push. This exists for brands with no usable
    storefront, where the list has to be typed in.
    """
    brand_name = payload.brand_name.strip()
    if not brand_name:
        raise HTTPException(status_code=400, detail="brand_name is required")
    brand_slug = (payload.brand_slug or "").strip() or slugify(brand_name)

    existing = session.exec(
        select(BrandCatalog).where(BrandCatalog.brand_slug == brand_slug)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="brand_slug already in use")

    catalog = BrandCatalog(
        brand_slug=brand_slug,
        brand_name=brand_name,
        source_url=payload.source_url,
        source_method=payload.source_method.strip() or "manual",
    )
    session.add(catalog)
    session.commit()
    session.refresh(catalog)
    return {
        **_serialize_catalog(catalog, _catalog_counts(session, [catalog.id]).get(catalog.id)),
        "export": export_status(session, catalog),
    }


@router.get("/brand-catalogs/{catalog_id}")
def get_brand_catalog(
    catalog_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None, description="'__null__' for uncategorised"),
    is_active: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    catalog = _get_catalog(session, catalog_id)
    page = _query_entries(session, catalog_id, q, category, is_active, limit, offset)
    return {
        "catalog": _serialize_catalog(
            catalog, _catalog_counts(session, [catalog_id]).get(catalog_id)
        ),
        "categories": _categories(session, catalog_id),
        "export": export_status(session, catalog),
        **page,
    }


@router.post("/brand-catalogs/{catalog_id}")
def update_brand_catalog(
    catalog_id: UUID,
    payload: CatalogUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    catalog = _get_catalog(session, catalog_id)
    data = payload.model_dump(exclude_unset=True)

    if "brand_name" in data:
        name = (data["brand_name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="brand_name cannot be empty")
        catalog.brand_name = name
    if "brand_slug" in data:
        slug = (data["brand_slug"] or "").strip()
        if not slug:
            raise HTTPException(status_code=400, detail="brand_slug cannot be empty")
        conflict = session.exec(
            select(BrandCatalog).where(
                BrandCatalog.brand_slug == slug, BrandCatalog.id != catalog_id
            )
        ).first()
        if conflict:
            raise HTTPException(status_code=409, detail="brand_slug already in use")
        # The slug names the export file. Renaming it does not move or delete the old
        # file — enrichment loads every *.json in data/catalogs, so the stale one
        # keeps being read until it is removed by hand. Reported, not guessed at.
        catalog.brand_slug = slug
    if "source_url" in data:
        catalog.source_url = data["source_url"]
    if "source_method" in data:
        method = (data["source_method"] or "").strip()
        if not method:
            raise HTTPException(status_code=400, detail="source_method cannot be empty")
        catalog.source_method = method

    # fetched_at is not editable: it records when the source was last read, and only
    # a fetch can know that.
    catalog.updated_at = utcnow_tz()
    session.add(catalog)
    session.commit()
    session.refresh(catalog)
    return {
        **_serialize_catalog(catalog, _catalog_counts(session, [catalog_id]).get(catalog_id)),
        "export": export_status(session, catalog),
    }


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


@router.get("/brand-catalogs/{catalog_id}/entries")
def list_catalog_entries(
    catalog_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None, description="'__null__' for uncategorised"),
    is_active: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    _get_catalog(session, catalog_id)
    return _query_entries(session, catalog_id, q, category, is_active, limit, offset)


@router.post("/brand-catalogs/{catalog_id}/entries")
def create_catalog_entry(
    catalog_id: UUID,
    payload: EntryCreate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    catalog = _get_catalog(session, catalog_id)

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    external_id = (payload.external_id or "").strip() or None
    if external_id:
        clash = session.exec(
            select(BrandCatalogEntry).where(
                BrandCatalogEntry.catalog_id == catalog_id,
                BrandCatalogEntry.external_id == external_id,
            )
        ).first()
        if clash:
            raise HTTPException(
                status_code=409,
                detail="external_id already used in this catalog",
            )

    # Seeded the way `fetch` seeds it, so a hand-added entry is indexed like a
    # fetched one. Not recomputed on later renames: match_terms is the place to put
    # aliases a human curated ('alaskan thunder fuck' for a self-censored title), and
    # silently rewriting it would throw those away.
    match_terms = payload.match_terms
    if match_terms is None:
        match_terms = sorted({brand_catalog.norm_name(name)})

    entry = BrandCatalogEntry(
        catalog_id=catalog.id,
        external_id=external_id,
        name=name,
        product_line=payload.product_line,
        category=payload.category,
        subtype=payload.subtype,
        strain=payload.strain,
        variant=payload.variant,
        attributes=payload.attributes,
        match_terms=match_terms,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _serialize_entry(entry, 0)


@router.get("/brand-catalogs/{catalog_id}/entries/{entry_id}")
def get_catalog_entry(
    catalog_id: UUID,
    entry_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    entry = _get_entry(session, catalog_id, entry_id)
    return _serialize_entry(entry, _entry_listing_counts(session, [entry.id]).get(entry.id, 0))


@router.post("/brand-catalogs/{catalog_id}/entries/{entry_id}")
def update_catalog_entry(
    catalog_id: UUID,
    entry_id: UUID,
    payload: EntryUpdate,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Edit an entry's fields.

    Not touched here, by design, and not accepted in the payload:
      first_seen_at   — when we first saw the product; an edit is not a first sighting
      last_seen_at    — when the *source* last showed it; an edit is not a sighting
      verified_*      — a human sign-off outranks an edit, exactly as it outranks a
                        re-fetch and a re-enrichment (scripts/verification.py)
      is_active       — deactivation is a named action, below
    """
    entry = _get_entry(session, catalog_id, entry_id)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        entry.name = name
    if "external_id" in data:
        external_id = (data["external_id"] or "").strip() or None
        if external_id and external_id != entry.external_id:
            clash = session.exec(
                select(BrandCatalogEntry).where(
                    BrandCatalogEntry.catalog_id == catalog_id,
                    BrandCatalogEntry.external_id == external_id,
                    BrandCatalogEntry.id != entry_id,
                )
            ).first()
            if clash:
                raise HTTPException(
                    status_code=409, detail="external_id already used in this catalog"
                )
        entry.external_id = external_id

    for field in ("product_line", "category", "subtype", "strain", "variant"):
        if field in data:
            value = data[field]
            setattr(entry, field, value.strip() or None if isinstance(value, str) else value)

    if "attributes" in data:
        entry.attributes = data["attributes"]
    if "match_terms" in data:
        terms = data["match_terms"]
        entry.match_terms = sorted({t.strip() for t in terms if t and t.strip()}) if terms else None

    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _serialize_entry(entry, _entry_listing_counts(session, [entry.id]).get(entry.id, 0))


@router.post("/brand-catalogs/{catalog_id}/entries/{entry_id}/deactivate")
def set_catalog_entry_active(
    catalog_id: UUID,
    entry_id: UUID,
    payload: EntryActive,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Take an entry out of the catalog, or put it back. Never a delete.

    `listings.catalog_entry_id` points here. Deleting the row would dangle that
    foreign key and destroy the record of what 538 listings resolved to, so removal
    is a flag. `last_seen_at` is left exactly as it was: it records when the *source*
    last offered the product, and a person hiding a row is not evidence about that.
    """
    entry = _get_entry(session, catalog_id, entry_id)
    entry.is_active = payload.is_active
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _serialize_entry(entry, _entry_listing_counts(session, [entry.id]).get(entry.id, 0))


@router.post("/brand-catalogs/{catalog_id}/entries/{entry_id}/verify")
def verify_catalog_entry(
    catalog_id: UUID,
    entry_id: UUID,
    payload: EntryVerify,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Sign off on specific fields of an entry.

    The only endpoint that writes the verified_* columns — every other write path
    leaves them alone. Worth far more here than on a listing: one sign-off on a
    catalog entry covers every store carrying that product, rather than one store's
    row (CATALOG.md, 'Proposed shape').

    Claims merge, so verifying `strain` today does not withdraw last week's claim
    about `variant`; withdrawal goes through `clear`.
    """
    entry = _get_entry(session, catalog_id, entry_id)
    by = payload.verified_by.strip()
    if not by:
        raise HTTPException(status_code=400, detail="verified_by is required")

    existing = dict(entry.verified_fields or {})
    for field in payload.clear or []:
        existing.pop(field, None)

    if payload.fields:
        try:
            existing = verification.claim(payload.fields, entry.name, by, existing)
        except ValueError as exc:
            # verification.VERIFIABLE is the authority on what can be signed off.
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    entry.verified_fields = existing or None
    entry.verified_by = by if existing else None
    entry.verified_at = utcnow_tz() if existing else None
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _serialize_entry(entry, _entry_listing_counts(session, [entry.id]).get(entry.id, 0))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.get("/brand-catalogs/{catalog_id}/export")
def get_catalog_export_status(
    catalog_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Does data/catalogs/<slug>.json still agree with the database?

    Anything other than `in_sync: true` means enrichment is being shown a catalog
    that no longer matches what is stored here.
    """
    return export_status(session, _get_catalog(session, catalog_id))


@router.post("/brand-catalogs/{catalog_id}/export")
def regenerate_catalog_export(
    catalog_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """Rewrite data/catalogs/<slug>.json from the database.

    This is what makes an edit visible to enrichment. Written through
    brand_catalog.save so the file's location and formatting stay owned by one place.
    """
    catalog = _get_catalog(session, catalog_id)
    doc = build_export(session, catalog)
    try:
        path = brand_catalog.save(doc)
    except OSError as exc:
        # Worth a specific error: the API may well be running somewhere the repo
        # checkout is read-only, in which case the export has to be regenerated
        # where the file actually lives.
        raise HTTPException(
            status_code=500,
            detail=f"could not write {brand_catalog.catalog_path(catalog.brand_slug)}: {exc}",
        ) from exc

    return {
        "written": _rel(path),
        "entry_count": len(doc["entries"]),
        "product_count": doc["product_count"],
        "export": export_status(session, catalog),
    }
