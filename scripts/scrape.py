#!/usr/bin/env python3
"""
scrape.py — Single entry point to scrape any dispensary by slug.

Reads dispensaries.json, picks the right scraper, runs it, then imports the
resulting CSV into the DB.

Usage
-----
  python scripts/scrape.py --slug coney-island-cannabis
  python scripts/scrape.py --slug the-spot-bk --dry-run
  python scripts/scrape.py --all
  python scripts/scrape.py --all --dry-run
"""

import argparse
import os
import re
import subprocess
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper_common import run_stamp  # noqa: E402

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


def build_scraper_cmd(d: dict, out: str, parallel: bool = False, no_enrich: bool = False, passes: int = 1, model: str = "haiku") -> list[str] | None:
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
        cmd = [
            sys.executable, str(scraper),
            "--dutchie-id", d["dutchie_id"],
            "--dispensary-slug", slug,
            "--name", name,
            "--out", out,
        ]

    elif platform in ("dutchie_plus", "flowhub"):
        if not d.get("menu_url"):
            print(f"  [skip] {slug}: missing menu_url", file=sys.stderr)
            return None
        cmd = [
            sys.executable, str(scraper),
            "--url", d["menu_url"],
            "--dispensary-slug", slug,
            "--name", name,
            "--out", out,
        ]

    elif platform == "tymber":
        if not d.get("blaze_id"):
            print(f"  [skip] {slug}: missing blaze_id", file=sys.stderr)
            return None
        cmd = [
            sys.executable, str(scraper),
            "--blaze-id", d["blaze_id"],
            "--dispensary-slug", slug,
            "--name", name,
            "--out", out,
        ]

    elif platform == "alleaves":
        if not d.get("alleaves_tenant"):
            print(f"  [skip] {slug}: missing alleaves_tenant", file=sys.stderr)
            return None
        cmd = [
            sys.executable, str(scraper),
            "--tenant", d["alleaves_tenant"],
            "--dispensary-slug", slug,
            "--out", out,
        ]

    elif platform == "travel_agency":
        cmd = [
            sys.executable, str(scraper),
            "--output", out,
        ]

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


def read_usage(csv: Path) -> dict:
    path = csv.with_suffix(".usage.json")
    if path.exists():
        return json.loads(path.read_text())
    return {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0}


def run_import(csv: Path, dry_run: bool) -> bool:
    if not csv.exists():
        print(f"  [skip] no CSV at {csv}")
        return False
    import_cmd = [sys.executable, str(SCRIPTS / "import_listings.py"), "--csv", str(csv)]
    if dry_run:
        print(f"  [dry-run] would import: {csv.name}")
        return True
    result = subprocess.run(import_cmd, cwd=ROOT)
    return result.returncode == 0


def run_one(d: dict, dry_run: bool, import_only: bool = False, scrape_only: bool = False, parallel: bool = False, no_enrich: bool = False, passes: int = 1, model: str = "haiku") -> tuple[bool, dict]:
    slug = d["slug"]
    platform = d["platform"]
    empty_usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0}

    print(f"\n{'='*60}")
    print(f"  {d['name']}  [{platform}]")

    if import_only:
        latest = find_latest_csv(slug)
        if latest is None:
            print(f"  [skip] no CSV found for {slug}")
            return False, empty_usage
        return run_import(latest, dry_run), empty_usage

    out_path = csv_path(slug, run_stamp())
    cmd = build_scraper_cmd(d, str(out_path), parallel=parallel, no_enrich=no_enrich, passes=passes, model=model)
    if cmd is None:
        print(f"  [skip] {slug}: unsupported platform '{platform}'")
        return False, empty_usage

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"  [dry-run] would run: {' '.join(cmd)}")
        return True, empty_usage

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"  [error] scraper exited {result.returncode}", file=sys.stderr)
        return False, empty_usage

    usage = read_usage(out_path)
    if scrape_only:
        return True, usage
    return run_import(out_path, dry_run=False), usage


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape dispensary menus and import into DB")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="Dispensary slug (from dispensaries.json)")
    group.add_argument("--all",  action="store_true", help="Run all supported dispensaries")
    parser.add_argument("--dry-run",     action="store_true", help="Print commands without running")
    parser.add_argument("--import-only", action="store_true", help="Skip scraping; import existing CSVs from data/scrapes/")
    parser.add_argument("--scrape-only", action="store_true", help="Scrape to CSV only; skip DB import")
    parser.add_argument("--parallel",    action="store_true", help="Fetch pages concurrently within each dispensary scrape")
    parser.add_argument("--no-enrich",   action="store_true", help="Skip Haiku enrichment; write raw scraped data only")
    parser.add_argument("--model",       default="haiku", help="Enrichment model id (see MODELS in scripts/enrich.py)")
    parser.add_argument("--passes",      type=int, default=50, help="Flowhub: max page sweeps until all reported products collected (default 50)")
    args = parser.parse_args()

    registry = load_registry()

    if args.slug:
        matches = [d for d in registry if d["slug"] == args.slug]
        if not matches:
            slugs = [d["slug"] for d in registry]
            print(f"Unknown slug: {args.slug!r}", file=sys.stderr)
            print(f"Known slugs: {', '.join(slugs)}", file=sys.stderr)
            sys.exit(1)
        targets = matches
    else:
        targets = registry

    ok = skipped = failed = 0
    total_usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0}

    for d in targets:
        success, u = run_one(d, dry_run=args.dry_run, import_only=args.import_only, scrape_only=args.scrape_only, parallel=args.parallel, no_enrich=args.no_enrich, passes=args.passes, model=args.model)
        if success:
            ok += 1
            if not args.import_only and not args.dry_run:
                for k in ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens"):
                    total_usage[k] += u.get(k, 0)
                total_usage["cost_usd"] = round(total_usage["cost_usd"] + u.get("cost_usd", 0.0), 4)
                if u.get("input_tokens") or u.get("cache_read_tokens"):
                    print(f"  enrich: input={u.get('input_tokens',0):,}  output={u.get('output_tokens',0):,}  "
                          f"cache_write={u.get('cache_write_tokens',0):,}  cache_read={u.get('cache_read_tokens',0):,}  "
                          f"cost=${u.get('cost_usd',0.0):.4f}")
        elif args.import_only or d["platform"] in SCRAPER:
            failed += 1
        else:
            skipped += 1

    print(f"\n{'='*60}")
    print(f"Done.  ok={ok}  skipped={skipped}  failed={failed}")
    if not args.import_only and not args.dry_run and (total_usage["input_tokens"] or total_usage["cache_read_tokens"]):
        print(f"Enrich tokens — input: {total_usage['input_tokens']:,}  output: {total_usage['output_tokens']:,}  "
              f"cache_write: {total_usage['cache_write_tokens']:,}  cache_read: {total_usage['cache_read_tokens']:,}")
        print(f"Estimated cost: ${total_usage['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
