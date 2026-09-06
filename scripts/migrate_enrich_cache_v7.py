#!/usr/bin/env python3
"""
migrate_enrich_cache_v7.py — carry a v5 or v6 enrich cache forward to v7.

_ENRICH_VERSION is one stamp per entry, not per category, so a merch-only change
invalidates the whole fleet's cache. Both bumps since v5 were merch-only:

  6  form-factor subtypes, pack/size in variant, colour or flavour in strain
  7  merch variant as a composite of size and pack, width normalised

so a NON-merch answer stamped 5 or 6 is still exactly what 7 would produce. This
restamps those.

Merch entries are DROPPED rather than re-enriched, which is the difference from
the v6 migration. Merch now has an owner that declares needs_model = False
(scripts/enrichers.py), so those rows are answered from the name before a batch is
formed and never consult the cache at all. Their entries are dead weight.

Measured on the 2026-08-30 fleet cache: 21,315 entries, 19,432 at v5 and 1,883 at
v6, and NOT ONE at v7 — so a sweep today re-enriches everything for about $11
regardless of which model flag is passed. That is the problem this fixes; the
model namespace (<slug>.json vs <slug>.<model>.json) is a separate trap and does
not help while the version check rejects every entry anyway.

Like its v6 predecessor, this is sound only for the bumps it names. A later bump
that touches a non-merch category needs its own reasoning — do not generalise
this into a "restamp the cache" tool.

    python scripts/migrate_enrich_cache_v7.py            # report, change nothing
    python scripts/migrate_enrich_cache_v7.py --run
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "enrich_cache"
FROM_V = (5, 6)
TO_V = 7


def main() -> None:
    ap = argparse.ArgumentParser(description="Restamp non-merch v5/v6 cache entries to v7")
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
            if (entry.get("category") or "").lower() == "merch":
                dropped += 1              # never read again — merch skips the cache
                continue
            if version == TO_V:
                kept[key] = entry
                continue
            if version not in FROM_V:     # unstamped or from a bump we cannot reason about
                other_v += 1
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
          f"{totals['restamped']:,} entries restamped to v{TO_V}, "
          f"{totals['dropped']:,} merch entries dropped (answered from the name now)")
    if totals["other_version"]:
        print(f"  {totals['other_version']:,} entries at another version were left to re-enrich")
    if not args.run:
        print("\nPass --run to apply.")


if __name__ == "__main__":
    main()
