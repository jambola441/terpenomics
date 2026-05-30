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
import subprocess
import sys
import json
from pathlib import Path

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


def csv_path(slug: str) -> Path:
    return OUT_DIR / f"{slug}.csv"


def build_scraper_cmd(d: dict) -> list[str] | None:
    platform = d["platform"]
    slug     = d["slug"]
    name     = d["name"]
    scraper  = SCRAPER.get(platform)

    if not scraper:
        return None  # unsupported

    out = str(csv_path(slug))

    if platform == "dutchie_graphql":
        if not d.get("dutchie_id"):
            print(f"  [skip] {slug}: missing dutchie_id", file=sys.stderr)
            return None
        return [
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
        return [
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
        return [
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
        return [
            sys.executable, str(scraper),
            "--tenant", d["alleaves_tenant"],
            "--dispensary-slug", slug,
            "--out", out,
        ]

    elif platform == "travel_agency":
        return [
            sys.executable, str(scraper),
            "--output", out,
        ]

    return None


def run_import(slug: str, dry_run: bool) -> bool:
    csv = csv_path(slug)
    if not csv.exists():
        print(f"  [skip] no CSV at {csv}")
        return False
    import_cmd = [sys.executable, str(SCRIPTS / "import_listings.py"), "--csv", str(csv)]
    if dry_run:
        print(f"  [dry-run] would import: {csv.name}")
        return True
    result = subprocess.run(import_cmd, cwd=ROOT)
    return result.returncode == 0


def run_one(d: dict, dry_run: bool, import_only: bool = False) -> bool:
    slug = d["slug"]
    platform = d["platform"]

    print(f"\n{'='*60}")
    print(f"  {d['name']}  [{platform}]")

    if import_only:
        return run_import(slug, dry_run)

    cmd = build_scraper_cmd(d)
    if cmd is None:
        print(f"  [skip] {slug}: unsupported platform '{platform}'")
        return False

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"  [dry-run] would run: {' '.join(cmd)}")
        return True

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"  [error] scraper exited {result.returncode}", file=sys.stderr)
        return False

    return run_import(slug, dry_run=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape dispensary menus and import into DB")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="Dispensary slug (from dispensaries.json)")
    group.add_argument("--all",  action="store_true", help="Run all supported dispensaries")
    parser.add_argument("--dry-run",     action="store_true", help="Print commands without running")
    parser.add_argument("--import-only", action="store_true", help="Skip scraping; import existing CSVs from data/scrapes/")
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
    for d in targets:
        success = run_one(d, dry_run=args.dry_run, import_only=args.import_only)
        if success:
            ok += 1
        elif args.import_only or d["platform"] in SCRAPER:
            failed += 1
        else:
            skipped += 1

    print(f"\n{'='*60}")
    print(f"Done.  ok={ok}  skipped={skipped}  failed={failed}")


if __name__ == "__main__":
    main()
