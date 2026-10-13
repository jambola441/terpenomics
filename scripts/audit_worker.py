#!/usr/bin/env python3
"""
audit_worker.py — Runs the admin audits' queued jobs (audit_jobs, db/migrations/0020).

The admin pages (routes/admin/audits.py) only write rows and queue jobs; this does the
work (scripts/audits.py): build a run (flags, sample, evidence; then the LLM judge when
the run has a model), judge a run, measure a proposal, apply an approved one. One job at
a time, oldest first.

  python scripts/audit_worker.py              # loop: poll every AUDIT_POLL_SEC (default 10)
  python scripts/audit_worker.py --drain      # run what is queued, then exit (a cron job)
  python scripts/audit_worker.py --drain --max-minutes 14

On Render: a cron job every 15 minutes with --drain --max-minutes 14 (scripts/render.yaml,
terpenomics-audit-worker), or a background worker running the loop. Needs SUPABASE_URL
and SUPABASE_SERVICE_ROLE_KEY (all reads and writes are over Supabase's REST API),
ANTHROPIC_API_KEY for the LLM judge, OPENROUTER_API_KEY for Jev (measuring and
re-matching re-read listings; without it they use the stored readings), and
READING_EXAMPLES=db once the examples are imported.

A job left 'running' by a worker that died is taken again after STALE_MINUTES.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audits  # noqa: E402

STALE_MINUTES = 60
MAX_ATTEMPTS = 3


def handlers() -> dict:
    return {
        "build_run": lambda p: audits.build_run(p["run_id"]),
        "judge_run": lambda p: audits.judge_run(p["run_id"]),
        "measure_proposal": lambda p: audits.measure_proposal(p["proposal_id"]),
        "apply_proposal": lambda p: audits.apply_proposal(p["proposal_id"]),
    }


def claim() -> dict | None:
    """The oldest queued job (or one stuck running), marked running. A claim is an
    update filtered on the status read, so two workers cannot both take one."""
    import db_http
    stale = (datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES)).replace(tzinfo=None).isoformat()
    for query in ("status=eq.queued", f"status=eq.running&started_at=lt.{stale}"):
        for job in db_http.select("audit_jobs", f"select=*&{query}&order=created_at&limit=5"):
            if (job.get("attempts") or 0) >= MAX_ATTEMPTS:
                db_http.update("audit_jobs", f"id=eq.{job['id']}",
                               {"status": "failed", "error": job.get("error") or "too many attempts"})
                continue
            got = db_http.update("audit_jobs", f"id=eq.{job['id']}&status=eq.{job['status']}",
                                 {"status": "running", "started_at": audits.now(),
                                  "attempts": (job.get("attempts") or 0) + 1})
            if got:
                return got[0]
    return None


def run_one(job: dict) -> bool:
    """Run a claimed job; True when it finished. A failure is recorded on the job, and
    on the run or proposal it was for, so the page shows it."""
    import catalog_reading
    import db_http
    catalog_reading.reload_examples()          # an applied example proposal counts at once
    handler = handlers().get(job["kind"])
    try:
        if handler is None:
            raise ValueError(f"unknown job kind {job['kind']!r}")
        handler(job.get("payload") or {})
    except Exception as exc:
        traceback.print_exc()
        error = f"{type(exc).__name__}: {exc}"[:2000]
        db_http.update("audit_jobs", f"id=eq.{job['id']}",
                       {"status": "failed", "error": error, "finished_at": audits.now()})
        payload = job.get("payload") or {}
        if payload.get("run_id"):
            db_http.update("audit_runs", f"id=eq.{payload['run_id']}", {"status": "failed", "error": error})
        if payload.get("proposal_id"):
            db_http.update("audit_proposals", f"id=eq.{payload['proposal_id']}", {"status": "failed", "error": error})
        return False
    db_http.update("audit_jobs", f"id=eq.{job['id']}", {"status": "done", "finished_at": audits.now(), "error": None})
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drain", action="store_true", help="run the queued jobs, then exit")
    ap.add_argument("--max-minutes", type=float, default=0, help="with --drain: start no job after this long")
    args = ap.parse_args(argv)
    poll = float(os.environ.get("AUDIT_POLL_SEC", "10"))
    started = time.monotonic()
    done = failed = 0
    while True:
        if args.max_minutes and time.monotonic() - started > args.max_minutes * 60:
            break
        job = claim()
        if job is None:
            if args.drain:
                break
            time.sleep(poll)
            continue
        print(f"[audit-worker] {job['kind']} {job.get('payload')}", flush=True)
        if run_one(job):
            done += 1
        else:
            failed += 1
    print(f"[audit-worker] {done} job(s) done, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
