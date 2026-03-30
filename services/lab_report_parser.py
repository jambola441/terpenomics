"""
Lab report (COA) parser using Claude's Files API + native PDF support.

Pipeline:
  PDF bytes -> upload to Anthropic Files API -> single messages call with
  document block (text layer + image per page) -> validated COAExtraction
"""

import io
import json
import os
import re
from typing import Optional

import anthropic
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


class CannabinoidReading(BaseModel):
    name: str
    percent: float

    @field_validator("percent")
    @classmethod
    def percent_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"Cannabinoid percent {v} out of range 0–100")
        return round(v, 4)


class COAExtraction(BaseModel):
    lab_name:         Optional[str]   = None
    lab_license:      Optional[str]   = None
    test_date:        Optional[str]   = None
    batch_id:         Optional[str]   = None
    product_name:     Optional[str]   = None
    total_terpenes:   Optional[float] = None
    pass_fail:        Optional[str]   = None
    terpenes:         list[TerpeneReading]     = []
    cannabinoids:     list[CannabinoidReading] = []
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

| Canonical Name     | Common Aliases                                                    |
|--------------------|-------------------------------------------------------------------|
| Myrcene            | β-Myrcene, beta-Myrcene, b-Myrcene                               |
| Limonene           | d-Limonene                                                        |
| β-Caryophyllene    | BCP, b-Caryophyllene, Beta-Caryophyllene, Caryophyllene          |
| Linalool           |                                                                   |
| α-Pinene           | alpha-Pinene, Pinene, a-Pinene                                    |
| β-Pinene           | beta-Pinene, b-Pinene                                             |
| Terpinolene        |                                                                   |
| Ocimene            | β-Ocimene, b-Ocimene, trans-b-Ocimene                            |
| Humulene           | α-Humulene, a-Humulene, α-Caryophyllene, alpha-Humulene          |
| Bisabolol          | α-Bisabolol, a-Bisabolol, alpha-Bisabolol                         |
| Valencene          |                                                                   |
| Terpineol          | α-Terpineol, a-Terpineol, Alpha Terpineol                        |
| Geraniol           |                                                                   |
| Camphene           |                                                                   |
| Borneol            |                                                                   |
| trans-Nerolidol    |                                                                   |
| cis-Nerolidol      |                                                                   |
| Guaiol             |                                                                   |
| Eucalyptol         | 1,8-Cineole                                                       |
| Fenchol            | Fenchyl Alcohol                                                   |
| Phytol             |                                                                   |
| p-Cymene           |                                                                   |
| γ-Terpinene        | gamma-Terpinene, g-Terpinene                                      |
| Farnesene          | trans-β-Farnesene, trans-b-Farnesene                              |
| Sabinene Hydrate   |                                                                   |
| Sabinene           |                                                                   |
| Fenchone           |                                                                   |
| Isopulegol         |                                                                   |
| Caryophyllene Oxide| Caryophyllene oxide                                               |
| Camphor            |                                                                   |
| Isoborneol         |                                                                   |
| Menthol            | DL-Menthol                                                        |
| Nerol              |                                                                   |
| Pulegone           |                                                                   |
| Geranyl Acetate    |                                                                   |
| α-Cedrene          | a-Cedrene, Alpha-cedrene                                          |
| α-Phellandrene     | a-Phellandrene, Alpha-phellandrene                                |
| Δ3-Carene          | d-3-Carene, Carene                                                |
| Cedrol             |                                                                   |
| α-Terpinene        | a-Terpinene, alpha-Terpinene                                      |
| Citronellol        |                                                                   |

## Canonical cannabinoid names

Always normalize cannabinoid names to this canonical list. Map common aliases accordingly.

| Canonical Name        | Common Aliases                                          |
|-----------------------|---------------------------------------------------------|
| CBDV                  | Cannabidivarin                                          |
| CBDa                  | CBD-A, CBDA, Cannabidiolic Acid                         |
| CBGa                  | CBG-A, CBGA, Cannabigerolic Acid                        |
| CBG                   | Cannabigerol                                            |
| CBD                   | Cannabidiol                                             |
| THCV                  | THC-V, Tetrahydrocannabivarin                           |
| CBN                   | Cannabinol                                              |
| D9-THC                | Δ9-THC, Delta-9-THC, Delta 9 THC, THC, d9-THC          |
| D8-THC                | Δ8-THC, Delta-8-THC, d8-THC                             |
| (6aR,9S)-d10-THC      | Δ10-THC (9S isomer), Delta-10-THC, d10-THC             |
| (6aR,9R)-d10-THC      | Δ10-THC (9R isomer)                                     |
| CBC                   | Cannabichromene                                         |
| THCa                  | THC-A, THCA, Tetrahydrocannabinolic Acid                |

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
  "cannabinoids": [
    {"name": "<canonical name>", "percent": <float>}
  ],
  "confidence": <integer 1-5>,
  "confidence_notes": string | null
}

## Rules

- `terpenes`: include only terpenes actually present in the report with a numeric value.
  Omit any terpene listed as "ND" (not detected) or "<LOQ".
- `cannabinoids`: include only cannabinoids actually present in the report with a numeric value.
  Omit any cannabinoid listed as "ND" or "<LOQ". Use an empty array if the report has no cannabinoid panel.
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
# Claude API interaction
# ---------------------------------------------------------------------------

def _make_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key)


def extract_from_pdf(pdf_bytes: bytes) -> COAExtraction:
    """
    Files API pipeline:
      1. Upload raw PDF bytes to Anthropic (free, no rasterization needed)
      2. Send ONE message with a document block — Claude processes all pages
         simultaneously using both the text layer and images
      3. Delete the uploaded file (cleanup)
    """
    client = _make_client()

    upload = client.beta.files.upload(
        file=("report.pdf", io.BytesIO(pdf_bytes), "application/pdf"),
    )

    try:
        response = client.beta.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            betas=["files-api-2025-04-14"],
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
                            "type": "document",
                            "source": {
                                "type": "file",
                                "file_id": upload.id,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extract all terpene data and report metadata from this lab "
                                "report. Return only the JSON object as specified."
                            ),
                        },
                    ],
                }
            ],
        )

        raw_text = response.content[0].text.strip()
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
        data = json.loads(raw_text)
        return COAExtraction.model_validate(data)

    finally:
        client.beta.files.delete(upload.id)
