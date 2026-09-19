"""Checks a filled evaluation workbook before it is submitted.

The failure mode this guards against is silence: a step label that matches no
row, a column mapped to the wrong header, or a write into a merged cell that is
not the range's anchor all produce a blank cell rather than an error. Metrc
would be the one to notice.

Every check compares the workbook against the call transcript it was built
from, so it verifies what was actually sent and received rather than that the
file merely looks populated.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import openpyxl
from openpyxl.utils import get_column_letter, range_boundaries

from .client import CallRecord
from .workbook import map_sheet, _render

ERROR, WARN, INFO = "error", "warn", "info"
STEP_RE = re.compile(r"^Step", re.IGNORECASE)


@dataclass
class Finding:
    level: str
    sheet: str
    message: str
    step: str = ""

    def __str__(self) -> str:
        where = f"{self.sheet}/{self.step}" if self.step else self.sheet
        return f"[{self.level.upper():5}] {where}: {self.message}"


@dataclass
class Report:
    findings: list = field(default_factory=list)
    steps_total: int = 0
    steps_ok: int = 0
    cells_checked: int = 0

    def add(self, level, sheet, message, step=""):
        self.findings.append(Finding(level, sheet, message, step))

    @property
    def errors(self) -> list:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self) -> list:
        return [f for f in self.findings if f.level == WARN]

    def ok(self) -> bool:
        return not self.errors


def load_records(run_dirs) -> list:
    records = []
    for d in run_dirs:
        with open(f"{d}/calls.jsonl", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    records.append(CallRecord(**json.loads(line)))
    return records


def record_for(records, sheet, step):
    matches = [r for r in records if r.sheet == sheet and r.step == step]
    if not matches:
        return None
    for record in reversed(matches):
        if record.ok:
            return record
    return matches[-1]


def _merge_index(ws) -> dict:
    """Every cell covered by a merge -> the anchor it actually writes to."""
    index = {}
    for rng in ws.merged_cells.ranges:
        c1, r1, c2, r2 = range_boundaries(str(rng))
        anchor = f"{get_column_letter(c1)}{r1}"
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                index[f"{get_column_letter(c)}{r}"] = (anchor, str(rng))
    return index


def validate(
    workbook_path: str,
    records: list,
    *,
    template_path: str | None = None,
    sheets: list | None = None,
    expected_host: str = "",
) -> Report:
    wb = openpyxl.load_workbook(workbook_path)
    template = openpyxl.load_workbook(template_path) if template_path else None
    report = Report()

    targets = sheets or [
        ws.title for ws in wb.worksheets
        if map_sheet(ws) and map_sheet(ws).steps
    ]

    for name in targets:
        if name not in wb.sheetnames:
            report.add(ERROR, name, "sheet missing from the workbook")
            continue
        ws = wb[name]
        sm = map_sheet(ws)
        if not sm or not sm.steps:
            report.add(ERROR, name, "no step rows found — layout not recognised")
            continue

        merged = _merge_index(ws)
        template_merged = _merge_index(template[name]) if template and name in template.sheetnames else {}

        if "A" in sm.columns.values():
            report.add(ERROR, name, "an answer column is mapped onto column A (task text)")
        for required in ("status", "evidence"):
            if required not in sm.columns:
                report.add(ERROR, name, f"no {required!r} column resolved from the header row")

        for step, row in sm.steps.items():
            record = record_for(records, name, step)
            report.steps_total += 1

            for field_name, col in sm.columns.items():
                coord = f"{col}{row}"
                report.cells_checked += 1

                # A write into a merged range that is not its anchor is lost.
                if coord in merged and merged[coord][0] != coord:
                    anchor, rng = merged[coord]
                    level = ERROR if coord not in template_merged else WARN
                    report.add(
                        level, name,
                        f"{field_name} cell {coord} sits inside {rng} (anchor {anchor}) "
                        "— a write there would not be saved",
                        step,
                    )

                actual = str(ws[coord].value or "").strip()
                expected = "" if record is None else _render(field_name, record).strip()
                if actual != expected:
                    report.add(
                        ERROR, name,
                        f"{field_name} @{coord} is {actual[:50]!r} but the transcript "
                        f"says {expected[:50]!r}",
                        step,
                    )

                if field_name == "status" and actual:
                    if not re.fullmatch(r"\d{3}", actual):
                        report.add(ERROR, name, f"result code {actual!r} is not an HTTP status", step)
                    elif actual == "200":
                        report.steps_ok += 1
                    else:
                        report.add(
                            WARN, name,
                            f"result code {actual} — Metrc asks that every action return 200",
                            step,
                        )
                if field_name == "url" and actual:
                    if not actual.startswith("https://"):
                        report.add(ERROR, name, f"request URL is not https: {actual[:50]!r}", step)
                    elif expected_host and expected_host not in actual:
                        report.add(
                            WARN, name,
                            f"request URL is not {expected_host}: {actual[:60]!r}", step,
                        )
                if field_name == "evidence" and actual:
                    if "\n" in actual:
                        report.add(ERROR, name, "evidence JSON is not minified (contains a newline)", step)
                    try:
                        json.loads(actual)
                    except ValueError:
                        report.add(WARN, name, "evidence is not parseable JSON", step)

            if record is None:
                report.add(INFO, name, "no recorded call for this step", step)
                continue
            if getattr(record, "server_fault", False):
                report.add(
                    WARN, name,
                    "step failed on a Metrc server fault, not a rejected request", step,
                )
            blanks = [
                f for f, c in sm.columns.items()
                if not str(ws[f"{c}{row}"].value or "").strip()
            ]
            if blanks:
                report.add(INFO, name, f"blank: {', '.join(sorted(blanks))}", step)

    return report


def to_json(workbook_path: str, records: list, *, sheets: list | None = None) -> dict:
    """The filled evaluation as structured data, alongside the workbook."""
    wb = openpyxl.load_workbook(workbook_path)
    targets = sheets or [
        ws.title for ws in wb.worksheets if map_sheet(ws) and map_sheet(ws).steps
    ]

    out = {"sheets": [], "summary": {}}
    total = ok = 0
    for name in targets:
        ws = wb[name]
        sm = map_sheet(ws)
        steps = []
        for step, row in sm.steps.items():
            record = record_for(records, name, step)
            total += 1
            status = record.status if record else None
            if status == 200:
                ok += 1
            entry = {
                "step": step,
                "task": sm.step_tasks.get(step, ""),
                "result_code": status,
                "license_number": record.license_number if record else "",
                "object_ids": record.object_ids if record else [],
                "tags": record.tags if record else [],
                "names": record.names if record else [],
                "last_modified": record.last_modified if record else "",
                "request": {
                    "method": record.method if record else "",
                    "url": record.url if record else "",
                    "body": record.request_body if record else None,
                },
                "response": record.response_body if record else None,
            }
            if record is not None and getattr(record, "server_fault", False):
                entry["server_fault"] = True
            steps.append(entry)
        out["sheets"].append({"name": name, "steps": steps})

    out["summary"] = {
        "steps_total": total,
        "steps_ok": ok,
        "steps_not_ok": total - ok,
        "sheets": len(out["sheets"]),
    }
    return out
