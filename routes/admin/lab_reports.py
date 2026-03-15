import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
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
    """
    Upload one or more COA lab report PDFs.

    - Validates each file is a PDF under 20 MB.
    - Creates a pending `LabReport` row per file and stores the raw PDF bytes.
    - Returns the IDs to pass to `POST /admin/lab-reports/process`.
    """
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


class ProcessRequest(BaseModel):
    lab_report_ids: List[UUID]
    product_id: Optional[UUID] = None


@router.post("/lab-reports/process")
async def process_lab_reports(
    body: ProcessRequest = Body(...),
    session: Session = Depends(get_session),
    _: SupabaseAuthUser = Depends(require_admin),
):
    """
    Process previously uploaded COA lab report PDFs.

    - Fetches each LabReport by ID and runs Claude vision extraction.
    - If `product_id` is provided, writes terpene data to `product_terpenes`
      (last file's terpenes win if multiple files are processed).
    - Returns extraction results for each report.
    """
    if not body.lab_report_ids:
        raise HTTPException(status_code=400, detail="At least one lab_report_id is required")

    # Validate product exists if provided
    if body.product_id is not None:
        if not session.get(Product, body.product_id):
            raise HTTPException(status_code=404, detail="product not found")

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

        # Run Claude extraction
        try:
            extraction: COAExtraction = extract_from_pdf(report.pdf_bytes)
        except Exception as exc:
            report.status = LabReportStatus.failed
            report.error_message = str(exc)[:1000]
            report.pdf_bytes = None
            session.add(report)
            session.commit()
            raise HTTPException(status_code=502, detail=f"Extraction failed for {report_id}: {exc}") from exc

        # Populate LabReport from extraction
        report.product_id             = body.product_id
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
        report.status    = LabReportStatus.extracted
        report.pdf_bytes = None  # clear stored bytes after successful extraction

        applied = False
        if body.product_id is not None and extraction.terpenes:
            _apply_terpenes_to_product(session, body.product_id, extraction)
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
            "confidence":         report.confidence,
            "confidence_notes":   extraction.confidence_notes,
            "status":             report.status,
            "applied_to_product": applied,
        })

    return results
