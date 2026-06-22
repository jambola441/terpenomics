#!/usr/bin/env python3
"""
scrape_worker.py — Long-running Render background worker that triggers the daily
dispensary scrape + enrich + import pipeline.

Render cron jobs can't mount a persistent disk, and the per-SKU enrich cache is
what keeps Haiku cheap (only new/changed products get re-enriched). So instead of
a cron job we run a background worker with a disk attached at data/enrich_cache,
and the worker schedules itself:

  * sleeps until the next run time, then runs one pipeline sweep
  * drift-free — the next time is recomputed from the wall clock every loop
  * DST-aware — the run time is interpreted in America/New_York each loop
  * crash-proof — a failed sweep is logged and the loop simply continues

Env:
  SCRAPE_RUN_AT_ET     "HH:MM" Eastern time to run daily (default "09:00")
  SCRAPE_RUN_ON_START  "true" to run once immediately on boot (default "false")
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from run_scrape_cron import _setup_logging, run_pipeline  # noqa: E402

ET = ZoneInfo("America/New_York")
log = logging.getLogger("scrape-worker")


def _parse_run_at(raw: str) -> tuple[int, int]:
    try:
        hh, mm = (int(x) for x in raw.split(":", 1))
        if 0 <= hh < 24 and 0 <= mm < 60:
            return hh, mm
    except ValueError:
        pass
    log.error("bad SCRAPE_RUN_AT_ET %r — falling back to 09:00", raw)
    return 9, 0


def _next_run(now: datetime, hh: int, mm: int) -> datetime:
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def main() -> None:
    _setup_logging()
    hh, mm = _parse_run_at(os.environ.get("SCRAPE_RUN_AT_ET", "09:00"))

    if os.environ.get("SCRAPE_RUN_ON_START", "false").lower() == "true":
        log.info("SCRAPE_RUN_ON_START set — running one sweep now")
        run_pipeline()

    log.info("worker up; daily run scheduled for %02d:%02d America/New_York", hh, mm)
    while True:
        now = datetime.now(ET)
        nxt = _next_run(now, hh, mm)
        sleep_s = (nxt - now).total_seconds()
        log.info("next run %s (in %.1f h)", nxt.isoformat(), sleep_s / 3600)
        time.sleep(sleep_s)
        # run_pipeline never raises (it captures everything and returns a code),
        # but guard anyway so the worker can't die on a surprise.
        try:
            run_pipeline()
        except Exception:  # noqa: BLE001
            log.exception("run_pipeline raised unexpectedly; continuing")


if __name__ == "__main__":
    main()
