"""Catalog edits the daily audit makes (/audit-terpee-listings), as commands: the
conventions worked out by hand, written down once.

  python3 scripts/catalog_fix.py drop-term ENTRY "store name"      # recorded on the wrong product
  python3 scripts/catalog_fix.py add-term ENTRY "store name"       # a store's name for this product
  python3 scripts/catalog_fix.py add-size ENTRY 2.5g               # a size the product comes in
  python3 scripts/catalog_fix.py set-size ENTRY "10pk 100mg"       # the entry's own size is wrong
  python3 scripts/catalog_fix.py deactivate ENTRY [--into ENTRY]   # a duplicate; its names move over
  python3 scripts/catalog_fix.py size-sync                         # product-page sizes left behind

ENTRY is a brand_catalog_entries id (catalog_shape.py entries prints them). Every edit
prints what it would write and writes nothing without --write. --measure first runs
the matcher (Jev on, twice per side, no cache) over the brand's active listings with
the edit applied in memory, and prints what moves: an edit is judged on today's data,
and changes that differ between two runs of one side are Jev's noise, not the edit.
"""
from __future__ import annotations

import argparse
import copy
import sys
import urllib.parse
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_match as cm  # noqa: E402
import catalog_store  # noqa: E402
import sizes  # noqa: E402
from brand_catalog import norm_name, strip_brand  # noqa: E402

BOOTSTRAP = "listings_bootstrap"
TABLE = "brand_catalog_entries"


class Refused(Exception):
    """The edit would do harm or nothing; the message says why."""


@dataclass
class Plan:
    catalog: dict                     # as loaded
    changed: dict                     # a copy with the edit applied, for --measure
    category: str | None = None       # the edited product's; only its listings can move
    writes: list[tuple] = field(default_factory=list)     # (op, table, query, row)
    notes: list[str] = field(default_factory=list)


def find(catalogs: dict, entry_id: str) -> tuple[dict, dict]:
    hit = catalog_store.entries_by_id(catalogs).get(str(entry_id))
    if not hit:
        raise Refused(f"no catalog entry {entry_id}")
    return hit


def _copy_with(catalog: dict, entry_id: str, **changes) -> dict:
    out = copy.deepcopy(catalog)
    for e in out["entries"]:
        if str(e["id"]) == str(entry_id):
            e.update(changes)
    return out


def _product_entries(catalog: dict, entry: dict) -> list[dict]:
    key = entry.get("product_key") or catalog_store._product_key(entry)
    return [e for e in catalog["entries"] if e.get("is_active", True)
            and (e.get("product_key") or catalog_store._product_key(e)) == key]


def _label(size: str, category: str | None) -> sizes.Size:
    s = sizes.parse(size, category=category)
    if s.is_empty() or not s.label():
        raise Refused(f'"{size}" is not a size sizes.parse can read')
    return s


def _variant(s: sizes.Size, category: str | None) -> str:
    """The form entries keep: the package total for what is sold by weight ("2.5g"; the
    subtype says pack, as catalog_bootstrap writes it), the pack and total for doses
    ("10pk 100mg": the count tells the per-piece dose)."""
    return _total(s) if category in sizes.WEIGHT_CATEGORIES else s.label()


def _total(s: sizes.Size) -> str:
    return f"{s.grams:g}g" if s.grams is not None else f"{s.mg:g}mg"


def _desc(e: dict) -> str:
    return f'{e.get("name")} · {e.get("variant") or "?"} ({e["id"]})'


# ---------------------------------------------------------------------------
# Plans: what an edit would write, decided without writing
# ---------------------------------------------------------------------------

def plan_drop_term(catalogs: dict, entry_id: str, term: str, force: bool = False) -> Plan:
    catalog, entry = find(catalogs, entry_id)
    want = norm_name(term)
    terms = entry.get("match_terms") or []
    keep = [t for t in terms if norm_name(t) != want]
    if len(keep) == len(terms):
        raise Refused(f'"{term}" is not among {_desc(entry)}\'s store names')
    owners = [e for e in catalog["entries"] if e.get("is_active", True) and str(e["id"]) != str(entry_id)
              and any(norm_name(t) == want for t in e.get("match_terms") or [])]
    if not owners and not force:
        raise Refused(f'no other entry holds "{term}": its listings would lose their exact match and go '
                      "to Jev. Check that is wanted, then pass --force")
    plan = Plan(catalog, _copy_with(catalog, entry_id, match_terms=keep), entry.get("category"))
    plan.writes.append(("update", TABLE, f"id=eq.{entry['id']}", {"match_terms": keep}))
    plan.notes.append(f'drop "{term}" from {_desc(entry)}'
                      + (f"; it stays on {', '.join(_desc(e) for e in owners)}" if owners else ""))
    return plan


def plan_add_term(catalogs: dict, entry_id: str, name: str, force: bool = False) -> Plan:
    """Store names are recorded brand-less and normalised, as catalog_bootstrap records
    them, so a store that writes the brand in still matches."""
    catalog, entry = find(catalogs, entry_id)
    term = strip_brand(name, catalog.get("brand_name") or "")
    if not term:
        raise Refused(f'"{name}" is empty once normalised')
    if term in (entry.get("match_terms") or []):
        raise Refused(f'{_desc(entry)} already holds "{term}"')
    index = cm.CatalogIndex(catalog)
    key = entry.get("product_key") or catalog_store._product_key(entry)
    others = [k for k in index.by_term.get(term, []) if k != key
              and index.products[k].category == entry.get("category")]
    if others and index.unrelated(list(dict.fromkeys(others + [key]))) and not force:
        raise Refused(f'"{term}" is already a store name for '
                      f'{", ".join(index.products[k].title for k in dict.fromkeys(others))}: recording it here '
                      "too is how a name gets cross-wired. Pass --force if that product holds it by mistake "
                      "(and drop-term it there)")
    terms = sorted(set(entry.get("match_terms") or []) | {term})
    plan = Plan(catalog, _copy_with(catalog, entry_id, match_terms=terms), entry.get("category"))
    plan.writes.append(("update", TABLE, f"id=eq.{entry['id']}", {"match_terms": terms}))
    plan.notes.append(f'record "{term}" as a store name of {_desc(entry)}')
    return plan


def plan_add_size(catalogs: dict, entry_id: str, size: str, force: bool = False) -> Plan:
    """A new entry for a size the product comes in: the product's fields, its product_key
    (one product, two sizes), and an external id a later push will not fight. In a
    bootstrap catalog that is the bootstrap's own scheme (product key + package total),
    so a rebuild that proposes the size updates this entry instead of adding a second.
    In a storefront catalog it is none: a re-fetch deactivates every entry whose id the
    site does not list, and NULL is never in that list (see routes/admin EntryCreate)."""
    catalog, entry = find(catalogs, entry_id)
    s = _label(size, entry.get("category"))
    siblings = _product_entries(catalog, entry)
    has = [e for e in siblings if sizes.same_size(s, sizes.parse(e.get("variant"), category=entry.get("category")))]
    if has and not force:
        raise Refused(f"the product already comes in {_variant(s, entry.get('category'))}: "
                      f"{', '.join(_desc(e) for e in has)}")
    key = entry.get("product_key") or catalog_store._product_key(entry)
    external_id = f"{key}:{_total(s)}" if catalog.get("source_method") == BOOTSTRAP else None
    if external_id and any(e.get("external_id") == external_id for e in catalog["entries"]):
        raise Refused(f"external id {external_id} is taken (an inactive entry?); reactivate that one instead")
    row = {"catalog_id": entry["catalog_id"], "external_id": external_id, "product_key": key,
           "name": entry["name"], "product_line": entry.get("product_line"),
           "category": entry.get("category"), "subtype": entry.get("subtype"),
           "strain": entry.get("strain"), "variant": _variant(s, entry.get("category")),
           "attributes": entry.get("attributes"),
           "match_terms": [], "source": entry.get("source")}
    changed = copy.deepcopy(catalog)
    changed["entries"].append({**row, "id": f"new-{uuid.uuid4()}", "is_active": True})
    plan = Plan(catalog, changed, entry.get("category"))
    plan.writes.append(("insert", TABLE, None, row))
    plan.notes.append(f"add {row['variant']} to {entry['name']} (beside {', '.join(e.get('variant') or '?' for e in siblings)})"
                      f"; external_id {external_id or 'none (storefront catalog)'}")
    return plan


def plan_set_size(catalogs: dict, entry_id: str, size: str, force: bool = False) -> Plan:
    catalog, entry = find(catalogs, entry_id)
    s = _label(size, entry.get("category"))
    variant = _variant(s, entry.get("category"))
    if variant == entry.get("variant"):
        raise Refused(f"{_desc(entry)} already says {variant}")
    twins = [e for e in _product_entries(catalog, entry) if str(e["id"]) != str(entry_id)
             and sizes.same_size(s, sizes.parse(e.get("variant"), category=entry.get("category")))]
    if twins and not force:
        raise Refused(f"another entry of the product is already {variant}: "
                      f"{', '.join(_desc(e) for e in twins)}; deactivate one of the two instead")
    plan = Plan(catalog, _copy_with(catalog, entry_id, variant=variant), entry.get("category"))
    plan.writes.append(("update", TABLE, f"id=eq.{entry['id']}", {"variant": variant}))
    plan.notes.append(f"{_desc(entry)}: size {entry.get('variant')} -> {variant}")
    return plan


def plan_deactivate(catalogs: dict, entry_id: str, into: str | None = None) -> Plan:
    """Never a delete: listings point at entries. The duplicate's store names move to
    the survivor, so its listings keep matching exactly."""
    catalog, entry = find(catalogs, entry_id)
    if not entry.get("is_active", True):
        raise Refused(f"{_desc(entry)} is already inactive")
    changed = _copy_with(catalog, entry_id, is_active=False)
    plan = Plan(catalog, changed, entry.get("category"))
    plan.writes.append(("update", TABLE, f"id=eq.{entry['id']}", {"is_active": False}))
    plan.notes.append(f"deactivate {_desc(entry)}")
    if into:
        survivor_catalog, survivor = find(catalogs, into)
        if survivor_catalog is not catalog:
            raise Refused("the survivor is in another brand's catalog")
        terms = sorted(set(survivor.get("match_terms") or []) | set(entry.get("match_terms") or []))
        for e in changed["entries"]:
            if str(e["id"]) == str(into):
                e["match_terms"] = terms
        plan.writes.append(("update", TABLE, f"id=eq.{survivor['id']}", {"match_terms": terms}))
        plan.notes.append(f"move its {len(entry.get('match_terms') or [])} store name(s) to {_desc(survivor)}")
    return plan


def plan_size_sync(catalogs: dict, listings: list[dict]) -> list[tuple[dict, str]]:
    """(listing, size) for listings whose product-page size is not what the importer
    would write now (import_listings.assign_sizes)."""
    import import_listings
    recs = [dict(l) for l in listings if l.get("catalog_entry_id")]
    stored = {r["id"]: r.get("size") for r in recs}
    import_listings.assign_sizes(recs, catalogs)
    return [(r, r["size"]) for r in recs
            if r["size"] != (stored[r["id"]] if stored[r["id"]] is not None else r["variant"])]


# ---------------------------------------------------------------------------
# Measuring: the matcher before and after, on the brand's listings
# ---------------------------------------------------------------------------

def brand_listings(brand: str, category: str | None = None) -> list[dict]:
    """The brand's active listings; only one category's when given, since the matcher
    shortlists products of a listing's own category and nothing else can move."""
    import db_http
    rows = db_http.select_all(
        "listings", "select=id,dispensary_id,scraped_name,scraped_category,subtype,variant,description"
                    f"&is_active=is.true&scraped_brand=ilike.{urllib.parse.quote(brand)}"
                    + (f"&scraped_category=eq.{urllib.parse.quote(category)}" if category else ""))
    return [{"id": r["id"], "name": r.get("scraped_name") or "", "category": r.get("scraped_category"),
             "subtype": r.get("subtype"), "variant": r.get("variant"), "description": r.get("description")}
            for r in rows]


def outcome(catalog: dict, listing: dict, d) -> tuple:
    """What a decision means for the listing: (trust, product, entry, page size)."""
    trust = "trusted" if d.method in cm.OVERLAY_METHODS else d.method if d.method == "jev_review" else "none"
    page = listing.get("variant")
    if trust == "trusted" and d.entry is not None:
        product = _product_entries(catalog, d.entry) or [d.entry]
        page = cm.catalog_size(listing.get("variant"), listing.get("name"), d.entry, product,
                               listing.get("description")) or page
    return trust, d.product_key, (d.entry or {}).get("id"), page


def compare(old_runs: list[dict], new_runs: list[dict]) -> tuple[dict, int]:
    """({listing id: (before, after)} for changes both runs of each side agree on,
    noise): noise counts listings whose runs of one side disagree."""
    stable, noise = {}, 0
    for i in old_runs[0]:
        olds = {r.get(i) for r in old_runs}
        news = {r.get(i) for r in new_runs}
        if len(olds) > 1 or len(news) > 1:
            noise += 1
            continue
        before, after = olds.pop(), news.pop()
        if before != after:
            stable[i] = (before, after)
    return stable, noise


def summarize(stable: dict) -> Counter:
    c = Counter()
    for before, after in stable.values():
        if before[0] != after[0]:
            if after[0] == "trusted":
                c["trusted gained"] += 1
            if before[0] == "trusted":
                c["trusted lost"] += 1
        if before[0] == after[0] == "trusted":
            if before[1] != after[1]:
                c["trusted moved to another product"] += 1
            elif before[2] != after[2]:
                c["trusted moved to another size"] += 1
        if before[3] != after[3]:
            c["page size changed"] += 1
    return c


def measure(plan: Plan, runs: int = 2) -> None:
    import jev
    brand = plan.catalog.get("brand_name") or ""
    listings = brand_listings(brand, plan.category)
    use_jev = jev.available()
    if not use_jev:
        print("  (Jev is not available here: measuring the exact tier only)")
    by_id = {l["id"]: l for l in listings}

    def run(catalog):
        return {d.listing["id"]: outcome(catalog, d.listing, d)
                for d in cm.resolve(catalog, listings, use_jev=use_jev)}
    old = [run(plan.catalog) for _ in range(runs)]
    new = [run(plan.changed) for _ in range(runs)]
    stable, noise = compare(old, new)
    tally = summarize(stable)
    print(f"measure: {len(listings)} active {brand} {plan.category or ''} listings, {runs} runs per side"
          f"{' (Jev on, no cache)' if use_jev else ''}")
    print("  " + (", ".join(f"{k} {v}" for k, v in tally.items()) or "no listing changes")
          + f"; {noise} listing(s) differed between runs of one side (Jev's noise, not counted)")
    for i, (before, after) in list(stable.items())[:20]:
        print(f'  - "{by_id[i]["name"][:60]}" [{by_id[i].get("variant")}]: '
              f"{before[0]} {before[3]} -> {after[0]} {after[3]}"
              + (" (other product)" if before[1] != after[1] else " (other size)" if before[2] != after[2] else ""))
    if len(stable) > 20:
        print(f"  ... and {len(stable) - 20} more")


def apply(plan: Plan) -> None:
    import db_http
    for op, table, query, row in plan.writes:
        if op == "insert":
            print("  inserted", db_http.insert(table, row)[0]["id"])
        else:
            db_http.update(table, query, row)
            print(f"  updated {query}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    for name, extra in (("drop-term", "term"), ("add-term", "name"), ("add-size", "size"),
                        ("set-size", "size"), ("deactivate", None)):
        p = sub.add_parser(name)
        p.add_argument("entry")
        if extra:
            p.add_argument(extra)
        if name == "deactivate":
            p.add_argument("--into", help="the surviving entry, which takes the duplicate's store names")
        else:
            p.add_argument("--force", action="store_true", help="do it despite the refusal's reason")
        p.add_argument("--measure", action="store_true", help="run the matcher before and after first")
        p.add_argument("--write", action="store_true", help="write the edit (after the user approved it)")
    ss = sub.add_parser("size-sync")
    ss.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    catalogs = catalog_store.load_all("db")
    if args.command == "size-sync":
        import db_http
        rows = db_http.select_all("listings", "select=id,variant,size,scraped_name,catalog_entry_id,"
                                  "catalog_match_method,description&is_active=is.true&catalog_entry_id=not.is.null")
        todo = plan_size_sync(catalogs, rows)
        for r, size in todo:
            print(f'  "{(r.get("scraped_name") or "")[:60]}": {r.get("size") or r["variant"]} -> {size}')
            if args.write:
                db_http.update("listings", f"id=eq.{r['id']}", {"size": size})
        print(f"{len(todo)} listing(s)" + (" written" if args.write else " (dry run; --write writes)"))
        return 0
    try:
        if args.command == "drop-term":
            plan = plan_drop_term(catalogs, args.entry, args.term, args.force)
        elif args.command == "add-term":
            plan = plan_add_term(catalogs, args.entry, args.name, args.force)
        elif args.command == "add-size":
            plan = plan_add_size(catalogs, args.entry, args.size, args.force)
        elif args.command == "set-size":
            plan = plan_set_size(catalogs, args.entry, args.size, args.force)
        else:
            plan = plan_deactivate(catalogs, args.entry, args.into)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    for note in plan.notes:
        print(note)
    if args.measure:
        measure(plan)
    if args.write:
        apply(plan)
    else:
        print("(dry run; --write writes it)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
