"""
Lab report (COA) parser using Claude's vision API.

Pipeline:
  PDF bytes -> rasterize pages (PyMuPDF @ 200 DPI) -> base64 PNG images
  -> Claude vision API with cached system prompt -> validated COAExtraction
"""

import base64
import json
import os
import re
from typing import Optional

import anthropic
import fitz  # pymupdf
from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Pydantic schemas for Claude's structured output
# ---------------------------------------------------------------------------

class TerpeneReading(BaseModel):
    name: str
    percent: float

    @field_validator("percent")
    @classmethod
    def percent_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 20.0):
            raise ValueError(f"Terpene percent {v} out of range 0–20")
        return round(v, 4)


class COAExtraction(BaseModel):
    lab_name:         Optional[str]   = None
    lab_license:      Optional[str]   = None
    test_date:        Optional[str]   = None
    batch_id:         Optional[str]   = None
    product_name:     Optional[str]   = None
    total_terpenes:   Optional[float] = None
    pass_fail:        Optional[str]   = None
    terpenes:         list[TerpeneReading] = []
    confidence:       int             = 1   # 1–5
    confidence_notes: Optional[str]   = None

    @field_validator("total_terpenes")
    @classmethod
    def total_in_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError(f"total_terpenes {v} out of range")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: int) -> int:
        return max(1, min(5, v))

    @model_validator(mode="after")
    def check_sum_vs_total(self) -> "COAExtraction":
        """Flag (but don't reject) if individual sum deviates >15% from total."""
        if self.total_terpenes and self.terpenes:
            computed = sum(t.percent for t in self.terpenes)
            if self.total_terpenes > 0:
                deviation = abs(computed - self.total_terpenes) / self.total_terpenes
                if deviation > 0.15:
                    note = (
                        f"sum of individuals ({computed:.3f}%) deviates "
                        f"{deviation*100:.1f}% from total_terpenes ({self.total_terpenes}%)"
                    )
                    self.confidence_notes = (
                        f"{self.confidence_notes}; {note}" if self.confidence_notes else note
                    )
        return self


# ---------------------------------------------------------------------------
# System prompt (cached — identical across every call)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a cannabis lab report (Certificate of Analysis / COA) data extractor.
Your task is to read the provided lab report page image and return a single JSON object
containing terpene percentages and report metadata.

## Canonical terpene names

Always normalize terpene names to this canonical list. Map common aliases accordingly.

| Canonical Name  | Common Aliases                        |
|-----------------|---------------------------------------|
| Myrcene         | β-Myrcene, beta-Myrcene               |
| Limonene        | d-Limonene                            |
| Caryophyllene   | β-Caryophyllene, BCP, b-Caryophyllene |
| Linalool        |                                       |
| α-Pinene        | alpha-Pinene, Pinene, a-Pinene        |
| β-Pinene        | beta-Pinene, b-Pinene                 |
| Terpinolene     |                                       |
| Ocimene         | β-Ocimene, b-Ocimene                  |
| Humulene        | α-Humulene, a-Humulene                |
| Bisabolol       | α-Bisabolol, a-Bisabolol              |
| Valencene       |                                       |
| Terpineol       | α-Terpineol, a-Terpineol             |
| Geraniol        |                                       |
| Camphene        |                                       |
| Borneol         |                                       |
| Nerolidol       | trans-Nerolidol                       |
| Guaiol          |                                       |
| Eucalyptol      | 1,8-Cineole                           |
| Fenchol         |                                       |
| Phytol          |                                       |

## JSON output schema

Return ONLY valid JSON matching this schema — no markdown fences, no extra text:

{
  "lab_name": string | null,
  "lab_license": string | null,
  "test_date": string | null,
  "batch_id": string | null,
  "product_name": string | null,
  "total_terpenes": number | null,
  "pass_fail": "PASS" | "FAIL" | null,
  "terpenes": [
    {"name": "<canonical name>", "percent": <float>}
  ],
  "confidence": <integer 1-5>,
  "confidence_notes": string | null
}

## Rules

- `terpenes`: include only terpenes actually present in the report with a numeric value.
  Omit any terpene listed as "ND" (not detected) or "<LOQ".
- `percent` values are percentage points (e.g. 0.42, not 0.0042). If the report shows
  mg/g, convert: divide by 10.
- `total_terpenes`: the sum reported on the document, NOT your own calculation.
- `confidence` scale:
    5 = Clear terpene table found, all values legible
    4 = Terpene table found, minor ambiguity in 1-2 values
    3 = Partial table or values partially obscured
    2 = Inferred from text, no clear table
    1 = No terpene data visible on this page
- If no terpene data is visible on this page, return an empty terpenes array and
  confidence = 1.
- `pass_fail`: look for an overall "PASS" or "FAIL" status on the document.
- NY OCM lab reports always include the ISO-accredited lab name and license number —
  capture both if visible.
"""

# ---------------------------------------------------------------------------
# PDF rasterization
# ---------------------------------------------------------------------------

def rasterize_pdf(pdf_bytes: bytes, dpi: int = 200, max_pages: int = 3) -> list[str]:
    """
    Convert up to `max_pages` pages of a PDF to base64-encoded PNG strings.
    Returns a list ordered by page number (0-indexed).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_b64: list[str] = []
    zoom = dpi / 72  # PyMuPDF default is 72 DPI
    mat = fitz.Matrix(zoom, zoom)

    for page_num in range(min(len(doc), max_pages)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        png_bytes = pix.tobytes("png")
        pages_b64.append(base64.standard_b64encode(png_bytes).decode("utf-8"))

    doc.close()
    return pages_b64


# ---------------------------------------------------------------------------
# Claude API interaction
# ---------------------------------------------------------------------------

def _make_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def _extract_from_page(client: anthropic.Anthropic, b64_image: str) -> COAExtraction:
    """Send a single page image to Claude and return a validated COAExtraction."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract all terpene data and report metadata from this lab "
                            "report page. Return only the JSON object as specified."
                        ),
                    },
                ],
            }
        ],
    )

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON anyway
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)

    data = json.loads(raw_text)
    return COAExtraction.model_validate(data)


def _merge_extractions(primary: COAExtraction, secondary: COAExtraction) -> COAExtraction:
    """
    Merge two page extractions. Page with more terpenes wins for terpene data;
    primary wins for metadata when both have values.
    """
    if len(secondary.terpenes) > len(primary.terpenes):
        merged_terpenes = secondary.terpenes
        merged_total = secondary.total_terpenes or primary.total_terpenes
    else:
        merged_terpenes = primary.terpenes
        merged_total = primary.total_terpenes or secondary.total_terpenes

    return COAExtraction(
        lab_name=primary.lab_name or secondary.lab_name,
        lab_license=primary.lab_license or secondary.lab_license,
        test_date=primary.test_date or secondary.test_date,
        batch_id=primary.batch_id or secondary.batch_id,
        product_name=primary.product_name or secondary.product_name,
        total_terpenes=merged_total,
        pass_fail=primary.pass_fail or secondary.pass_fail,
        terpenes=merged_terpenes,
        confidence=max(primary.confidence, secondary.confidence),
        confidence_notes="; ".join(
            filter(None, [primary.confidence_notes, secondary.confidence_notes])
        ) or None,
    )


def extract_from_pdf(pdf_bytes: bytes) -> COAExtraction:
    """
    Full pipeline: rasterize PDF pages, send to Claude one at a time,
    merge results. Returns the best COAExtraction we could get.
    """
    client = _make_client()
    pages = rasterize_pdf(pdf_bytes)

    if not pages:
        raise ValueError("PDF has no renderable pages")

    result = _extract_from_page(client, pages[0])

    # If page 1 gave us nothing useful, try subsequent pages
    for page_b64 in pages[1:]:
        if result.terpenes and result.confidence >= 3:
            break
        page_result = _extract_from_page(client, page_b64)
        result = _merge_extractions(result, page_result)

    return result
