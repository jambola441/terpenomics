#!/usr/bin/env python3
"""
migrate_enrich_cache_v6.py — carry a v5 enrich cache forward to v6.

_ENRICH_VERSION exists so a taxonomy change re-enriches stale rows automatically,
and it is deliberately coarse: one stamp per entry, not per category. So bumping
5 -> 6 invalidates every cached answer even though the v6 change touches only
merch — form-factor subtypes, pack/size in variant, colour or flavour in strain.
Re-enriching a 19k-listing fleet to fix 7.7% of it costs about $5-6.

The v5 -> v6 diff is merch-only, so a non-merch v5 answer is still exactly what
v6 would produce. This restamps those to 6 and drops the merch entries, which
then re-enrich on the next run for roughly $0.40.

This is sound ONLY for 5 -> 6. Any later bump needs its own reasoning about which
categories actually changed — do not generalise it into a "restamp the cache"
tool.

    python scripts/migrate_enrich_cache_v6.py            # report, change nothing
    python scripts/migrate_enrich_cache_v6.py --run
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "enrich_cache"
FROM_V, TO_V = 5, 6


def main() -> None:
    ap = argparse.ArgumentParser(description="Restamp non-merch v5 cache entries to v6")
    ap.add_argument("--run", action="store_true", help="write the changes (default: dry run)")
    args = ap.parse_args()

    files = sorted(p for p in CACHE_DIR.glob("*.json") if not p.name.startswith("_"))
    if not files:
        sys.exit(f"no cache files in {CACHE_DIR}")

    totals = Counter()
    for path in files:
        try:
            cache = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [skip] {path.name}: {type(exc).__name__}")
            totals["unreadable"] += 1
            continue

        kept, restamped, dropped, other_v = {}, 0, 0, 0
        for key, entry in cache.items():
            if not isinstance(entry, dict):
                continue
            version = entry.get("v")
            if version == TO_V:                      # already migrated
                kept[key] = entry
                continue
            if version != FROM_V:                    # older or unstamped — let it re-enrich
                other_v += 1
                continue
            if (entry.get("category") or "").lower() == "merch":
                dropped += 1                         # v6 changes these; must be redone
                continue
            kept[key] = {**entry, "v": TO_V}
            restamped += 1

        totals["restamped"] += restamped
        totals["dropped"] += dropped
        totals["other_version"] += other_v
        if restamped or dropped:
            print(f"  {path.name:44s} restamped={restamped:5d} dropped(merch)={dropped:4d}"
                  + (f" other_v={other_v}" if other_v else ""))
        if args.run:
            path.write_text(json.dumps(kept, indent=1, sort_keys=True))

    print(f"\n{'wrote' if args.run else 'would write'}: "
          f"{totals['restamped']:,} entries restamped v{FROM_V}->v{TO_V}, "
          f"{totals['dropped']:,} merch entries dropped (they re-enrich on the next run)")
    if totals["other_version"]:
        print(f"  {totals['other_version']:,} entries at another version were left to re-enrich")
    if not args.run:
        print("\nPass --run to apply.")


if __name__ == "__main__":
    main()
