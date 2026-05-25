"""
geocode_dispensaries.py — Fill in lat/lng for dispensaries.json via Nominatim.

For each entry missing `latitude`/`longitude`, query Nominatim with the
formatted address. Writes results back to dispensaries.json. Respects
Nominatim's 1 req/sec usage policy.

Usage:
  python scripts/geocode_dispensaries.py [--json dispensaries.json] [--force]
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "terpenomics-geocode/1.0 (jambola441@gmail.com)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def geocode(address: str) -> tuple[float, float] | None:
    qs = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    req = urllib.request.Request(f"{NOMINATIM}?{qs}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return None
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def format_address(addr: dict) -> str:
    return f"{addr['street']}, {addr['city']}, {addr['state']} {addr['zip']}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", default="dispensaries.json")
    p.add_argument("--force", action="store_true", help="Re-geocode entries that already have lat/lng")
    args = p.parse_args()

    src = Path(args.json)
    entries = json.loads(src.read_text())

    geocoded = skipped = failed = 0
    for i, e in enumerate(entries):
        slug = e["slug"]
        addr = e.get("address")
        if not addr:
            print(f"[{i+1:2d}/{len(entries)}] {slug:40s} no address — skip")
            skipped += 1
            continue
        if not args.force and e.get("latitude") is not None and e.get("longitude") is not None:
            print(f"[{i+1:2d}/{len(entries)}] {slug:40s} already geocoded — skip")
            skipped += 1
            continue

        formatted = format_address(addr)
        print(f"[{i+1:2d}/{len(entries)}] {slug:40s} {formatted}")
        result = geocode(formatted)
        if result is None:
            print("  -> no result")
            failed += 1
        else:
            lat, lng = result
            e["latitude"] = lat
            e["longitude"] = lng
            print(f"  -> {lat:.6f}, {lng:.6f}")
            geocoded += 1

        # Nominatim policy: max 1 request per second
        time.sleep(1.1)

    src.write_text(json.dumps(entries, indent=2) + "\n")
    print(f"\ngeocoded={geocoded} skipped={skipped} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
