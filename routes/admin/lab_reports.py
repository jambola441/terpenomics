import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlmodel import Session, select, delete, func

from auth import SupabaseAuthUser
from database import get_session
from models import LabReport, LabReportStatus, Listing, ListingTerpene, ListingCannabinoid, Terpene, Cannabinoid
from services.lab_report_parser import COAExtraction, extract_from_pdf
from .auth import require_admin

router = APIRouter()

_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB


@router.get("/lab-reports")
def list_lab_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    reports = session.exec(
        select(LabReport).order_by(LabReport.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [_serialize_report(r) for r in reports]


def _apply_terpenes_to_listing(
    session: Session,
    listing_id: UUID,
    extraction: COAExtraction,
) -> None:
    session.exec(delete(ListingTerpene).where(ListingTerpene.listing_id == listing_id))

    for t in extraction.terpenes:
        tname = t.name.strip()
        if not tname:
            continue
        terp = session.exec(select(Terpene).where(Terpene.name == tname)).first()
        if not terp:
            terp = Terpene(name=tname)
            session.add(terp)
            session.flush()

        session.add(
            ListingTerpene(
                listing_id=listing_id,
                terpene_id=terp.id,
                percent=t.percent,
            )
        )


def _apply_cannabinoids_to_listing(
    session: Session,
    listing_id: UUID,
    extraction: COAExtraction,
) -> None:
    session.exec(delete(ListingCannabinoid).where(ListingCannabinoid.listing_id == listing_id))

    for c in extraction.cannabinoids:
        cname = c.name.strip()
        if not cname:
            continue
        cannabinoid = session.exec(select(Cannabinoid).where(Cannabinoid.name == cname)).first()
        if not cannabinoid:
            cannabinoid = Cannabinoid(name=cname, family="other")
            session.add(cannabinoid)
            session.flush()
        session.add(
            ListingCannabinoid(
                listing_id=listing_id,
                cannabinoid_id=cannabinoid.id,
                percent=c.percent,
            )
        )


def _validate_pdf(file: UploadFile) -> None:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Only PDF files are accepted (got '{file.filename}')",
            )


@router.post("/lab-reports/upload")
async def upload_lab_reports(
    files: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    results = []
    for file in files:
        _validate_pdf(file)
        pdf_bytes = await file.read()
        if len(pdf_bytes) > _MAX_PDF_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"'{file.filename}' exceeds 20 MB limit",
            )
        if len(pdf_bytes) == 0:
            raise HTTPException(
                status_code=400,
                detail=f"'{file.filename}' is empty",
            )

        report = LabReport(status=LabReportStatus.pending, pdf_bytes=pdf_bytes)
        session.add(report)
        session.flush()
        results.append({"lab_report_id": str(report.id), "filename": file.filename})

    session.commit()
    return results


def _serialize_report(r: LabReport) -> dict:
    terpenes = []
    if r.raw_terpenes_json:
        try:
            terpenes = json.loads(r.raw_terpenes_json)
        except Exception:
            pass
    cannabinoids = []
    if r.raw_cannabinoids_json:
        try:
            cannabinoids = json.loads(r.raw_cannabinoids_json)
        except Exception:
            pass
    return {
        "id": str(r.id),
        "status": r.status,
        "lab_name": r.lab_name,
        "lab_license": r.lab_license,
        "test_date": r.test_date,
        "batch_id": r.batch_id,
        "product_name_on_report": r.product_name_on_report,
        "product_name": r.product_name_on_report,
        "total_terpenes": r.total_terpenes,
        "pass_fail": r.pass_fail,
        "confidence": r.confidence,
        "confidence_notes": None,
        "listing_id": str(r.listing_id) if r.listing_id else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "terpenes": terpenes,
        "cannabinoids": cannabinoids,
    }


class ProcessRequest(BaseModel):
    lab_report_ids: List[UUID]
    listing_id: Optional[UUID] = None


@router.post("/lab-reports/process")
async def process_lab_reports(
    body: ProcessRequest = Body(...),
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    if not body.lab_report_ids:
        raise HTTPException(status_code=400, detail="At least one lab_report_id is required")

    if body.listing_id is not None:
        if not session.get(Listing, body.listing_id):
            raise HTTPException(status_code=404, detail="listing not found")

    results = []
    for report_id in body.lab_report_ids:
        report = session.get(LabReport, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail=f"lab_report {report_id} not found")
        if report.pdf_bytes is None:
            raise HTTPException(
                status_code=400,
                detail=f"lab_report {report_id} has no stored PDF (already processed or invalid)",
            )

        try:
            extraction: COAExtraction = extract_from_pdf(report.pdf_bytes)
        except Exception as exc:
            report.status = LabReportStatus.failed
            report.error_message = str(exc)[:1000]
            report.pdf_bytes = None
            session.add(report)
            session.commit()
            raise HTTPException(status_code=502, detail=f"Extraction failed for {report_id}: {exc}") from exc

        report.listing_id             = body.listing_id
        report.lab_name               = extraction.lab_name
        report.lab_license            = extraction.lab_license
        report.test_date              = extraction.test_date
        report.batch_id               = extraction.batch_id
        report.product_name_on_report = extraction.product_name
        report.total_terpenes         = extraction.total_terpenes
        report.pass_fail              = extraction.pass_fail
        report.confidence             = extraction.confidence
        report.raw_terpenes_json      = json.dumps(
            [{"name": t.name, "percent": t.percent} for t in extraction.terpenes]
        )
        report.raw_cannabinoids_json  = json.dumps(
            [{"name": c.name, "percent": c.percent} for c in extraction.cannabinoids]
        )
        report.status = LabReportStatus.extracted

        applied = False
        if body.listing_id is not None and (extraction.terpenes or extraction.cannabinoids):
            _apply_terpenes_to_listing(session, body.listing_id, extraction)
            _apply_cannabinoids_to_listing(session, body.listing_id, extraction)
            report.status = LabReportStatus.applied
            applied = True

        session.add(report)
        session.commit()
        session.refresh(report)

        results.append({
            "lab_report_id":      str(report.id),
            "lab_name":           report.lab_name,
            "lab_license":        report.lab_license,
            "test_date":          report.test_date,
            "batch_id":           report.batch_id,
            "product_name":       report.product_name_on_report,
            "total_terpenes":     report.total_terpenes,
            "pass_fail":          report.pass_fail,
            "terpenes":           [{"name": t.name, "percent": t.percent} for t in extraction.terpenes],
            "cannabinoids":       [{"name": c.name, "percent": c.percent} for c in extraction.cannabinoids],
            "confidence":         report.confidence,
            "confidence_notes":   extraction.confidence_notes,
            "status":             report.status,
            "applied_to_listing": applied,
        })

    return results


@router.get("/lab-reports/{report_id}")
def get_lab_report(
    report_id: UUID,
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    report = session.get(LabReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="lab_report not found")
    return _serialize_report(report)


class AssignRequest(BaseModel):
    listing_id: Optional[UUID] = None


@router.post("/lab-reports/{report_id}")
def assign_lab_report(
    report_id: UUID,
    body: AssignRequest = Body(...),
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    report = session.get(LabReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="lab_report not found")

    if body.listing_id is not None:
        if not session.get(Listing, body.listing_id):
            raise HTTPException(status_code=404, detail="listing not found")

    report.listing_id = body.listing_id
    session.add(report)
    session.commit()
    session.refresh(report)
    return _serialize_report(report)
