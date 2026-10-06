#!/usr/bin/env python3
"""
scrape.py — Single entry point to scrape any dispensary by slug.

Reads dispensaries.json, picks the right scraper, runs it (scrape + enrich into a
CSV), then imports the CSV into the DB — where catalog matching also happens.

Usage
-----
  python scripts/scrape.py --slug the-spot-bk
  python scripts/scrape.py --slug the-spot-bk --dry-run
  python scripts/scrape.py --all                      # every store whose status is "active"
  python scripts/scrape.py --all --include-pending    # ... plus "pending" ones
  python scripts/scrape.py --all --import-only        # re-import the newest CSV per store
  python scripts/scrape.py --all --summary run.json   # per-store results for monitoring
  python scripts/scrape.py --all --via-http           # from a sandbox: the database over HTTPS

Exit code: 0 when every targeted store succeeded, 1 when any failed. A store fails
when its scraper exits non-zero or times out, produces no CSV or an empty one, its
import fails, or enrichment answered fewer than half its rows. Before, this script
exited 0 no matter what, so a run with every Dutchie store broken reported "ok". A
partial scrape (fewer products than the platform reported) is imported, retires
nothing, and is reported as a warning rather than a failure.
"""

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper_common import read_scrape_meta, run_stamp  # noqa: E402

ROOT      = Path(__file__).parent.parent
DISPOS    = ROOT / "dispensaries.json"
OUT_DIR   = ROOT / "data" / "scrapes"
SCRIPTS   = ROOT / "scripts"
PROTOS    = ROOT / "prototypes"

SCRAPER = {
    "dutchie_graphql": PROTOS / "dutchie-scraper"  / "scrape_graphql.py",
    "dutchie_plus":    PROTOS / "dutchie-scraper"   / "scrape.py",
    "flowhub":         PROTOS / "dutchie-scraper"   / "scrape.py",
    "tymber":          PROTOS / "tymber-scraper"    / "scrape_blaze.py",
    "alleaves":        PROTOS / "alleaves-scraper"  / "scrape.py",
    "travel_agency":   PROTOS / "travel-agency-scraper" / "scrape.py",
}

# One store's scrape + enrich. The slowest healthy store takes a few minutes; this is
# a ceiling for a hung connection or a model retry loop, so it never eats the run.
SCRAPER_TIMEOUT_SEC = int(os.environ.get("SCRAPER_TIMEOUT_SEC", "1200"))
IMPORT_TIMEOUT_SEC = int(os.environ.get("IMPORT_TIMEOUT_SEC", "900"))
# Below this share of rows answered, a store's enrichment is treated as broken.
MIN_ENRICHED_SHARE = 0.5

EMPTY_USAGE = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0,
               "cache_read_tokens": 0, "cost_usd": 0.0, "failed_rows": 0}


def load_registry() -> list[dict]:
    return json.loads(DISPOS.read_text())


def csv_path(slug: str, stamp: str | None = None) -> Path:
    suffix = f"_{stamp}" if stamp else ""
    return OUT_DIR / f"{slug}{suffix}.csv"


def find_latest_csv(slug: str) -> Path | None:
    """Newest CSV for a slug, for --import-only (no fresh scrape produced a path).
    Prefers timestamped files; falls back to legacy {slug}.csv / {slug}_listings.csv."""
    stamped = re.compile(rf"^{re.escape(slug)}_\d{{8}}T\d{{6}}Z\.csv$")
    matches = sorted(p for p in OUT_DIR.glob(f"{slug}_*.csv") if stamped.match(p.name))
    if matches:
        return matches[-1]  # timestamp sorts chronologically
    for legacy in (OUT_DIR / f"{slug}.csv", OUT_DIR / f"{slug}_listings.csv"):
        if legacy.exists():
            return legacy
    return None


def build_scraper_cmd(d: dict, out: str, parallel: bool = False, no_enrich: bool = False,
                      passes: int = 50, model: str = "haiku") -> list[str] | None:
    platform = d["platform"]
    slug     = d["slug"]
    name     = d["name"]
    scraper  = SCRAPER.get(platform)

    if not scraper:
        return None  # unsupported

    if platform == "dutchie_graphql":
        if not d.get("dutchie_id"):
            print(f"  [skip] {slug}: missing dutchie_id", file=sys.stderr)
            return None
        cmd = [sys.executable, str(scraper), "--dutchie-id", d["dutchie_id"],
               "--dispensary-slug", slug, "--name", name, "--out", out]
    elif platform in ("dutchie_plus", "flowhub"):
        if not d.get("menu_url"):
            print(f"  [skip] {slug}: missing menu_url", file=sys.stderr)
            return None
        cmd = [sys.executable, str(scraper), "--url", d["menu_url"],
               "--dispensary-slug", slug, "--name", name, "--out", out]
    elif platform == "tymber":
        if not d.get("blaze_id"):
            print(f"  [skip] {slug}: missing blaze_id", file=sys.stderr)
            return None
        cmd = [sys.executable, str(scraper), "--blaze-id", d["blaze_id"],
               "--dispensary-slug", slug, "--name", name, "--out", out]
    elif platform == "alleaves":
        if not d.get("alleaves_tenant"):
            print(f"  [skip] {slug}: missing alleaves_tenant", file=sys.stderr)
            return None
        cmd = [sys.executable, str(scraper), "--tenant", d["alleaves_tenant"],
               "--dispensary-slug", slug, "--out", out]
    elif platform == "travel_agency":
        cmd = [sys.executable, str(scraper), "--output", out]
    else:
        return None

    if parallel:
        cmd.append("--parallel")
    if no_enrich:
        cmd.append("--no-enrich")
    if model != "haiku":
        cmd.extend(["--model", model])
    if passes != 50 and platform in ("dutchie_plus", "flowhub"):
        cmd.extend(["--passes", str(passes)])
    return cmd


# The child currently running, so a SIGTERM to this process (run_scrape_cron's
# timeout) can take it down too. Each child runs in its own session to be killable
# as a tree on its own timeout — which also puts it out of reach of a kill aimed at
# this process's group, so it has to be forwarded explicitly.
_active_child: subprocess.Popen | None = None


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _on_sigterm(signum, frame) -> None:
    if _active_child is not None:
        _kill_tree(_active_child)
    sys.exit(128 + signum)


def run_bounded(cmd: list[str], timeout: int) -> int:
    """Run a child in its own process group and kill the whole group on timeout.

    subprocess.run(timeout=) kills only the direct child; a scraper's own children
    (and anything an importer spawned) would carry on as orphans holding the lock's
    resources. 124 is the conventional timeout exit code.
    """
    global _active_child
    proc = subprocess.Popen(cmd, cwd=ROOT, start_new_session=True)
    _active_child = proc
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  [error] timed out after {timeout}s — killing {' '.join(cmd[:2])}",
              file=sys.stderr)
        _kill_tree(proc)
        proc.wait()
        return 124
    finally:
        _active_child = None


def read_usage(csv_file: Path) -> dict:
    path = csv_file.with_suffix(".usage.json")
    if path.exists():
        return {**EMPTY_USAGE, **json.loads(path.read_text())}
    return dict(EMPTY_USAGE)


def count_rows(csv_file: Path) -> int:
    try:
        with open(csv_file, newline="", encoding="utf-8") as f:
            return sum(1 for _ in csv.DictReader(f))
    except OSError:
        return 0


def run_import(csv_file: Path, dry_run: bool) -> tuple[bool, str]:
    if not csv_file.exists():
        return False, f"no CSV at {csv_file.name}"
    if dry_run:
        print(f"  [dry-run] would import: {csv_file.name}")
        return True, "dry-run"
    code = run_bounded([sys.executable, str(SCRIPTS / "import_listings.py"),
                        "--csv", str(csv_file)], IMPORT_TIMEOUT_SEC)
    reasons = {2: "dispensary not in DB (run import_dispensaries.py)",
               3: "empty CSV", 124: "import timed out"}
    return code == 0, ("imported" if code == 0 else reasons.get(code, f"import exited {code}"))


def run_one(d: dict, dry_run: bool, import_only: bool = False, scrape_only: bool = False,
            parallel: bool = False, no_enrich: bool = False, passes: int = 50,
            model: str = "haiku") -> dict:
    """One store, start to finish. Returns a result row for the run summary."""
    slug = d["slug"]
    platform = d["platform"]
    result = {"slug": slug, "platform": platform, "ok": False, "stage": "", "detail": "",
              "warning": None, "rows": 0, "usage": dict(EMPTY_USAGE), "seconds": 0.0}
    t0 = time.time()

    print(f"\n{'='*60}")
    print(f"  {d['name']}  [{platform}]")

    try:
        if import_only:
            latest = find_latest_csv(slug)
            if latest is None:
                result.update(stage="import", detail="no CSV found")
                return result
            result["rows"] = count_rows(latest)
            ok, detail = run_import(latest, dry_run)
            result.update(ok=ok, stage="import", detail=detail)
            return result

        out_path = csv_path(slug, run_stamp())
        cmd = build_scraper_cmd(d, str(out_path), parallel=parallel, no_enrich=no_enrich,
                                passes=passes, model=model)
        if cmd is None:
            result.update(stage="scrape", detail=f"unsupported platform '{platform}'")
            return result

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        if dry_run:
            print(f"  [dry-run] would run: {' '.join(cmd)}")
            result.update(ok=True, stage="scrape", detail="dry-run")
            return result

        code = run_bounded(cmd, SCRAPER_TIMEOUT_SEC)
        if code != 0:
            result.update(stage="scrape", detail="timed out" if code == 124 else f"scraper exited {code}")
            return result
        if not out_path.exists():
            result.update(stage="scrape", detail="scraper wrote no CSV")
            return result

        usage = read_usage(out_path)
        rows = count_rows(out_path)
        result.update(usage=usage, rows=rows)
        if rows == 0:
            result.update(stage="scrape", detail="scrape returned 0 rows")
            return result
        degraded = (not no_enrich and usage.get("failed_rows", 0)
                    and usage["failed_rows"] > (1 - MIN_ENRICHED_SHARE) * rows)
        meta = read_scrape_meta(str(out_path))
        if meta.get("partial"):
            # A short menu, not a broken store: what arrived is imported and nothing is
            # retired. A warning, not a failure, so a chronic one (Flowhub stalls near
            # 810 of 861) does not turn every run red and bury the real failures.
            result["warning"] = (f"partial scrape {meta.get('collected')}/"
                                 f"{meta.get('reported_total')} products (nothing retired)")
        if scrape_only:
            result.update(ok=not degraded, stage="scrape",
                          detail="enrichment mostly failed" if degraded else "scraped")
            return result
        # Import even when enrichment degraded: the importer keeps the stored identity
        # of every row marked enrich_failed, so prices and stock still refresh. The
        # store is still reported as failed so someone looks at why.
        ok, detail = run_import(out_path, dry_run=False)
        if degraded:
            ok, detail = False, f"enrichment answered only {rows - usage['failed_rows']}/{rows} rows; {detail}"
        result.update(ok=ok, stage="import", detail=detail)
        return result
    finally:
        result["seconds"] = round(time.time() - t0, 1)


def select_targets(registry: list[dict], slug: str | None, include_pending: bool) -> list[dict]:
    """--slug runs that store whatever its status (it was asked for by name); --all runs
    "active" stores, plus "pending" with --include-pending. "inactive" and "unsupported"
    stores used to be attempted — and fail — every day, burying real failures."""
    if slug:
        return [d for d in registry if d["slug"] == slug]
    wanted = {"active"} | ({"pending"} if include_pending else set())
    return [d for d in registry if d.get("status", "active") in wanted]


def _snapshot_size_prices() -> None:
    """Typical prices for size_choice, read once per run and handed to every store's
    scraper and importer through SIZE_PRICES, so they all choose sizes against the same
    prices (and the database is read once, not once per store). Without it, sizes are
    chosen without prices; the run goes on either way."""
    if os.environ.get("SIZE_PRICES"):
        return
    try:
        import tempfile
        import size_choice
        book = size_choice.PriceBook.from_db()
        fd, path = tempfile.mkstemp(prefix="size_prices_", suffix=".json")
        os.close(fd)
        book.save(path)
        os.environ["SIZE_PRICES"] = path
        print(f"size prices: {len(book.category)} category sizes, {len(book.brand_per_g)} brand "
              f"price-per-gram, {len(book.product)} catalog product sizes -> {path}")
    except Exception as exc:  # noqa: BLE001 — prices sharpen a choice; a run never fails for them
        print(f"  [warn] size prices not read ({exc}); sizes will be chosen without them",
              file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape dispensary menus and import into DB")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="Dispensary slug (from dispensaries.json)")
    group.add_argument("--all",  action="store_true", help="Run every active dispensary")
    parser.add_argument("--include-pending", action="store_true",
                        help="With --all, also run stores whose status is 'pending'")
    parser.add_argument("--dry-run",     action="store_true", help="Print commands without running")
    parser.add_argument("--import-only", action="store_true", help="Skip scraping; import existing CSVs from data/scrapes/")
    parser.add_argument("--scrape-only", action="store_true", help="Scrape to CSV only; skip DB import")
    parser.add_argument("--parallel",    action="store_true", help="Fetch pages concurrently within each dispensary scrape")
    parser.add_argument("--no-enrich",   action="store_true", help="Skip enrichment; write raw scraped data only")
    parser.add_argument("--model",       default="haiku", help="Enrichment model id (see MODELS in scripts/enrich.py)")
    parser.add_argument("--passes",      type=int, default=50, help="Flowhub: max page sweeps until all reported products collected (default 50)")
    parser.add_argument("--summary",     help="Write a JSON summary of this run (per store) to this path")
    parser.add_argument("--via-http",    action="store_true",
                        help="Reach the database over Supabase's REST API instead of DATABASE_URL, "
                             "for a machine that cannot open a Postgres connection (DB_ACCESS.md). "
                             "Same as DB_VIA_HTTP=1")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _on_sigterm)
    if args.via_http:
        # Every child reads it: the importer, and the scrapers' enrich cache when it
        # lives in Postgres (ENRICH_CACHE=db).
        os.environ["DB_VIA_HTTP"] = "1"

    registry = load_registry()
    targets = select_targets(registry, args.slug, args.include_pending)
    if args.slug and not targets:
        print(f"Unknown slug: {args.slug!r}", file=sys.stderr)
        print(f"Known slugs: {', '.join(d['slug'] for d in registry)}", file=sys.stderr)
        sys.exit(1)
    if args.slug and targets[0].get("status") in ("inactive", "unsupported"):
        print(f"  [note] {args.slug} is marked {targets[0]['status']} in dispensaries.json")
    if args.all:
        skipped = [d["slug"] for d in registry if d not in targets]
        if skipped:
            print(f"Skipping {len(skipped)} store(s) not marked active: {', '.join(skipped)}")

    if not args.dry_run and not args.no_enrich:
        _snapshot_size_prices()

    results = []
    for d in targets:
        res = run_one(d, dry_run=args.dry_run, import_only=args.import_only,
                      scrape_only=args.scrape_only, parallel=args.parallel,
                      no_enrich=args.no_enrich, passes=args.passes, model=args.model)
        results.append(res)
        u = res["usage"]
        if u.get("input_tokens") or u.get("cache_read_tokens"):
            print(f"  enrich: input={u.get('input_tokens',0):,}  output={u.get('output_tokens',0):,}  "
                  f"cost=${u.get('cost_usd',0.0):.4f}")
        status = "ok" if res["ok"] else "FAILED"
        print(f"  -> {status} ({res['stage']}: {res['detail']}, {res['rows']} rows, {res['seconds']}s)"
              + (f"  WARN: {res['warning']}" if res.get("warning") else ""))

    failed = [r for r in results if not r["ok"]]
    warned = [r for r in results if r["ok"] and r.get("warning")]
    cost = round(sum(r["usage"].get("cost_usd", 0.0) for r in results), 4)
    print(f"\n{'='*60}")
    print(f"Done.  ok={len(results) - len(failed)}  failed={len(failed)}  warned={len(warned)}  "
          f"enrich cost=${cost:.4f}")
    for r in failed:
        print(f"  FAILED {r['slug']:34} {r['stage']}: {r['detail']}")
    for r in warned:
        print(f"  WARN   {r['slug']:34} {r['warning']}")

    if args.summary:
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary).write_text(json.dumps({
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ok": len(results) - len(failed), "failed": len(failed), "warned": len(warned),
            "cost_usd": cost,
            "stores": results,
        }, indent=2))

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
