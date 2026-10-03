"""Collects CallRecords from a run and persists them as a replayable transcript."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .client import CallRecord


class Recorder:
    def __init__(self, run_dir: str, run_id: str | None = None):
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = os.path.join(run_dir, self.run_id)
        self.records: list[CallRecord] = []
        os.makedirs(self.run_dir, exist_ok=True)

    # The live append-only stream, written before a step annotates its result.
    RAW = "calls.raw.jsonl"
    # The finalised transcript, written once every annotation is attached.
    FINAL = "calls.jsonl"

    def add(self, record: CallRecord) -> CallRecord:
        self.records.append(record)
        # Append-only, so a crash mid-run still leaves usable evidence. This
        # snapshot predates any annotation the step attaches afterwards.
        with open(os.path.join(self.run_dir, self.RAW), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), default=str) + "\n")
        return record

    def flush(self) -> str:
        """Write the transcript with every annotation applied.

        Steps attach ids, tags and names to a record after the call returns, so
        the append-only stream is always one step behind. Everything that reads
        a run back — filling the workbook above all — needs the final state.
        """
        path = os.path.join(self.run_dir, self.FINAL)
        with open(path, "w", encoding="utf-8") as fh:
            for record in self.records:
                fh.write(json.dumps(record.to_dict(), default=str) + "\n")
        return path

    def for_step(self, sheet: str, step: str) -> CallRecord | None:
        """The record a given workbook cell block should report.

        When a step makes several calls, the last successful one is the one
        whose evidence belongs in the sheet.
        """
        matches = [r for r in self.records if r.sheet == sheet and r.step == step]
        if not matches:
            return None
        for record in reversed(matches):
            if record.ok:
                return record
        return matches[-1]

    def steps_for(self, sheet: str) -> list[str]:
        seen: list[str] = []
        for record in self.records:
            if record.sheet == sheet and record.step and record.step not in seen:
                seen.append(record.step)
        return seen

    def summary(self) -> dict:
        by_status: dict[str, int] = {}
        for record in self.records:
            key = str(record.status or "error")
            by_status[key] = by_status.get(key, 0) + 1
        failures = [
            {"sheet": r.sheet, "step": r.step, "endpoint": r.endpoint,
             "status": r.status, "error": r.error or str(r.response_body)[:300]}
            for r in self.records if not r.ok
        ]
        return {
            "run_id": self.run_id,
            "total_calls": len(self.records),
            "by_status": by_status,
            "failures": failures,
        }

    def write_summary(self) -> str:
        self.flush()
        path = os.path.join(self.run_dir, "summary.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.summary(), fh, indent=2, default=str)
        return path
