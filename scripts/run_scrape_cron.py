#!/usr/bin/env python3
"""
run_scrape_cron.py — One robust end-to-end pipeline run for the scrape worker.

Wraps `scripts/scrape.py --all`, adding the operational concerns a scheduled job
needs but the orchestrator itself doesn't care about:

  * structured, timestamped logging to stdout (Render captures this)
  * an overlap lock so two runs can never clobber the shared enrich cache
  * a hard wall-clock timeout so a hung scraper can't block tomorrow's run
  * a heartbeat file on the persistent disk (last run time / status / duration,
    and which stores failed and why — from scrape.py's --summary)
  * a non-zero exit code on failure, and an optional POST to ALERT_WEBHOOK_URL
    (Slack/Discord-style {"text": ...}) so a failed morning run is noticed the same
    morning rather than weeks later

One-off:        python scripts/run_scrape_cron.py
Custom sweep:   SCRAPE_ARGS="--all --parallel --no-enrich" python scripts/run_scrape_cron.py

The worker (scrape_worker.py) imports run_pipeline() and calls it on a schedule.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"
# data/enrich_cache is where the Render persistent disk is mounted, so the lock
# and heartbeat live alongside the cache they protect — all on durable storage.
CACHE_DIR = ROOT / "data" / "enrich_cache"
LOCK_FILE = CACHE_DIR / "_cron.lock"
STATUS_FILE = CACHE_DIR / "_cron_status.json"
SUMMARY_FILE = CACHE_DIR / "_last_run.json"

# A full --all sweep is ~10-20 min; 90 min is a generous ceiling that still
# guarantees a hung scraper is killed long before the next daily run.
DEFAULT_TIMEOUT_SEC = int(os.environ.get("SCRAPE_TIMEOUT_SEC", str(90 * 60)))

# What to hand scrape.py. Override via env for a one-off (e.g. drop --parallel).
SCRAPE_ARGS = os.environ.get("SCRAPE_ARGS", "--all --parallel")

log = logging.getLogger("scrape-cron")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )


def _write_status(**fields) -> None:
    """Best-effort heartbeat. Never let a status write failure abort a run."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps(fields, indent=2, default=str))
    except OSError as exc:
        log.warning("could not write status file: %s", exc)


class _Lock:
    """Best-effort overlap guard. A lock older than max_age is presumed dead
    (the holder timed out or crashed) and reclaimed."""

    def __init__(self, path: Path, max_age: int):
        self.path = path
        self.max_age = max_age

    def __enter__(self) -> "_Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age = time.time() - self.path.stat().st_mtime
            if age < self.max_age:
                raise RuntimeError(
                    f"another run is in progress (lock {int(age)}s old); aborting"
                )
            log.warning("reclaiming stale lock (%ds old)", int(age))
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *exc) -> None:
        self.path.unlink(missing_ok=True)


def _alert(text: str) -> None:
    """Best-effort notification. A webhook outage must not fail the run."""
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).close()
    except Exception as exc:  # noqa: BLE001
        log.warning("alert webhook failed: %s", exc)


def _read_summary() -> dict:
    try:
        return json.loads(SUMMARY_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def run_pipeline(timeout: int = DEFAULT_TIMEOUT_SEC) -> int:
    """Run one full scrape -> enrich -> import sweep.

    Returns a process-style exit code: 0 ok, 124 timeout, 75 lock contention
    (transient — not recorded as a real run), non-zero otherwise.
    """
    started = datetime.now(timezone.utc)
    cmd = [sys.executable, str(SCRIPTS / "scrape.py"), *shlex.split(SCRAPE_ARGS),
           "--summary", str(SUMMARY_FILE)]
    log.info("starting pipeline: %s", " ".join(cmd))
    SUMMARY_FILE.unlink(missing_ok=True)

    try:
        with _Lock(LOCK_FILE, timeout):
            _write_status(state="running", started_at=started)
            # Own process group, so a timeout kills the scraper and importer that
            # scrape.py started too — subprocess.run(timeout=) would orphan them.
            proc = subprocess.Popen(cmd, cwd=ROOT, start_new_session=True)
            try:
                code = proc.wait(timeout=timeout)
                state = "ok" if code == 0 else "failed"
            except subprocess.TimeoutExpired:
                # SIGTERM first: scrape.py forwards it to the scraper or importer it
                # is running, which live in their own sessions and so are not in
                # this process group. Then SIGKILL whatever is left of the group.
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                log.error("pipeline exceeded %ds timeout — killed", timeout)
                code, state = 124, "timeout"
    except RuntimeError as exc:  # lock contention — another run holds it
        log.error("%s", exc)
        return 75  # EX_TEMPFAIL; leave the existing heartbeat untouched
    except Exception:  # noqa: BLE001 — never let an unexpected error escape
        log.exception("pipeline crashed")
        code, state = 1, "crashed"

    finished = datetime.now(timezone.utc)
    dur = (finished - started).total_seconds()
    summary = _read_summary()
    failed = [s for s in summary.get("stores", []) if not s.get("ok")]
    warned = [s for s in summary.get("stores", []) if s.get("ok") and s.get("warning")]
    _write_status(
        state=state,
        started_at=started,
        finished_at=finished,
        duration_sec=round(dur),
        exit_code=code,
        stores_ok=summary.get("ok"),
        stores_failed=[{"slug": s["slug"], "stage": s["stage"], "detail": s["detail"]}
                       for s in failed],
        stores_warned=[{"slug": s["slug"], "warning": s["warning"]} for s in warned],
        enrich_cost_usd=summary.get("cost_usd"),
    )
    log.info("pipeline %s in %.0fs (exit %d)", state, dur, code)
    if code != 0:
        lines = [f"terpenomics scrape {state} (exit {code}, {dur / 60:.0f} min)"]
        lines += [f"• {s['slug']}: {s['stage']} — {s['detail']}" for s in failed[:15]]
        lines += [f"• {s['slug']} (warning): {s['warning']}" for s in warned[:5]]
        _alert("\n".join(lines))
    return code


def main() -> None:
    _setup_logging()
    sys.exit(run_pipeline())


if __name__ == "__main__":
    main()
