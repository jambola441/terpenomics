"""
Common output schema for lab report entries across all sources.

Adapters (checkweedny.py, metrc.py, etc.) must return LabReportEntry objects.
scrape.py serializes them to CSV via to_csv_row().
"""

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TerpeneReading:
    name: str
    percent: float


@dataclass
class CannabinoidReading:
    name: str
    percent: float


@dataclass
class LabReportEntry:
    source: str                             # "checkweedny" | "metrc" | "pdf"
    batch_id: str
    source_id: Optional[str] = None         # CheckWeedNY COA ID, Metrc test ID, etc.
    lab_name: Optional[str] = None
    lab_license: Optional[str] = None
    test_date: Optional[str] = None
    product_name: Optional[str] = None
    pass_fail: Optional[str] = None         # "PASS" | "FAIL" | None
    total_terpenes: Optional[float] = None
    confidence: Optional[float] = None      # 0.0–1.0 (CheckWeedNY) or 1–5 (PDF)
    terpenes: list[TerpeneReading] = field(default_factory=list)
    cannabinoids: list[CannabinoidReading] = field(default_factory=list)


CSV_FIELDS = [
    "source",
    "batch_id",
    "brand",
    "product_name_scraped",
    "source_id",
    "lab_name",
    "lab_license",
    "test_date",
    "product_name",
    "pass_fail",
    "total_terpenes",
    "confidence",
    "terpene_count",
    "cannabinoid_count",
    "terpenes_json",
    "cannabinoids_json",
]


def to_csv_row(entry: LabReportEntry, brand: str = "", product_name_scraped: str = "") -> dict:
    return {
        "source":               entry.source,
        "batch_id":             entry.batch_id,
        "brand":                brand,
        "product_name_scraped": product_name_scraped,
        "source_id":            entry.source_id or "",
        "lab_name":             entry.lab_name or "",
        "lab_license":          entry.lab_license or "",
        "test_date":            entry.test_date or "",
        "product_name":         entry.product_name or "",
        "pass_fail":            entry.pass_fail or "",
        "total_terpenes":       "" if entry.total_terpenes is None else entry.total_terpenes,
        "confidence":           "" if entry.confidence is None else entry.confidence,
        "terpene_count":        len(entry.terpenes),
        "cannabinoid_count":    len(entry.cannabinoids),
        "terpenes_json":        json.dumps([{"name": t.name, "percent": t.percent} for t in entry.terpenes]),
        "cannabinoids_json":    json.dumps([{"name": c.name, "percent": c.percent} for c in entry.cannabinoids]),
    }
