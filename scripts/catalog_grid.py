#!/usr/bin/env python3
"""
catalog_grid.py — Every brand catalog is a full grid.

The owner's rule (2026-10-12), for every brand, with no exceptions:

    Within a brand's catalog, for each group (category, subtype, product line — a
    product with no line is in the brand's line-less group of that category and
    subtype), the active entries are exactly every strain in the group x every size
    that appears anywhere in the group. Every strain has every size, whether or not
    it was ever sold, so a listing never fails to match only because a size is missing.

A "strain" is a product (product_key) with at least one active entry that is not
inferred. A group's sizes are the sizes of its active non-inferred entries. A cell a
product does not state is filled with an entry of its own, source "inferred"
(external id "inferred:<product_key>:<size>").

`plan` is the whole sync, and it is idempotent:
  insert      a missing cell
  revive      a previously inferred cell that is wanted again (a push retired it, or
              the size came back)
  retire      an inferred cell no longer wanted: no non-inferred entry in the group has
              that size any more, the strain has no non-inferred entry any more, or the
              product now states that size itself (the stated entry fills the cell)
  patch       an inferred cell whose copied fields (name, line, category, subtype,
              strain) no longer follow its product (a re-line moved it)
Entries that are not inferred are never touched.

Every catalog write ends with the sync: brand_catalog.push over its own DB path (sync_cursor
in the push transaction over DATABASE_URL, sync_rest when via HTTP) — so storefront.py
push and catalog_bootstrap --push —, catalog_fix.py --write), and the daily cron re-syncs
every catalog before the import (run_scrape_cron.py). data_health.py's grid-gap detector
counts groups that are not full grids; it should read 0.

Usage
-----
  python scripts/catalog_grid.py --brand "STIIIZY"            # what a sync would change
  python scripts/catalog_grid.py --all                        # every catalog, dry run
  python scripts/catalog_grid.py --all --write                # every catalog, written
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_store  # noqa: E402
import sizes  # noqa: E402
from brand_catalog import norm_name  # noqa: E402

INFERRED = "inferred"
TABLE = "brand_catalog_entries"
COPIED = ("name", "product_line", "category", "subtype", "strain")


def size_of(variant: str | None, category: str | None) -> tuple[str | None, sizes.Size | None]:
    """An entry's size in the form entries keep ("2.5g", "10pk 100mg"), and parsed."""
    s = sizes.parse(variant, category=category)
    if s.is_empty() or not s.label():
        return None, None
    pack = getattr(sizes, "pack_label", None)      # "2 × 0.5g" stays a pack, where sizes knows packs
    if pack and pack(variant):
        return pack(variant), s
    if category in sizes.WEIGHT_CATEGORIES:
        return (f"{s.grams:g}g" if s.grams is not None else s.label()), s
    return s.label(), s


def group_of(entry: dict) -> tuple[str, str, str]:
    """(category, subtype, line) — a blank line is the group's own line-less group."""
    return (entry.get("category") or "", entry.get("subtype") or "",
            norm_name((entry.get("product_line") or "").strip()))


def key_of(entry: dict) -> str:
    return entry.get("product_key") or catalog_store._product_key(entry)


def _same(a: str, sa: sizes.Size, b: str, sb: sizes.Size, category: str | None) -> bool:
    """Whether two sizes are one cell: sizes.same_variant where sizes has it (a pack is
    not its total weight), else sizes.same_size."""
    if a == b:
        return True
    same_variant = getattr(sizes, "same_variant", None)
    if same_variant:
        return bool(same_variant(a, b, category))
    return sizes.same_size(sa, sb) is True


def _has(own: dict[str, sizes.Size], label: str, s: sizes.Size, category: str | None) -> bool:
    return any(_same(label, s, o, so, category) for o, so in own.items())


def wanted(catalog: dict) -> dict[str, dict]:
    """The inferred entries the catalog's active non-inferred entries call for, by
    external id: every strain of each group in every size of the group it lacks."""
    groups: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for e in catalog.get("entries") or []:
        if e.get("is_active", True) and e.get("source") != INFERRED:
            groups[group_of(e)][key_of(e)].append(e)
    out: dict[str, dict] = {}
    for (category, _, _), products in groups.items():
        cat = category or None
        own = {k: dict(filter(lambda kv: kv[0], (size_of(e.get("variant"), cat) for e in es)))
               for k, es in products.items()}
        group_sizes: dict[str, sizes.Size] = {}
        carriers: dict[str, list[str]] = defaultdict(list)
        for k, es in products.items():
            for label, s in own[k].items():
                hit = next((g for g, gs in group_sizes.items() if _same(label, s, g, gs, cat)), None)
                if hit is None:
                    group_sizes[label] = s
                    hit = label
                carriers[hit].append(es[0].get("name") or "")
        for k, es in products.items():
            base = es[0]
            for label, s in group_sizes.items():
                if _has(own[k], label, s, cat):
                    continue
                external_id = f"{INFERRED}:{k}:{label}"
                if external_id in out:      # a product split across groups: one cell
                    continue
                out[external_id] = {
                    "catalog_id": catalog.get("id"), "external_id": external_id, "product_key": k,
                    "name": base.get("name"), "product_line": base.get("product_line"),
                    "category": base.get("category"), "subtype": base.get("subtype"),
                    "strain": base.get("strain"), "variant": label, "match_terms": [],
                    "source": INFERRED,
                    "attributes": {"inferred_from": sorted(set(carriers[label]))[:5]},
                }
    return out


@dataclass
class Plan:
    inserts: list[dict] = field(default_factory=list)
    revive: list[str] = field(default_factory=list)
    retire: list[str] = field(default_factory=list)
    patch: list[tuple[str, dict]] = field(default_factory=list)

    def counts(self) -> tuple[int, int, int, int]:
        return len(self.inserts), len(self.revive), len(self.retire), len(self.patch)

    def __bool__(self) -> bool:
        return any(self.counts())


def plan(catalog: dict) -> Plan:
    """What makes the catalog a full grid. Its entries should include the inactive
    ones, so a retired inferred cell is brought back by its external id rather than
    inserted again (which the unique key would refuse)."""
    want = wanted(catalog)
    have = {e["external_id"]: e for e in catalog.get("entries") or []
            if e.get("source") == INFERRED and e.get("external_id")}
    out = Plan()
    for xid, row in want.items():
        cur = have.get(xid)
        if cur is None:
            out.inserts.append(row)
            continue
        if not cur.get("is_active", True):
            out.revive.append(cur["id"])
        change = {c: row[c] for c in COPIED if (cur.get(c) or None) != (row[c] or None)}
        if change:
            out.patch.append((cur["id"], change))
    out.retire = [e["id"] for xid, e in have.items() if xid not in want and e.get("is_active", True)]
    return out


def gaps(catalog: dict) -> dict[tuple, tuple[int, int]]:
    """The groups of an active-only catalog that are not full grids:
    group -> (cells missing, inferred cells that should not be there)."""
    p = plan(catalog)
    by_id = {e.get("id"): e for e in catalog.get("entries") or []}
    out: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for row in p.inserts:
        out[group_of(row)][0] += 1
    for i in p.revive:                       # an inactive cell counts as missing
        out[group_of(by_id[i])][0] += 1
    for i in p.retire:
        out[group_of(by_id[i])][1] += 1
    return {g: tuple(v) for g, v in out.items()}


def apply(p: Plan) -> None:
    import db_http
    for i in range(0, len(p.inserts), 200):
        db_http.insert(TABLE, p.inserts[i:i + 200])
    for ids, active in ((p.revive, True), (p.retire, False)):
        for i in range(0, len(ids), 100):
            db_http.update(TABLE, f"id=in.({','.join(ids[i:i + 100])})", {"is_active": active})
    for i, change in p.patch:
        db_http.update(TABLE, f"id=eq.{i}", change)


def _one(catalog_id, entries: list[dict]) -> dict | None:
    """A catalog of these rows, or None before migration 0003 (no source/product_key:
    nothing can be marked inferred)."""
    if entries and not all(k in entries[0] for k in ("source", "product_key")):
        return None
    return {"id": str(catalog_id), "entries": [dict(e, id=str(e["id"]), catalog_id=str(e["catalog_id"]))
                                               for e in entries]}


def sync_rest(catalog_id: str) -> Plan:
    """The sync over Supabase's REST API, for a write that went over it (push via_http)."""
    import db_http
    catalog = _one(catalog_id, db_http.select_all(TABLE, f"select=*&catalog_id=eq.{catalog_id}&order=id"))
    if catalog is None:
        return Plan()
    return sync(catalog, write=True)


def sync_cursor(cur, catalog_id) -> Plan:
    """The sync inside an open psycopg2 transaction, for a write over a direct
    connection (push over DATABASE_URL); the caller commits."""
    import psycopg2.extras
    cur.execute(f"SELECT * FROM {TABLE} WHERE catalog_id = %s ORDER BY id", (catalog_id,))
    cols = [d[0] for d in cur.description]
    catalog = _one(catalog_id, [dict(zip(cols, r)) for r in cur.fetchall()])
    if catalog is None:
        return Plan()
    p = plan(catalog)
    if p.inserts:
        keys = list(p.inserts[0])
        psycopg2.extras.execute_values(
            cur, f"INSERT INTO {TABLE} ({', '.join(keys)}) VALUES %s",
            [tuple(psycopg2.extras.Json(r[k]) if isinstance(r[k], dict) else r[k] for k in keys)
             for r in p.inserts])
    for ids, active in ((p.revive, True), (p.retire, False)):
        if ids:
            cur.execute(f"UPDATE {TABLE} SET is_active = %s WHERE id::text = ANY(%s)", (active, ids))
    for i, change in p.patch:
        cur.execute(f"UPDATE {TABLE} SET {', '.join(f'{c} = %s' for c in change)} WHERE id::text = %s",
                    (*change.values(), i))
    return p


def load(brand: str | None) -> list[dict]:
    """The catalogs to sync, with their inactive entries."""
    import catalog_fix
    catalogs = catalog_fix.with_inactive(catalog_store.load_all("db"))
    if brand:
        return [catalog_fix.catalog_of(catalogs, brand)]
    return list(catalogs.values())


def sync(catalog: dict, write: bool = False) -> Plan:
    p = plan(catalog)
    if write and p:
        apply(p)
    return p


def _say(p: Plan) -> str:
    a, b, c, d = p.counts()
    return f"+{a} inferred, {b} brought back, {c} retired, {d} re-copied"


def sync_brand(brand: str) -> None:
    """Make one brand's catalog a full grid; the last step of every catalog write."""
    import catalog_fix
    try:
        [catalog] = load(brand)
    except catalog_fix.Refused:
        return
    print(f"  catalog grid: {_say(sync(catalog, write=True))}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--brand")
    which.add_argument("--all", action="store_true")
    ap.add_argument("--write", action="store_true", help="write the changes (else print them)")
    args = ap.parse_args(argv)
    totals = Plan()
    for catalog in sorted(load(args.brand), key=lambda c: c.get("brand_name") or ""):
        p = sync(catalog, write=args.write)
        if p:
            print(f"{catalog.get('brand_name')}: {_say(p)}")
        for f in ("inserts", "revive", "retire", "patch"):
            getattr(totals, f).extend(getattr(p, f))
    print(f"total: {_say(totals)}" + ("" if args.write else " (dry run; --write writes it)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
