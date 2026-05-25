"""
CheckWeedNY adapter — batch_id in, LabReportEntry out.

Lookup: GET /v1/coas?batch=<batch_id> → pick best match →
        GET /v1/coas/<id>             → normalize to LabReportEntry
"""

import os
import time
from typing import Optional

import requests

from schema import CannabinoidReading, LabReportEntry, TerpeneReading

API_BASE = "https://api.checkweedny.com/v1"
REQUEST_TIMEOUT = 10
RATE_LIMIT_DELAY = 0.25  # seconds between calls

# Canonical terpene name map (CheckWeedNY names → our canonical names)
TERPENE_NAME_MAP: dict[str, str] = {
    "Caryophyllene":        "β-Caryophyllene",
    "Beta-Caryophyllene":   "β-Caryophyllene",
    "B-Caryophyllene":      "β-Caryophyllene",
    "Alpha-Pinene":         "α-Pinene",
    "A-Pinene":             "α-Pinene",
    "alpha-Pinene":         "α-Pinene",
    "Beta-Pinene":          "β-Pinene",
    "B-Pinene":             "β-Pinene",
    "beta-Pinene":          "β-Pinene",
    "Alpha-Humulene":       "Humulene",
    "A-Humulene":           "Humulene",
    "alpha-Humulene":       "Humulene",
    "Alpha-Terpineol":      "Terpineol",
    "A-Terpineol":          "Terpineol",
    "Alpha-Bisabolol":      "Bisabolol",
    "A-Bisabolol":          "Bisabolol",
    "Trans-Nerolidol":      "trans-Nerolidol",
    "Cis-Nerolidol":        "cis-Nerolidol",
    "Beta-Ocimene":         "Ocimene",
    "B-Ocimene":            "Ocimene",
    "Trans-Beta-Ocimene":   "Ocimene",
    "trans-b-Ocimene":      "Ocimene",
    "Alpha-Cedrene":        "α-Cedrene",
    "Alpha-Phellandrene":   "α-Phellandrene",
    "Gamma-Terpinene":      "γ-Terpinene",
    "G-Terpinene":          "γ-Terpinene",
    "Alpha-Terpinene":      "α-Terpinene",
    "1,8-Cineole":          "Eucalyptol",
    "Fenchyl Alcohol":      "Fenchol",
    "D-3-Carene":           "Δ3-Carene",
    "Trans-Beta-Farnesene": "Farnesene",
}

CANNABINOID_NAME_MAP: dict[str, str] = {
    "THC":              "D9-THC",
    "Delta-9-THC":      "D9-THC",
    "Δ9-THC":           "D9-THC",
    "Delta-8-THC":      "D8-THC",
    "Δ8-THC":           "D8-THC",
    "THCA":             "THCa",
    "THC-A":            "THCa",
    "CBDA":             "CBDa",
    "CBD-A":            "CBDa",
    "CBGA":             "CBGa",
    "CBG-A":            "CBGa",
}


def _headers() -> dict:
    key = os.environ.get("COA_API_KEY", "")
    if not key:
        print("WARNING: COA_API_KEY not set")
    return {"X-API-Key": key, "Accept": "application/json"}


def _norm_terpene(name: str) -> str:
    return TERPENE_NAME_MAP.get(name, name)


def _norm_cannabinoid(name: str) -> str:
    return CANNABINOID_NAME_MAP.get(name, name)


def _list_record(batch_id: str) -> Optional[dict]:
    resp = requests.get(
        f"{API_BASE}/coas",
        params={"batch": batch_id, "limit": 1},
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    items = data.get("data") or (data if isinstance(data, list) else [])
    return items[0] if items else None


def _detail(coa_id: str) -> Optional[dict]:
    resp = requests.get(
        f"{API_BASE}/coas/{coa_id}",
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def fetch(batch_id: str) -> Optional[LabReportEntry]:
    """
    Look up a single batch ID on CheckWeedNY.
    Returns a LabReportEntry on success, None if not found.
    """
    time.sleep(RATE_LIMIT_DELAY)
    record = _list_record(batch_id)
    if not record:
        return None

    coa_id = record.get("id")
    if not coa_id:
        return None

    time.sleep(RATE_LIMIT_DELAY)
    detail = _detail(coa_id)
    if not detail:
        return None

    terpenes = [
        TerpeneReading(
            name=_norm_terpene(c.get("compound", "")),
            percent=round(float(c["value_pct"]), 4),
        )
        for c in (detail.get("terpenes") or [])
        if c.get("compound") and c.get("value_pct") is not None
    ]

    cannabinoids = [
        CannabinoidReading(
            name=_norm_cannabinoid(c.get("compound", "")),
            percent=round(float(c["value_pct"]), 4),
        )
        for c in (detail.get("cannabinoids") or [])
        if c.get("compound") and c.get("value_pct") is not None
    ]

    return LabReportEntry(
        source="checkweedny",
        batch_id=batch_id,
        source_id=str(coa_id),
        lab_name=detail.get("lab_name") or detail.get("lab") or None,
        lab_license=detail.get("lab_license") or detail.get("lab_license_number") or None,
        test_date=detail.get("test_date") or detail.get("tested_at") or None,
        product_name=detail.get("product") or detail.get("product_name") or None,
        pass_fail=detail.get("pass_fail") or detail.get("overall_pass") or None,
        total_terpenes=detail.get("total_terpenes"),
        confidence=record.get("parse_confidence"),
        terpenes=terpenes,
        cannabinoids=cannabinoids,
    )
