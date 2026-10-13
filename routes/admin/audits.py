"""
audits.py — The admin audits: brand health, audit runs, proposals.

The loop (owner's design, 2026-10-13): a run flags listings of the brands picked
(scripts/data_health.py detectors: price-outlier, odd-title, price) plus a random sample
of trusted listings; each item is judged right / wrong / unsure by a person here or by
the Claude model picked for the run; a wrong one gets a listing fix (manual match, store
error) or a catalog proposal; a proposal is measured as a dry run, approved or rejected
here, then applied, the brand's grid synced and its listings re-matched, and logged.

This API stays thin, as the rest of the admin API: it reads and writes the audit rows
and queues jobs (audit_jobs). Everything that reads the pipeline's data or changes the
catalog runs in the worker (scripts/audit_worker.py -> scripts/audits.py). The two
direct listing fixes reuse the review queue's manual-match path (review.make_manual)
and only record a store error. Nothing applies without an admin's approval.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlmodel import Session, col, select

from auth import SupabaseAuthUser
from database import get_session
from models import (
    PROPOSAL_KINDS, TRUSTED_MATCH_METHODS,
    AuditItem, AuditJob, AuditLog, AuditProposal, AuditRun, BrandCatalog, BrandCatalogEntry,
    Listing, utcnow,
)
from .auth import require_admin
from .review import _candidates, _reviewer, _brand_groups, make_manual

_SCRIPTS = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.append(_SCRIPTS)

from catalog_store import brand_key  # noqa: E402
import audit_judge  # noqa: E402

router = APIRouter(prefix="/audits")

MAX_SAMPLE = 200
RECENT_RUNS = 300
OPEN_PROPOSALS = ("measuring", "measured", "approved", "applying")
# Rough tokens one judged item costs (evidence JSON + instructions in, verdict out),
# for the estimate on the "Run audit" form; the run records what it really cost.
EST_INPUT_TOKENS, EST_OUTPUT_TOKENS = 4500, 600


def enqueue(session: Session, kind: str, **payload) -> AuditJob:
    job = AuditJob(kind=kind, payload={k: str(v) for k, v in payload.items()})
    session.add(job)
    return job


def _log(session: Session, actor: str, action: str, brand: Optional[str], target_kind: str, target_id,
         before: Optional[dict], after: Optional[dict]) -> None:
    session.add(AuditLog(actor=actor, action=action, brand=brand, target_kind=target_kind,
                         target_id=str(target_id), before=before, after=after))


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def _rate(items: list[AuditItem]) -> dict:
    """Judged counts and the error rate: wrong / (right + wrong); unsure counted apart."""
    c = Counter(i.verdict for i in items if i.verdict)
    decided = c["right"] + c["wrong"]
    return {"items": len(items), "judged": sum(c.values()), "right": c["right"], "wrong": c["wrong"],
            "unsure": c["unsure"], "error_rate": round(c["wrong"] / decided, 3) if decided else None}


def summarize(items: list[AuditItem]) -> dict:
    """The run's error rate overall, on the random sample (the estimate for the brand's
    trusted listings) and on the flagged items, and each flag kind's precision: of the
    items it flagged and a judge decided, the share that were wrong."""
    by_flag: dict[str, list[AuditItem]] = defaultdict(list)
    for i in items:
        for kind in {f.get("kind") for f in i.flags or []}:
            by_flag[kind].append(i)
    precision = {}
    for kind, rows in sorted(by_flag.items()):
        r = _rate(rows)
        precision[kind] = {**r, "precision": r["error_rate"]}
    return {"all": _rate(items), "sample": _rate([i for i in items if i.source == "sample"]),
            "flagged": _rate([i for i in items if i.source == "flag"]), "flags": precision,
            "causes": dict(Counter(i.cause for i in items if i.verdict == "wrong" and i.cause))}


def _unresolved(item: AuditItem, proposed: set[UUID]) -> bool:
    return item.verdict is None or (item.verdict == "wrong" and not item.fix and item.id not in proposed)


def _run_dict(run: AuditRun) -> dict:
    return {"id": str(run.id), "brands": run.brands, "sample_size": run.sample_size,
            "judge_model": run.judge_model,
            "judge_label": audit_judge.MODELS.get(run.judge_model or "", {}).get("label"),
            "status": run.status, "created_by": run.created_by, "created_at": run.created_at,
            "finished_at": run.finished_at, "total_items": run.total_items, "judged_items": run.judged_items,
            "input_tokens": run.input_tokens, "output_tokens": run.output_tokens,
            "cost_usd": round(run.cost_usd or 0, 4), "error": run.error}


def _item_dict(i: AuditItem, proposals: list[AuditProposal]) -> dict:
    return {"id": str(i.id), "listing_id": str(i.listing_id), "brand": i.brand, "source": i.source,
            "flags": i.flags or [], "evidence": i.evidence or {}, "verdict": i.verdict, "cause": i.cause,
            "explanation": i.explanation, "proposed_fix": i.proposed_fix, "judged_by": i.judged_by,
            "judged_at": i.judged_at, "fix": i.fix,
            "proposals": [{"id": str(p.id), "kind": p.kind, "status": p.status} for p in proposals]}


def _proposal_dict(p: AuditProposal) -> dict:
    return {"id": str(p.id), "run_id": str(p.run_id) if p.run_id else None,
            "item_id": str(p.item_id) if p.item_id else None, "brand": p.brand, "kind": p.kind,
            "params": p.params, "why": p.why, "status": p.status, "measure": p.measure,
            "measured_at": p.measured_at, "created_by": p.created_by, "created_at": p.created_at,
            "decided_by": p.decided_by, "decided_at": p.decided_at, "applied_at": p.applied_at,
            "result": p.result, "error": p.error}


# ---------------------------------------------------------------------------
# Brand health
# ---------------------------------------------------------------------------

@router.get("/models")
def models(_: SupabaseAuthUser = Depends(require_admin), sample_size: int = Query(default=20, ge=1, le=MAX_SAMPLE)):
    """The judge models, with a rough cost per item and for a run of `sample_size`
    items plus the usual handful of flags."""
    out = []
    for model, m in audit_judge.MODELS.items():
        per_item = audit_judge.cost(model, EST_INPUT_TOKENS, EST_OUTPUT_TOKENS)
        out.append({"id": model, "label": m["label"], "price_per_mtok": list(m["price"]),
                    "est_per_item_usd": round(per_item, 5),
                    "est_run_usd": round(per_item * (sample_size + 10), 4)})
    return {"models": out, "default": audit_judge.DEFAULT_MODEL}


@router.get("/brands")
def brand_health(session: Session = Depends(get_session), _: SupabaseAuthUser = Depends(require_admin)):
    """Per catalog brand: active listings, trusted share, review backlog, the last audit
    (when, error rate on its sample and overall), its unresolved flags, open proposals."""
    catalogs = {brand_key(c.brand_name): c for c in session.exec(select(BrandCatalog)).all()}
    counts: dict[str, Counter] = defaultdict(Counter)
    for name, method, n in session.exec(
            select(Listing.scraped_brand, Listing.catalog_match_method, func.count())
            .where(Listing.is_active == True)  # noqa: E712
            .group_by(Listing.scraped_brand, Listing.catalog_match_method)).all():
        key = brand_key(name)
        if key in catalogs:
            counts[key]["total"] += n
            if method in TRUSTED_MATCH_METHODS:
                counts[key]["trusted"] += n
    backlog = {g["key"]: g["remaining"] for g in _brand_groups(session)}
    runs = session.exec(select(AuditRun).order_by(col(AuditRun.created_at).desc()).limit(RECENT_RUNS)).all()
    last: dict[str, AuditRun] = {}
    for run in runs:
        for b in run.brands or []:
            last.setdefault(brand_key(b), run)
    run_ids = list({r.id for r in last.values()})
    items = session.exec(select(AuditItem).where(col(AuditItem.run_id).in_(run_ids))).all() if run_ids else []
    proposals = session.exec(select(AuditProposal)).all()
    proposed = {p.item_id for p in proposals if p.item_id}
    open_by_brand = Counter(brand_key(p.brand) for p in proposals if p.status in OPEN_PROPOSALS)
    out = []
    for key, c in catalogs.items():
        run = last.get(key)
        mine = [i for i in items if run and i.run_id == run.id and brand_key(i.brand) == key]
        total = counts[key]["total"]
        out.append({
            "brand": c.brand_name, "catalog_id": str(c.id), "listings": total,
            "trusted": counts[key]["trusted"],
            "trusted_pct": round(100 * counts[key]["trusted"] / total, 1) if total else None,
            "review_backlog": backlog.get(key, 0),
            "last_audit": {**_run_dict(run), "sample": _rate([i for i in mine if i.source == "sample"]),
                           "all": _rate(mine)} if run else None,
            "open_flags": sum(1 for i in mine if i.source == "flag" and _unresolved(i, proposed)),
            "open_proposals": open_by_brand.get(key, 0),
        })
    out.sort(key=lambda b: (-(b["listings"] or 0), b["brand"].lower()))
    return {"brands": out}


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brands: list[str] = Field(min_length=1, max_length=50)
    sample_size: int = Field(default=20, ge=0, le=MAX_SAMPLE)
    # A Claude model (audit_judge.MODELS), or None to judge by hand.
    judge_model: Optional[str] = None


@router.post("/runs")
def create_run(body: RunIn, session: Session = Depends(get_session), user: SupabaseAuthUser = Depends(require_admin)):
    if body.judge_model and body.judge_model not in audit_judge.MODELS:
        raise HTTPException(status_code=422, detail="judge_model must be one of " + ", ".join(audit_judge.MODELS))
    catalogs = {brand_key(c.brand_name): c for c in session.exec(select(BrandCatalog)).all()}
    unknown = [b for b in body.brands if brand_key(b) not in catalogs]
    if unknown:
        raise HTTPException(status_code=422, detail=f"No catalog for: {', '.join(unknown)}")
    run = AuditRun(brands=[catalogs[brand_key(b)].brand_name for b in dict.fromkeys(body.brands)],
                   sample_size=body.sample_size, judge_model=body.judge_model, created_by=_reviewer(user))
    session.add(run)
    session.flush()
    enqueue(session, "build_run", run_id=run.id)
    session.commit()
    return _run_dict(run)


@router.get("/runs")
def list_runs(session: Session = Depends(get_session), _: SupabaseAuthUser = Depends(require_admin),
              brand: Optional[str] = Query(default=None), limit: int = Query(default=50, ge=1, le=RECENT_RUNS)):
    runs = session.exec(select(AuditRun).order_by(col(AuditRun.created_at).desc()).limit(RECENT_RUNS)).all()
    if brand:
        runs = [r for r in runs if brand_key(brand) in {brand_key(b) for b in r.brands or []}]
    return {"runs": [_run_dict(r) for r in runs[:limit]]}


def _get_run(session: Session, run_id: UUID) -> AuditRun:
    run = session.get(AuditRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Audit run not found")
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, session: Session = Depends(get_session), _: SupabaseAuthUser = Depends(require_admin)):
    """The run, its items (flagged first), the summary, and whether a job is pending."""
    run = _get_run(session, run_id)
    items = session.exec(select(AuditItem).where(AuditItem.run_id == run.id)
                         .order_by(col(AuditItem.source), col(AuditItem.created_at))).all()
    proposals = session.exec(select(AuditProposal).where(AuditProposal.run_id == run.id)).all()
    by_item: dict[UUID, list[AuditProposal]] = defaultdict(list)
    for p in proposals:
        if p.item_id:
            by_item[p.item_id].append(p)
    pending = session.exec(select(AuditJob).where(col(AuditJob.status).in_(("queued", "running")))).all()
    return {"run": _run_dict(run), "summary": summarize(items),
            "items": [_item_dict(i, by_item.get(i.id, [])) for i in items],
            "pending_jobs": [{"kind": j.kind, "status": j.status} for j in pending
                             if j.payload.get("run_id") == str(run.id)]}


class JudgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    judge_model: str


@router.post("/runs/{run_id}/judge")
def judge_run(run_id: UUID, body: JudgeIn, session: Session = Depends(get_session),
              _: SupabaseAuthUser = Depends(require_admin)):
    """Have the LLM judge every item without a verdict, with the model given."""
    if body.judge_model not in audit_judge.MODELS:
        raise HTTPException(status_code=422, detail="judge_model must be one of " + ", ".join(audit_judge.MODELS))
    run = _get_run(session, run_id)
    if run.status in ("queued", "building", "judging"):
        raise HTTPException(status_code=409, detail=f"The run is {run.status}")
    run.judge_model, run.status = body.judge_model, "judging"
    session.add(run)
    enqueue(session, "judge_run", run_id=run.id)
    session.commit()
    return _run_dict(run)


# ---------------------------------------------------------------------------
# Items: a person's verdict, and the two direct listing fixes
# ---------------------------------------------------------------------------

def _get_item(session: Session, item_id: UUID) -> AuditItem:
    item = session.get(AuditItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Audit item not found")
    return item


class VerdictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["right", "wrong", "unsure"]
    cause: Optional[str] = Field(default=None, max_length=64)
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/items/{item_id}/verdict")
def set_verdict(item_id: UUID, body: VerdictIn, session: Session = Depends(get_session),
                user: SupabaseAuthUser = Depends(require_admin)):
    """A person's verdict; it replaces the judge's (which stays in judged_by's history
    only as the explanation it gave, kept unless a note replaces it)."""
    item = _get_item(session, item_id)
    run = session.get(AuditRun, item.run_id)
    had = item.verdict is not None
    item.verdict, item.cause = body.verdict, (body.cause if body.verdict != "right" else None)
    if body.note:
        item.explanation = body.note.strip()
    item.judged_by, item.judged_at = f"manual:{_reviewer(user)}", utcnow()
    session.add(item)
    if run is not None and not had:
        run.judged_items = (run.judged_items or 0) + 1
        session.add(run)
    session.commit()
    return _item_dict(item, [])


@router.get("/items/{item_id}/candidates")
def item_candidates(item_id: UUID, session: Session = Depends(get_session), _: SupabaseAuthUser = Depends(require_admin)):
    """Entries the listing might be (the review queue's candidates), plus the judge's
    pick when it proposed a manual match."""
    item = _get_item(session, item_id)
    listing = session.get(Listing, item.listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    catalog = session.exec(select(BrandCatalog)).all()
    catalog = next((c for c in catalog if brand_key(c.brand_name) == brand_key(item.brand)), None)
    out = _candidates(session, listing, catalog)
    for c in (item.evidence or {}).get("candidates") or []:
        if c and c.get("id") and all(o["id"] != c["id"] for o in out):
            out.append({**c, "suggested": False})
    want = (item.proposed_fix or {}).get("entry_id")
    for c in out:
        c["judge_pick"] = bool(want) and c["id"] == want
    return {"candidates": out}


class ManualMatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_id: UUID


@router.post("/items/{item_id}/manual-match")
def manual_match(item_id: UUID, body: ManualMatchIn, session: Session = Depends(get_session),
                 user: SupabaseAuthUser = Depends(require_admin)):
    """Make the item's listing a manual match to an entry of its brand's catalog (the
    review queue's make_manual), logged with the match it replaced."""
    item = _get_item(session, item_id)
    listing = session.get(Listing, item.listing_id)
    entry = session.get(BrandCatalogEntry, body.entry_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    catalog = next((c for c in session.exec(select(BrandCatalog)).all()
                    if brand_key(c.brand_name) == brand_key(listing.scraped_brand or item.brand)), None)
    if entry is None or catalog is None or entry.catalog_id != catalog.id:
        raise HTTPException(status_code=422, detail="That entry is not in this listing's brand catalog")
    before = {"catalog_entry_id": str(listing.catalog_entry_id) if listing.catalog_entry_id else None,
              "catalog_match_method": listing.catalog_match_method,
              "catalog_match_confidence": listing.catalog_match_confidence}
    make_manual(session, listing, entry)
    actor = _reviewer(user)
    after = {"catalog_entry_id": str(entry.id), "catalog_match_method": "manual", "catalog_match_confidence": 1.0}
    item.fix = {"action": "manual-match", "entry_id": str(entry.id), "entry": f"{entry.name} {entry.variant or ''}".strip(),
                "by": actor, "at": utcnow().isoformat(), "before": before}
    session.add(item)
    _log(session, actor, "manual-match", item.brand, "listing", listing.id, before, after)
    session.commit()
    return _item_dict(item, [])


class StoreErrorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what: Literal["price", "photo", "title"]
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/items/{item_id}/store-error")
def store_error(item_id: UUID, body: StoreErrorIn, session: Session = Depends(get_session),
                user: SupabaseAuthUser = Depends(require_admin)):
    """The match is right; the store's price, photo or title is wrong. Recorded (and
    logged): later runs leave the listing's flags out (scripts/audits.py settled_listings)."""
    item = _get_item(session, item_id)
    actor = _reviewer(user)
    item.fix = {"action": "store-error", "what": body.what, "note": (body.note or "").strip() or None,
                "by": actor, "at": utcnow().isoformat()}
    session.add(item)
    _log(session, actor, "store-error", item.brand, "listing", item.listing_id, None,
         {"what": body.what, "note": item.fix["note"]})
    session.commit()
    return _item_dict(item, [])


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------

class ProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    params: dict[str, Any]
    brand: Optional[str] = None
    why: Optional[str] = Field(default=None, max_length=4000)
    item_id: Optional[UUID] = None


def _check_params(kind: str, params: dict) -> None:
    """The fields each kind needs (the worker refuses the rest when it plans)."""
    need = {"add-product": ("category", "strain", "sizes"), "add-size": ("entry", "size"),
            "rekey": (), "set-subtype": ("entry", "subtype"), "deactivate": ("entry",),
            "manual-match": ("listing_id", "entry"), "add-example": ("listing", "entry"),
            "remove-example": ("example_id",)}[kind]
    missing = [k for k in need if params.get(k) in (None, "", [], {})]
    if kind == "rekey" and not (params.get("entry") or params.get("entries")):
        missing.append("entry")
    if missing:
        raise HTTPException(status_code=422, detail=f"{kind} needs {', '.join(missing)}")


@router.post("/proposals")
def create_proposal(body: ProposalIn, session: Session = Depends(get_session),
                    user: SupabaseAuthUser = Depends(require_admin)):
    """A proposal, measured by the worker before anyone can approve it."""
    if body.kind not in PROPOSAL_KINDS:
        raise HTTPException(status_code=422, detail="kind must be one of " + ", ".join(PROPOSAL_KINDS))
    item = _get_item(session, body.item_id) if body.item_id else None
    brand = body.brand or (item.brand if item else None)
    if not brand:
        raise HTTPException(status_code=422, detail="brand is required without an item")
    _check_params(body.kind, body.params)
    p = AuditProposal(run_id=item.run_id if item else None, item_id=item.id if item else None, brand=brand,
                      kind=body.kind, params=body.params, why=(body.why or "").strip() or None,
                      created_by=_reviewer(user))
    session.add(p)
    session.flush()
    enqueue(session, "measure_proposal", proposal_id=p.id)
    session.commit()
    return _proposal_dict(p)


@router.get("/proposals")
def list_proposals(session: Session = Depends(get_session), _: SupabaseAuthUser = Depends(require_admin),
                   status: Literal["open", "decided", "all"] = Query(default="open"),
                   brand: Optional[str] = Query(default=None)):
    """open: measuring, measured, approved or applying (the queue); decided: the rest."""
    rows = session.exec(select(AuditProposal).order_by(col(AuditProposal.created_at))).all()
    if status == "open":
        rows = [p for p in rows if p.status in OPEN_PROPOSALS]
    elif status == "decided":
        rows = [p for p in rows if p.status not in OPEN_PROPOSALS][::-1]
    if brand:
        rows = [p for p in rows if brand_key(p.brand) == brand_key(brand)]
    items = {i.id: i for i in session.exec(select(AuditItem).where(
        col(AuditItem.id).in_([p.item_id for p in rows if p.item_id]))).all()} if rows else {}
    return {"proposals": [{**_proposal_dict(p), "item": _item_dict(items[p.item_id], []) if p.item_id in items else None}
                          for p in rows]}


def _get_proposal(session: Session, proposal_id: UUID) -> AuditProposal:
    p = session.get(AuditProposal, proposal_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return p


class ProposalEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    params: Optional[dict[str, Any]] = None
    why: Optional[str] = Field(default=None, max_length=4000)


@router.patch("/proposals/{proposal_id}")
def edit_proposal(proposal_id: UUID, body: ProposalEdit, session: Session = Depends(get_session),
                  user: SupabaseAuthUser = Depends(require_admin)):
    """Edit and re-measure: the old measure no longer says what this would do."""
    p = _get_proposal(session, proposal_id)
    if p.status not in ("measuring", "measured", "failed"):
        raise HTTPException(status_code=409, detail=f"The proposal is {p.status}")
    if body.params is not None:
        _check_params(p.kind, body.params)
        p.params = body.params
    if body.why is not None:
        p.why = body.why.strip() or None
    p.status, p.measure, p.measured_at, p.error = "measuring", None, None, None
    session.add(p)
    enqueue(session, "measure_proposal", proposal_id=p.id)
    session.commit()
    return _proposal_dict(p)


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: UUID, session: Session = Depends(get_session), user: SupabaseAuthUser = Depends(require_admin)):
    """Approve a measured proposal; the worker applies it."""
    p = _get_proposal(session, proposal_id)
    if p.status != "measured":
        raise HTTPException(status_code=409, detail=f"Only a measured proposal can be approved (this one is {p.status})")
    p.status, p.decided_by, p.decided_at = "approved", _reviewer(user), utcnow()
    session.add(p)
    enqueue(session, "apply_proposal", proposal_id=p.id)
    session.commit()
    return _proposal_dict(p)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: UUID, body: RejectIn, session: Session = Depends(get_session),
           user: SupabaseAuthUser = Depends(require_admin)):
    p = _get_proposal(session, proposal_id)
    if p.status not in ("measuring", "measured", "failed"):
        raise HTTPException(status_code=409, detail=f"The proposal is {p.status}")
    p.status, p.decided_by, p.decided_at = "rejected", _reviewer(user), utcnow()
    if body.note:
        p.error = None
        p.result = {"reject_note": body.note.strip()}
    session.add(p)
    session.commit()
    return _proposal_dict(p)


@router.get("/log")
def audit_log(session: Session = Depends(get_session), _: SupabaseAuthUser = Depends(require_admin),
              limit: int = Query(default=100, ge=1, le=500)):
    rows = session.exec(select(AuditLog).order_by(col(AuditLog.created_at).desc()).limit(limit)).all()
    return {"log": [{"id": str(r.id), "actor": r.actor, "action": r.action, "brand": r.brand,
                     "target_kind": r.target_kind, "target_id": r.target_id, "before": r.before,
                     "after": r.after, "created_at": r.created_at} for r in rows]}
