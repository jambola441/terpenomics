"""
category_health.py — Detect per-dispensary category distribution outliers.

For each (brand, dispensary) pair with enough listings, computes the
Jensen-Shannon divergence between that pair's category mix and the brand's
aggregate distribution across all other dispensaries carrying it.

JSD = 0   → identical distribution (no anomaly)
JSD = 1   → maximally different (strong signal)

Usage:
    python scripts/category_health.py
    python scripts/category_health.py --min-listings 3 --top 30 --brand "Find."
"""

import argparse
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


# ---------------------------------------------------------------------------
# Math
# ---------------------------------------------------------------------------

def _kl(p: list[float], q: list[float]) -> float:
    return sum(pi * math.log(pi / qi) for pi, qi in zip(p, q) if pi > 0)


def jsd(p: dict[str, int], q: dict[str, int]) -> float:
    """Jensen-Shannon divergence between two category count dicts. Bounded [0, 1]."""
    keys = sorted(set(p) | set(q))
    eps = 1e-9
    pv = [p.get(k, 0) + eps for k in keys]
    qv = [q.get(k, 0) + eps for k in keys]
    ps = sum(pv); pv = [x / ps for x in pv]
    qs = sum(qv); qv = [x / qs for x in qv]
    mv = [(pv[i] + qv[i]) / 2 for i in range(len(keys))]
    return (_kl(pv, mv) + _kl(qv, mv)) / 2


def dist_str(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    parts = sorted(counts.items(), key=lambda x: -x[1])
    return "  ".join(f"{cat}={n}/{total}({n/total:.0%})" for cat, n in parts)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(min_brand_dispensaries: int = 2):
    """
    Returns:
        brand_disp:  {brand: {disp_slug: {category: count}}}
        disp_totals: {disp_slug: {category: count}}   (all brands, for per-disp report)
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                COALESCE(l.scraped_brand, '__no_brand__') AS brand,
                d.slug                                    AS dispensary,
                COALESCE(l.scraped_category, 'other')    AS category,
                count(*)                                  AS n
            FROM listings l
            JOIN dispensaries d ON d.id = l.dispensary_id
            GROUP BY 1, 2, 3
        """)).mappings().all()

    brand_disp: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    disp_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r in rows:
        brand_disp[r["brand"]][r["dispensary"]][r["category"]] += r["n"]
        disp_totals[r["dispensary"]][r["category"]] += r["n"]

    # Filter: only brands carried by >= min_brand_dispensaries dispensaries
    brand_disp = {
        b: d for b, d in brand_disp.items()
        if len(d) >= min_brand_dispensaries
    }
    return brand_disp, disp_totals


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def brand_dispensary_report(brand_disp, min_listings: int, top_n: int, brand_filter: str | None):
    """
    For each (brand, dispensary) pair, compute JSD vs. the brand's leave-one-out
    aggregate across all other dispensaries.
    """
    results = []

    for brand, by_disp in brand_disp.items():
        if brand_filter and brand.lower() != brand_filter.lower():
            continue

        # Aggregate across ALL dispensaries for this brand
        agg_all: dict[str, int] = defaultdict(int)
        for counts in by_disp.values():
            for cat, n in counts.items():
                agg_all[cat] += n

        for disp, counts in by_disp.items():
            total = sum(counts.values())
            if total < min_listings:
                continue

            # Leave-one-out aggregate: subtract this dispensary's counts
            agg_loo: dict[str, int] = {
                cat: agg_all[cat] - counts.get(cat, 0)
                for cat in agg_all
            }
            if sum(agg_loo.values()) == 0:
                continue  # only one dispensary carries this brand

            score = jsd(counts, agg_loo)
            results.append((score, brand, disp, counts, dict(agg_loo), total))

    results.sort(reverse=True)

    print(f"\n{'='*80}")
    print(f"BRAND × DISPENSARY OUTLIERS  (JSD vs leave-one-out brand aggregate)")
    print(f"min_listings={min_listings}  showing top {top_n}")
    print(f"{'='*80}")
    print(f"{'JSD':>6}  {'Brand':<30}  {'Dispensary':<32}  N")
    print(f"{'-'*6}  {'-'*30}  {'-'*32}  {'-'*5}")

    for score, brand, disp, counts, agg, total in results[:top_n]:
        print(f"{score:6.3f}  {brand:<30}  {disp:<32}  {total}")
        print(f"         this:  {dist_str(counts)}")
        print(f"         agg:   {dist_str(agg)}")

    return results


def listing_consensus_report(min_dispensaries: int = 2, min_group: int = 3, top_n: int = 40):
    """
    For each (brand, scraped_name) group carried at 2+ dispensaries, find listings
    whose subtype disagrees with the group majority.

    Signals Haiku drift (same product, different subtype assigned at one store) or
    a genuine scraping/mapping error. Strain is intentionally excluded — too much
    expected variation across scrapers in how much strain detail they extract.

    SKUs are dispensary-local so cannot be used for cross-store grouping.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                COALESCE(l.scraped_brand, '__no_brand__') AS brand,
                l.scraped_name,
                COALESCE(l.subtype,  'none')           AS subtype,
                COALESCE(l.scraped_category, 'other')  AS category,
                d.slug                                  AS dispensary
            FROM listings l
            JOIN dispensaries d ON d.id = l.dispensary_id
            WHERE l.scraped_name IS NOT NULL
        """)).mappings().all()

    # Group by (brand, scraped_name)
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r["brand"], r["scraped_name"])].append(dict(r))

    results = []

    for (brand, name), listings in groups.items():
        disps = {r["dispensary"] for r in listings}
        if len(disps) < min_dispensaries or len(listings) < min_group:
            continue

        # Majority subtype across all dispensaries carrying this (brand, name)
        subtype_counts: dict[str, int] = defaultdict(int)
        for r in listings:
            subtype_counts[r["subtype"]] += 1
        maj_subtype = max(subtype_counts, key=subtype_counts.__getitem__)
        maj_count   = subtype_counts[maj_subtype]

        # Only interesting if there's disagreement
        if len(subtype_counts) == 1:
            continue

        for r in listings:
            if r["subtype"] == maj_subtype:
                continue
            minority_count = subtype_counts[r["subtype"]]
            minority_frac  = minority_count / len(listings)
            results.append((
                minority_frac,
                brand, name, r["dispensary"],
                r["subtype"], maj_subtype, maj_count, len(listings),
            ))

    results.sort()  # ascending: smallest minority fraction = strongest outlier

    print(f"\n{'='*80}")
    print(f"LISTING-LEVEL SUBTYPE OUTLIERS  "
          f"(minority subtype within (brand, name) group across dispensaries)")
    print(f"min_dispensaries={min_dispensaries}  min_group={min_group}  showing top {top_n}")
    print(f"{'='*80}")

    seen: set[tuple] = set()
    shown = 0
    for minority_frac, brand, name, disp, subtype, maj_subtype, maj_count, group_size in results:
        if shown >= top_n:
            break
        key = (brand, name, subtype, maj_subtype)
        if key in seen:
            continue
        seen.add(key)
        print(f"  [{minority_frac:.0%} minority of {group_size}]  {brand}")
        print(f"    name:      {name}")
        print(f"    at {disp}: subtype={subtype!r}")
        print(f"    majority ({maj_count}/{group_size}): subtype={maj_subtype!r}")
        shown += 1


def dispensary_other_report(disp_totals, min_listings: int = 50):
    """
    Per-dispensary: what fraction of all listings are in 'other',
    ranked against the fleet average.
    """
    fleet_total = sum(sum(c.values()) for c in disp_totals.values())
    fleet_other = sum(c.get("other", 0) for c in disp_totals.values())
    fleet_rate  = fleet_other / fleet_total if fleet_total else 0

    rows = []
    for disp, counts in disp_totals.items():
        total = sum(counts.values())
        if total < min_listings:
            continue
        other = counts.get("other", 0)
        rate  = other / total
        rows.append((rate, disp, other, total))

    rows.sort(reverse=True)

    print(f"\n{'='*80}")
    print(f"PER-DISPENSARY 'OTHER' RATE  (fleet avg = {fleet_rate:.1%})")
    print(f"{'='*80}")
    print(f"{'other%':>7}  {'other':>6}  {'total':>6}  dispensary")
    print(f"{'-'*7}  {'-'*6}  {'-'*6}  {'-'*32}")
    for rate, disp, other, total in rows:
        flag = "  <<<" if rate > fleet_rate * 3 and other > 10 else ""
        print(f"{rate:7.1%}  {other:6d}  {total:6d}  {disp}{flag}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Category distribution health check")
    p.add_argument("--min-listings", type=int, default=5,
                   help="Min listings for a (brand, dispensary) pair to be scored (default: 5)")
    p.add_argument("--top", type=int, default=25,
                   help="Show top N outlier pairs (default: 25)")
    p.add_argument("--brand", default=None,
                   help="Filter to a single brand")
    p.add_argument("--no-disp-report", action="store_true",
                   help="Skip the per-dispensary other-rate table")
    p.add_argument("--no-consensus", action="store_true",
                   help="Skip the listing-level consensus outlier report")
    p.add_argument("--consensus-only", action="store_true",
                   help="Show only the listing-level consensus report")
    return p.parse_args()


def main():
    args = parse_args()
    print("Loading data...")
    brand_disp, disp_totals = load_data()
    if not args.consensus_only:
        brand_dispensary_report(brand_disp, args.min_listings, args.top, args.brand)
        if not args.no_disp_report:
            dispensary_other_report(disp_totals)
    if not args.no_consensus:
        listing_consensus_report(top_n=args.top)


if __name__ == "__main__":
    main()
