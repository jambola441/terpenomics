import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlmodel import Session, select, delete

from auth import SupabaseAuthUser
from database import get_session
from models import LabReport, LabReportStatus, Product, ProductTerpene, Terpene
from services.lab_report_parser import COAExtraction, extract_from_pdf
from .auth import require_admin

router = APIRouter()

_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB


def _apply_terpenes_to_product(
    session: Session,
    product_id: UUID,
    extraction: COAExtraction,
) -> None:
    """
    Replace all ProductTerpene rows for this product with the extracted data.
    Reuses the same upsert pattern as routes/admin/products.py.
    """
    session.exec(delete(ProductTerpene).where(ProductTerpene.product_id == product_id))

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
            ProductTerpene(
                product_id=product_id,
                terpene_id=terp.id,
                percent=t.percent,
            )
        )


@router.post("/lab-reports/upload")
async def upload_lab_report(
    file: UploadFile = File(...),
    product_id: Optional[UUID] = Query(default=None),
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """
    Upload a cannabis lab report PDF (COA).

    - Rasterizes each page and sends to Claude's vision API.
    - Extracts terpene percentages + report metadata.
    - If `product_id` is provided, writes terpene data to `product_terpenes`.
    - Always persists a `LabReport` row for audit trail.
    """
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=400, detail="PDF exceeds 20 MB limit")
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Validate product exists if provided
    if product_id is not None:
        if not session.get(Product, product_id):
            raise HTTPException(status_code=404, detail="product not found")

    # Create pending LabReport row so we have an ID even if extraction fails
    report = LabReport(
        product_id=product_id,
        status=LabReportStatus.pending,
    )
    session.add(report)
    session.flush()

    # --- Claude extraction ---
    try:
        extraction: COAExtraction = extract_from_pdf(pdf_bytes)
    except Exception as exc:
        report.status = LabReportStatus.failed
        report.error_message = str(exc)[:1000]
        session.add(report)
        session.commit()
        raise HTTPException(status_code=502, detail=f"Extraction failed: {exc}") from exc

    # Populate LabReport from extraction
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
    report.status = LabReportStatus.extracted

    applied = False
    if product_id is not None and extraction.terpenes:
        _apply_terpenes_to_product(session, product_id, extraction)
        report.status = LabReportStatus.applied
        applied = True

    session.add(report)
    session.commit()
    session.refresh(report)

    return {
        "lab_report_id":      str(report.id),
        "lab_name":           report.lab_name,
        "lab_license":        report.lab_license,
        "test_date":          report.test_date,
        "batch_id":           report.batch_id,
        "product_name":       report.product_name_on_report,
        "total_terpenes":     report.total_terpenes,
        "pass_fail":          report.pass_fail,
        "terpenes":           [{"name": t.name, "percent": t.percent} for t in extraction.terpenes],
        "confidence":         report.confidence,
        "confidence_notes":   extraction.confidence_notes,
        "status":             report.status,
        "applied_to_product": applied,
    }
