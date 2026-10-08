#!/usr/bin/env python3
"""
line_fill.py — Each product of a named line in the sizes its line comes in.

A brand's sizes belong to a line, not to a strain: STIIIZY's Original pods come in
0.5g and 1g, Fernway's Traveler PRO in 0.5, 1 and 2g. A catalog read off a brand's
site or built from store menus often has a strain in fewer of its line's sizes than
the line comes in — the site showed one size, or two stores carried only one — and a
listing of the missing size then matches its product with a size the product lacks.

This adds the missing ones as entries of their own, marked source "inferred": for
each product of a named line (the brand, category, subtype and line; never across
brands), every size another product of that line comes in. On the labelled match set
(evals/match, 2026-10-08) this gave 7 more right matches, none on a wrong product.
Lines with no name are left alone: a catalog's line-less products are often several
real lines it never named, and filling them gave line-less products sizes that won
listings belonging to a named product.

Inferred entries never decide which product a listing is (catalog_match leaves them
out of a product's sizes and of what Jev is shown); they only give the chosen product
the listing's size. They are derived: a sync recomputes them from the stated entries,
adds what is missing, takes back what no longer follows (the line stopped carrying
the size, or the product now states it) and brings back one a push retired.

Usage
-----
  python scripts/line_fill.py --brand "STIIIZY"            # what a sync would change
  python scripts/line_fill.py --all --write                # every catalog, written
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_store  # noqa: E402
import sizes  # noqa: E402
from brand_catalog import norm_name  # noqa: E402

INFERRED = "inferred"
TABLE = "brand_catalog_entries"


def _size(variant: str | None, category: str | None) -> tuple[str | None, sizes.Size | None]:
    """An entry's size in the form entries keep ("2.5g", "10pk 100mg"), and parsed."""
    s = sizes.parse(variant, category=category)
    if s.is_empty() or not s.label():
        return None, None
    if category in sizes.WEIGHT_CATEGORIES:
        return (f"{s.grams:g}g" if s.grams is not None else s.label()), s
    return s.label(), s


def wanted(catalog: dict) -> dict[str, dict]:
    """The inferred entries the catalog's stated entries call for, by external id."""
    products: dict[str, list[dict]] = defaultdict(list)
    for e in catalog.get("entries") or []:
        if e.get("is_active", True) and e.get("source") != INFERRED:
            products[e.get("product_key") or catalog_store._product_key(e)].append(e)
    lines: dict[tuple, list[str]] = defaultdict(list)
    for key, es in products.items():
        line = (es[0].get("product_line") or "").strip()
        if line:
            lines[(es[0].get("category"), es[0].get("subtype") or "", norm_name(line))].append(key)
    out: dict[str, dict] = {}
    for (category, _, _), keys in lines.items():
        if len(keys) < 2:
            continue
        own = {k: dict(filter(lambda kv: kv[0], (_size(e.get("variant"), category) for e in products[k])))
               for k in keys}
        carriers: dict[str, list[str]] = defaultdict(list)
        for k in keys:
            for label in own[k]:
                carriers[label].append(products[k][0].get("name") or "")
        sized = {label: s for k in keys for label, s in own[k].items()}
        for k in keys:
            for label, s in sized.items():
                if label in own[k] or any(sizes.same_size(s, o) is True for o in own[k].values()):
                    continue
                base = products[k][0]
                external_id = f"{INFERRED}:{k}:{label}"
                out[external_id] = {
                    "catalog_id": catalog.get("id"), "external_id": external_id, "product_key": k,
                    "name": base.get("name"), "product_line": base.get("product_line"),
                    "category": category, "subtype": base.get("subtype"), "strain": base.get("strain"),
                    "variant": label, "match_terms": [], "source": INFERRED,
                    "attributes": {"inferred_from": sorted(carriers[label])[:5]},
                }
    return out


def plan(catalog: dict) -> tuple[list[dict], list[str], list[str]]:
    """(rows to insert, ids to bring back, ids to take back) for one catalog whose
    entries include the inactive ones."""
    want = wanted(catalog)
    have = {e["external_id"]: e for e in catalog.get("entries") or []
            if e.get("source") == INFERRED and e.get("external_id")}
    inserts = [row for xid, row in want.items() if xid not in have]
    revive = [have[xid]["id"] for xid in want if xid in have and not have[xid].get("is_active", True)]
    retire = [e["id"] for xid, e in have.items() if xid not in want and e.get("is_active", True)]
    return inserts, revive, retire


def load(brand: str | None) -> list[dict]:
    """The catalogs to sync, with their inactive entries (a push retires inferred
    entries; the sync brings them back by external id)."""
    import catalog_fix
    catalogs = catalog_fix.with_inactive(catalog_store.load_all("db"))
    if brand:
        return [catalog_fix.catalog_of(catalogs, brand)]
    return list(catalogs.values())


def sync(catalog: dict, write: bool = False) -> tuple[int, int, int]:
    inserts, revive, retire = plan(catalog)
    if write and (inserts or revive or retire):
        import db_http
        for i in range(0, len(inserts), 200):
            db_http.insert(TABLE, inserts[i:i + 200])
        for ids, active in ((revive, True), (retire, False)):
            for i in range(0, len(ids), 100):
                db_http.update(TABLE, f"id=in.({','.join(ids[i:i + 100])})", {"is_active": active})
    return len(inserts), len(revive), len(retire)


def sync_brand(brand: str) -> None:
    """For a command that just wrote a brand's catalog (a push, a curation plan).

    Only a catalog line fill was turned on for (it holds inferred entries, active or
    retired, from a `--write` run) is synced: a push never starts filling a brand.
    """
    import catalog_fix
    try:
        [catalog] = load(brand)
    except catalog_fix.Refused:
        return
    if not any(e.get("source") == INFERRED for e in catalog.get("entries") or []):
        return
    added, revived, retired = sync(catalog, write=True)
    print(f"  line fill: {added} inferred sizes added, {revived} brought back, {retired} taken back")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--brand")
    which.add_argument("--all", action="store_true")
    ap.add_argument("--write", action="store_true", help="write the changes (else print them)")
    args = ap.parse_args(argv)
    totals = [0, 0, 0]
    for catalog in sorted(load(args.brand), key=lambda c: c.get("brand_name") or ""):
        counts = sync(catalog, write=args.write)
        if any(counts):
            print(f"{catalog.get('brand_name')}: +{counts[0]} inferred, {counts[1]} back, {counts[2]} taken back")
        totals = [a + b for a, b in zip(totals, counts)]
    print(f"total: +{totals[0]} inferred, {totals[1]} back, {totals[2]} taken back"
          + ("" if args.write else " (dry run; --write writes it)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
