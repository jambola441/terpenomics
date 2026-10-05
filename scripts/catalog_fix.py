"""Catalog edits the daily audit makes (/audit-terpee-listings), as commands: the
conventions worked out by hand, written down once.

  python3 scripts/catalog_fix.py drop-term ENTRY "store name"      # recorded on the wrong product
  python3 scripts/catalog_fix.py add-term ENTRY "store name"       # a store's name for this product
  python3 scripts/catalog_fix.py add-size ENTRY 2.5g               # a size the product comes in
  python3 scripts/catalog_fix.py set-size ENTRY "10pk 100mg"       # the entry's own size is wrong
  python3 scripts/catalog_fix.py deactivate ENTRY [--into ENTRY]   # a duplicate; its names move over
  python3 scripts/catalog_fix.py add-product "Find." --category flower --subtype flower \
      --strain "Out Of Office" --size 3.5g --term "Out Of Office - 3.5G Flower"   # a product it lacks
  python3 scripts/catalog_fix.py plan curation.json                # many edits, measured as one
  python3 scripts/catalog_fix.py size-sync                         # product-page sizes left behind

ENTRY is a brand_catalog_entries id (catalog_shape.py entries prints them). Every edit
prints what it would write and writes nothing without --write. --measure first runs
the matcher (Jev on, twice per side, no cache) over the brand's active listings with
the edit applied in memory, and prints what moves: an edit is judged on today's data,
and changes that differ between two runs of one side are Jev's noise, not the edit.

Entries made here are marked source "curated": a bootstrap rebuild with --replace
retires the bootstrap entries it no longer proposes, and a product added from one
store's listings by judgment is one it never proposes. In a bootstrap catalog they take
the bootstrap's id scheme, so a rebuild that does propose them updates them in place.

A plan file curates a catalog in one go (the catalog-audit skill, "Curating a
store-built catalog"): {"brand": ..., "edits": [{"op": ..., "why": ..., ...}]}, the ops
being the commands above with their arguments as keys ("entry", "into", "size",
"term", "name"; add-product: "category", "subtype", "line", "strain", "sizes", "terms").
An entry is its id or a selector, {"strain", "category", "subtype", "line", "size"},
that must name one active entry. Edits apply in order to one copy of the catalog, are
measured together, and are written together; one refusal stops the whole plan.
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
CURATED = "curated"
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
           "match_terms": [], "source": CURATED}
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


def catalog_of(catalogs: dict, brand: str) -> dict:
    want = norm_name(brand)
    hits = [c for c in catalogs.values() if norm_name(c.get("brand_name") or "") == want]
    if len(hits) != 1:
        raise Refused(f"no catalog for brand {brand!r}" if not hits else f"{len(hits)} catalogs for {brand!r}")
    return hits[0]


def product_key(catalog: dict, category: str, subtype: str | None, line: str | None, strain: str) -> str:
    """The key catalog_bootstrap gives a product, so a rebuild finds a curated product
    instead of proposing it again; "cur:" in a storefront catalog, whose push owns no
    such key."""
    import catalog_bootstrap
    prefix = "lb" if catalog.get("source_method") == BOOTSTRAP else "cur"
    return (f"{prefix}:{category}:{subtype or ''}:{catalog_bootstrap.squash(line)}:"
            f"{catalog_bootstrap.squash(strain)}")


def plan_add_product(catalogs: dict, brand: str, category: str, strain: str, sizes_wanted: list[str],
                     subtype: str | None = None, line: str | None = None,
                     terms: list[str] | tuple = ()) -> Plan:
    """A product the catalog lacks: one entry per size, named as the bootstrap names
    them (line, then strain), with the store names it is sold under recorded so those
    listings match exactly. Subtype is part of a product's identity where the category
    keeps one (taxonomy.keeps_subtype: a strain's whole flower and its pre-ground are
    two products) and is none where it does not (pre-rolls)."""
    import catalog_bootstrap
    import taxonomy
    catalog = catalog_of(catalogs, brand)
    strain, line = (strain or "").strip(), (line or "").strip() or None
    if not strain or not sizes_wanted:
        raise Refused("add-product needs a strain and at least one size")
    if category not in taxonomy.SPECS:
        raise Refused(f"unknown category {category!r}")
    if taxonomy.keeps_subtype(category):
        if not subtype:
            raise Refused(f"{category} keeps a subtype (whole flower and pre-ground are two products); give one")
    elif subtype:
        raise Refused(f"{category} keeps no subtype")
    key = product_key(catalog, category, subtype, line, strain)
    same = [e for e in catalog["entries"] if e.get("is_active", True) and e.get("category") == category
            and (e.get("subtype") or None) == (subtype or None)
            and catalog_bootstrap.squash(e.get("product_line")) == catalog_bootstrap.squash(line)
            and catalog_bootstrap.strain_key(e.get("strain") or e.get("name")) == catalog_bootstrap.strain_key(strain)]
    if same or any(e.get("product_key") == key and e.get("is_active", True) for e in catalog["entries"]):
        raise Refused(f"the catalog has this product: {', '.join(_desc(e) for e in same) or key}; "
                      "add-size it instead")
    by_variant: dict[str, sizes.Size] = {}
    for x in (_label(x, category) for x in sizes_wanted):
        by_variant.setdefault(_variant(x, category), x)        # "28g" and "1 ounce" are one size
    variants = list(by_variant)
    recorded = sorted({t for t in (strip_brand(n, catalog.get("brand_name") or "") for n in terms) if t})
    name = " ".join(x for x in (line, strain) if x)
    index, mine = cm.CatalogIndex(catalog), set(norm_name(name).split())
    for t in recorded:                  # the guard add-term has: a name stays on its own product
        for k in index.by_term.get(t, []):
            other = index.products[k]
            theirs = set(norm_name(other.title).split())
            if other.category == category and not (theirs <= mine or mine <= theirs):
                raise Refused(f'"{t}" is already a store name for {other.title}: recording it on {name} '
                              "too would cross-wire it. Leave it out, or drop-term it there first")
    bootstrap = catalog.get("source_method") == BOOTSTRAP
    taken = {e.get("external_id") for e in catalog["entries"]}
    rows = []
    for i, (variant, x) in enumerate(by_variant.items()):
        external_id = f"{key}:{_total(x)}" if bootstrap else None
        if external_id in taken:
            raise Refused(f"external id {external_id} is taken (an inactive entry?); reactivate that one instead")
        rows.append({"catalog_id": catalog["id"], "external_id": external_id, "product_key": key,
                     "name": name, "product_line": line,
                     "category": category, "subtype": subtype or None, "strain": strain,
                     "variant": variant, "attributes": None,
                     "match_terms": recorded if i == 0 else [], "source": CURATED})
    changed = copy.deepcopy(catalog)
    changed["entries"] += [{**r, "id": f"new-{uuid.uuid4()}", "is_active": True} for r in rows]
    plan = Plan(catalog, changed, category)
    plan.writes.append(("insert", TABLE, None, rows))
    plan.notes.append(f"add {rows[0]['name']} ({category}{'/' + subtype if subtype else ''}) in "
                      f"{', '.join(variants)}" + (f", {len(recorded)} store name(s)" if recorded else ""))
    return plan


def resolve_entry(catalogs: dict, brand: str, ref) -> str:
    """An entry id, or the one active entry a selector names: {"strain", "category",
    "subtype", "line", "size"}, each optional but together naming one entry. Entries a
    plan has just added are not selectable: give their sizes and store names in their
    add-product."""
    if isinstance(ref, str):
        return ref
    import catalog_bootstrap
    catalog = catalog_of(catalogs, brand)
    want_size = ref.get("size")
    hits = []
    for e in catalog["entries"]:
        if not e.get("is_active", True) or str(e["id"]).startswith("new-"):
            continue
        if "strain" in ref and catalog_bootstrap.strain_key(e.get("strain") or e.get("name")) \
                != catalog_bootstrap.strain_key(ref["strain"]):
            continue
        if "category" in ref and e.get("category") != ref["category"]:
            continue
        if "subtype" in ref and (e.get("subtype") or None) != (ref["subtype"] or None):
            continue
        if "line" in ref and catalog_bootstrap.squash(e.get("product_line")) != catalog_bootstrap.squash(ref["line"]):
            continue
        if want_size and sizes.same_size(sizes.parse(want_size, category=e.get("category")),
                                         sizes.parse(e.get("variant"), category=e.get("category"))) is not True:
            continue
        hits.append(e)
    if len(hits) != 1:
        raise Refused(f"{ref} names {len(hits)} active entries"
                      + (f": {', '.join(_desc(e) for e in hits[:5])}" if hits else ""))
    return str(hits[0]["id"])


OPS = ("add-product", "add-size", "set-size", "add-term", "drop-term", "deactivate")


def apply_plan(catalogs: dict, doc: dict) -> Plan:
    """Every edit of a plan file, in order, each seeing the ones before it. One Plan
    out: the catalog before, the catalog after, the writes in order."""
    brand = doc.get("brand") or ""
    state = copy.deepcopy(catalogs)
    original = catalog_of(catalogs, brand)
    writes, notes, categories = [], [], set()
    for n, edit in enumerate(doc.get("edits") or [], 1):
        op = edit.get("op")
        try:
            if op not in OPS:
                raise Refused(f"unknown op {op!r} (one of {', '.join(OPS)})")
            force = bool(edit.get("force"))
            if op == "add-product":
                step = plan_add_product(state, brand, edit.get("category"), edit.get("strain"),
                                        edit.get("sizes") or [], edit.get("subtype"), edit.get("line"),
                                        edit.get("terms") or [])
            else:
                entry = resolve_entry(state, brand, edit.get("entry"))
                if op == "add-size":
                    step = plan_add_size(state, entry, edit.get("size"), force)
                elif op == "set-size":
                    step = plan_set_size(state, entry, edit.get("size"), force)
                elif op == "add-term":
                    step = plan_add_term(state, entry, edit.get("name") or edit.get("term"), force)
                elif op == "drop-term":
                    step = plan_drop_term(state, entry, edit.get("term"), force)
                else:
                    into = resolve_entry(state, brand, edit["into"]) if edit.get("into") else None
                    step = plan_deactivate(state, entry, into)
        except Refused as exc:
            raise Refused(f"edit {n} ({op}): {exc}") from None
        for slug, c in state.items():
            if c.get("id") == step.catalog.get("id"):
                state[slug] = step.changed
        writes += step.writes
        categories.add(step.category)
        notes += [f"{n}. {note}" + (f"  [{edit['why']}]" if edit.get("why") and i == 0 else "")
                  for i, note in enumerate(step.notes)]
    final = catalog_of(state, brand)
    return Plan(original, final, categories.pop() if len(categories) == 1 else None, writes, notes)


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
    trusted = [sum(1 for v in r.values() if v[0] == "trusted") for r in (old[0], new[0])]
    print(f"measure: {len(listings)} active {brand} {plan.category or ''} listings, {runs} runs per side"
          f"{' (Jev on, no cache)' if use_jev else ''}; trusted {trusted[0]} -> {trusted[1]}")
    print("  " + (", ".join(f"{k} {v}" for k, v in tally.items()) or "no listing changes")
          + f"; {noise} listing(s) differed between runs of one side (Jev's noise, not counted)")

    def line(i, before, after):
        return (f'  - "{by_id[i]["name"][:64]}" [{by_id[i].get("variant")}]: '
                f"{before[0]} {before[3]} -> {after[0]} {after[3]}"
                + (" (other product)" if before[1] != after[1] else " (other size)" if before[2] != after[2] else ""))
    # Whatever could be a loss is listed in full; gains are sampled.
    risky = {i: v for i, v in stable.items() if v[0][0] == "trusted" and (v[1][0] != "trusted" or v[0][1] != v[1][1])}
    if risky:
        print("  check each (a trusted match lost or moved to another product):")
        for i, (before, after) in risky.items():
            print(line(i, before, after) + f"\n      {_names(plan, before[2])} -> {_names(plan, after[2])}")
    rest = [(i, v) for i, v in stable.items() if i not in risky]
    for i, (before, after) in rest[:15]:
        print(line(i, before, after))
    if len(rest) > 15:
        print(f"  ... and {len(rest) - 15} more")


def _names(plan: Plan, entry_id) -> str:
    """An entry by name and size, from either side of the plan."""
    for catalog in (plan.changed, plan.catalog):
        for e in catalog["entries"]:
            if str(e["id"]) == str(entry_id):
                return f"{e.get('name')} {e.get('variant') or ''} [{e.get('category')}]"
    return "none"


def apply(plan: Plan) -> None:
    import db_http
    for op, table, query, row in plan.writes:
        if op == "insert":
            print("  inserted", ", ".join(r["id"] for r in db_http.insert(table, row)))
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
    ap_prod = sub.add_parser("add-product", help="a product the catalog lacks, in one or more sizes")
    ap_prod.add_argument("brand")
    ap_prod.add_argument("--category", required=True)
    ap_prod.add_argument("--subtype", help="where the category keeps one: flower, preground, cart, gummy ...")
    ap_prod.add_argument("--line")
    ap_prod.add_argument("--strain", required=True)
    ap_prod.add_argument("--size", action="append", required=True, help="repeat for each size")
    ap_prod.add_argument("--term", action="append", default=[], help="a store's name for it; repeatable")
    pl = sub.add_parser("plan", help="many edits from a JSON file, measured and written together")
    pl.add_argument("file")
    for p in (ap_prod, pl):
        p.add_argument("--measure", action="store_true", help="run the matcher before and after first")
        p.add_argument("--write", action="store_true", help="write it (after the user approved it)")
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
        if args.command == "plan":
            import json
            plan = apply_plan(catalogs, json.loads(Path(args.file).read_text()))
        elif args.command == "add-product":
            plan = plan_add_product(catalogs, args.brand, args.category, args.strain, args.size,
                                    args.subtype, args.line, args.term)
        elif args.command == "drop-term":
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
