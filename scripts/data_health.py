"""The daily data checks behind /audit-terpee-listings.

Deterministic detectors over production data. They read over Supabase's REST API
(db_http), so they run from any session holding SUPABASE_URL and the service key,
with nothing to install. Each finding has a stable key. `dismiss` records one judged
not a problem, and later reports leave it out until its evidence grows. `report
--save` keeps a snapshot, so the next report can say what changed and what is new.

Detecting is all this does. Judging a finding is the agent's job (the skill), and
writing a fix is scripts/catalog_fix.py's.

  python3 scripts/data_health.py report             # today's numbers and findings
  python3 scripts/data_health.py report --save      # ...kept for tomorrow's deltas
  python3 scripts/data_health.py dismiss KEY --reason "why it is not a problem"
  python3 scripts/data_health.py undismiss KEY
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_match as cm  # noqa: E402
import catalog_store  # noqa: E402
import sizes  # noqa: E402
from brand_catalog import norm_name  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STALE_HOURS = 30    # the cron runs daily at 13:00 UTC; a store unseen this long missed a run
TOP = 15            # findings printed per detector; the rest are counted
MIN_STORES = 2      # a size or a review cluster at one store is noise, as for the bootstrap
SECTIONS = [        # (kind, title), in the order the report prints them
    ("stale-store", "Stores the daily run missed"),
    ("shared-name", "Store names recorded on unrelated products"),
    ("missing-size", "Sizes 2+ stores sell that the matched product lacks"),
    ("review-cluster", "Products with review-only listings at 2+ stores"),
    ("size-sync", "Product-page sizes the last import left behind"),
    ("brandless", "Listings with no brand that start with a catalog brand's name"),
]


@dataclass
class Finding:
    key: str
    kind: str
    text: str
    evidence: int        # listings (or products) behind it; a dismissal reopens when it grows
    look: str = ""       # the command that shows it
    rank: tuple = ()     # sort order within its section, biggest first


@dataclass
class Data:
    listings: list[dict]
    catalogs: dict
    dispensaries: dict[str, dict]
    aliases: dict[str, str]
    now: datetime


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

LISTING_COLS = ("id,dispensary_id,scraped_name,scraped_brand,scraped_category,variant,size,"
                "description,catalog_entry_id,catalog_match_method,catalog_match_confidence,last_seen_at")


def load(now: datetime | None = None) -> Data:
    import db_http
    listings = db_http.select_all("listings", f"select={LISTING_COLS}&is_active=is.true&order=id")
    stores = {d["id"]: d for d in db_http.select_all("dispensaries", "select=id,name,slug,is_active")}
    return Data(listings, catalog_store.load_all("db"), stores, brand_aliases(),
                now or datetime.now(timezone.utc))


def brand_aliases() -> dict[str, str]:
    """data/brand_aliases.json's raw spellings (normalised) -> canonical brand."""
    path = ROOT / "data" / "brand_aliases.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {norm_name(k): v for k, v in raw.items() if not k.startswith("_") and isinstance(v, str)}


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _matched(data: Data):
    """(listing, catalog, entry, index, product key) for each listing with a catalog entry."""
    by_id = catalog_store.entries_by_id(data.catalogs)
    indexes = {id(c): cm.CatalogIndex(c) for c in data.catalogs.values()}
    for l in data.listings:
        hit = by_id.get(str(l.get("catalog_entry_id") or ""))
        if not hit:
            continue
        catalog, entry = hit
        index = indexes[id(catalog)]
        key = entry.get("product_key") or catalog_store._product_key(entry)
        if key in index.products:
            yield l, catalog, entry, index, key


def _total(s: sizes.Size) -> str:
    return f"{s.grams:g}g" if s.grams is not None else f"{s.mg:g}mg" if s.mg is not None else ""


def _example(names) -> str:
    return "; ".join(f'"{n[:70]}"' for n in list(dict.fromkeys(names))[:2])


def _entries_look(brand: str, titles) -> str:
    rx = "|".join(re.escape(t) for t in dict.fromkeys(titles) if t)
    return f'python3 scripts/catalog_shape.py entries "{brand}" "(?i){rx}"'


# ---------------------------------------------------------------------------
# Detectors: each reads Data and returns findings, nothing else
# ---------------------------------------------------------------------------

def stale_stores(data: Data) -> list[Finding]:
    """A store whose newest active listing is older than STALE_HOURS: its scraper failed
    or was skipped, and its listings are a day or more out of date."""
    newest: dict[str, datetime] = {}
    count = Counter()
    for l in data.listings:
        store = l["dispensary_id"]
        count[store] += 1
        seen = _when(l.get("last_seen_at"))
        if seen and (store not in newest or seen > newest[store]):
            newest[store] = seen
    out = []
    for store, n in count.items():
        seen = newest.get(store)
        if seen is not None and data.now - seen <= timedelta(hours=STALE_HOURS):
            continue
        d = data.dispensaries.get(store, {})
        slug = d.get("slug") or store
        when = f"{seen:%Y-%m-%d %H:%M} UTC" if seen else "never"
        out.append(Finding(f"stale-store:{slug}", "stale-store",
                           f"{d.get('name') or slug}: newest listing seen {when}; {n} listing(s) still active",
                           n, f"Render cron logs (crn-db1fveugekts73dl7s60), search \"{slug}\"",
                           (n,)))
    return out


def cross_wired_names(data: Data) -> list[Finding]:
    """A store name recorded on two or more products of one category whose titles are
    unrelated (not one product's titles read short and long). The exact tier gives it
    to the product it names (catalog_match), so it moves no listings while the right
    product holds it too; it is still a store's slip on the others."""
    out = []
    for catalog in data.catalogs.values():
        index = cm.CatalogIndex(catalog)
        for term, keys in index.by_term.items():
            keys = list(dict.fromkeys(keys))
            for category in sorted({index.products[k].category or "" for k in keys}):
                same = [k for k in keys if (index.products[k].category or "") == category]
                if len(same) < 2 or not index.unrelated(same):
                    continue
                titles = [index.products[k].title for k in same]
                named = index.named(same, term)
                verdict = (f"names {index.products[named[0]].title}" if len(named) == 1
                           else "names none of them" if not named else "names several")
                out.append(Finding(
                    f"shared-name:{catalog['brand_slug']}:{term}", "shared-name",
                    f'{catalog["brand_name"]} {category}: "{term}" on {" · ".join(titles)} ({verdict})',
                    len(same), _entries_look(catalog["brand_name"], titles),
                    (len(named) == 1, len(same))))
    return out


def missing_sizes(data: Data) -> list[Finding]:
    """Listings matched to a product that does not come in the size they state, grouped
    by product and size, at MIN_STORES or more stores. Either a real size the catalog
    lacks (add it) or a typo stores share (nothing to add). A dose typo the product
    page already corrects (catalog_match.catalog_size) is left out."""
    groups: dict[tuple, list] = defaultdict(list)
    for l, catalog, entry, index, key in _matched(data):
        product = index.products[key]
        category = l.get("scraped_category") or product.category
        s = sizes.parse(l.get("variant"), l.get("scraped_name"), category=category)
        if s.is_empty() or product.size_ok(s) is not False:
            continue
        if (l.get("catalog_match_method") in cm.OVERLAY_METHODS
                and cm.catalog_size(l.get("variant"), l.get("scraped_name"), entry, product.entries,
                                    l.get("description"))):
            continue
        groups[(id(catalog), key, _total(s))].append((l, catalog, product))
    out = []
    for (_, key, total), rows in groups.items():
        _, catalog, product = rows[0]
        stores = len({l["dispensary_id"] for l, _, _ in rows})
        if stores < MIN_STORES:
            continue
        methods = Counter(l.get("catalog_match_method") for l, _, _ in rows)
        has = ", ".join(sorted({e.get("variant") or "?" for e in product.entries}))
        out.append(Finding(
            f"missing-size:{catalog['brand_slug']}:{key}:{total}", "missing-size",
            f"{catalog['brand_name']} {product.title} ({product.category}) comes in {has}; "
            f"{len(rows)} listing(s) at {stores} store(s) say {total} "
            f"({', '.join(f'{m} {n}' for m, n in methods.most_common())}): "
            + _example(l.get("scraped_name") or "" for l, _, _ in rows),
            len(rows), f'python3 scripts/catalog_shape.py listings "{catalog["brand_name"]}" '
                       f'"(?i){re.escape(product.strain or product.title)}" --descriptions',
            (stores, len(rows))))
    return out


def review_clusters(data: Data) -> list[Finding]:
    """Products with review-only matches (jev_review) at MIN_STORES or more stores whose size
    fits: the catalog likely has the product and the stores name it in a way that
    leaves the model unsure. Recording a store's name settles it, once the listings are
    checked to be that product."""
    groups: dict[tuple, list] = defaultdict(list)
    for l, catalog, entry, index, key in _matched(data):
        if l.get("catalog_match_method") != "jev_review":
            continue
        product = index.products[key]
        s = sizes.parse(l.get("variant"), l.get("scraped_name"),
                        category=l.get("scraped_category") or product.category)
        if not s.is_empty() and product.size_ok(s) is False:
            continue        # a size the product lacks: missing_sizes reports it
        groups[(id(catalog), key)].append((l, catalog, product))
    out = []
    for (_, key), rows in groups.items():
        stores = len({l["dispensary_id"] for l, _, _ in rows})
        if stores < MIN_STORES:
            continue
        _, catalog, product = rows[0]
        conf = [float(l["catalog_match_confidence"]) for l, _, _ in rows
                if l.get("catalog_match_confidence") is not None]
        span = f", Jev {min(conf):.2f}-{max(conf):.2f}" if conf else ""
        out.append(Finding(
            f"review-cluster:{catalog['brand_slug']}:{key}", "review-cluster",
            f"{catalog['brand_name']} {product.title}: {len(rows)} review-only listing(s) at "
            f"{stores} stores{span}: " + _example(l.get("scraped_name") or "" for l, _, _ in rows),
            len(rows), f'python3 scripts/catalog_shape.py listings "{catalog["brand_name"]}" '
                       f'"(?i){re.escape(product.strain or product.title)}" --descriptions',
            (stores, len(rows))))
    return out


def size_sync(data: Data) -> list[Finding]:
    """Listings whose product-page size (listings.size) is not what the importer would
    write now: a catalog edit since the last import, or an import that did not run."""
    import import_listings
    recs = [dict(l) for l in data.listings if l.get("catalog_entry_id")]
    stored = {r["id"]: r.get("size") for r in recs}
    import_listings.assign_sizes(recs, data.catalogs)
    off = [r for r in recs if r["size"] != (stored[r["id"]] if stored[r["id"]] is not None else r["variant"])]
    if not off:
        return []
    return [Finding("size-sync", "size-sync",
                    f"{len(off)} listing(s): " + "; ".join(
                        f'"{(r.get("scraped_name") or "")[:50]}" {stored[r["id"]] or r["variant"]} -> {r["size"]}'
                        for r in off[:3]),
                    len(off), "python3 scripts/catalog_fix.py size-sync", (len(off),))]


def brandless(data: Data) -> list[Finding]:
    """Listings with no brand whose name starts with a catalog brand's name (or one of
    its spellings in brand_aliases.json): no catalog is tried for them at import."""
    names = {norm_name(c["brand_name"]): c for c in data.catalogs.values()}
    for alias, canonical in data.aliases.items():
        catalog = names.get(norm_name(canonical))
        if catalog and alias:
            names.setdefault(alias, catalog)
    by_brand: dict[str, list[str]] = defaultdict(list)
    for l in data.listings:
        if l.get("scraped_brand"):
            continue
        name = norm_name(l.get("scraped_name") or "")
        for spelling in sorted(names, key=len, reverse=True):
            if name == spelling or name.startswith(spelling + " "):
                by_brand[names[spelling]["brand_slug"]].append(l.get("scraped_name") or "")
                break
    by_slug = {c["brand_slug"]: c for c in data.catalogs.values()}
    return [Finding(f"brandless:{slug}", "brandless",
                    f'{len(rows)} listing(s) with no brand start with "{by_slug[slug]["brand_name"]}": '
                    + _example(rows), len(rows),
                    'python3 scripts/db_http.py select listings "select=scraped_name,dispensary_id'
                    '&is_active=is.true&scraped_brand=is.null&scraped_name=ilike.'
                    + urllib.parse.quote(by_slug[slug]["brand_name"]) + '*"', (len(rows),))
            for slug, rows in by_brand.items()]


DETECTORS = (stale_stores, cross_wired_names, missing_sizes, review_clusters, size_sync, brandless)


def detect(data: Data) -> list[Finding]:
    return [f for detector in DETECTORS for f in detector(data)]


def metrics(data: Data, findings: list[Finding]) -> dict:
    brands = {c["brand_name"].lower() for c in data.catalogs.values()}
    in_catalog = sum(1 for l in data.listings if (l.get("scraped_brand") or "").lower() in brands)
    trusted = sum(1 for l in data.listings if l.get("catalog_match_method") in cm.OVERLAY_METHODS)
    out = {"active_listings": len(data.listings),
           "stores": len({l["dispensary_id"] for l in data.listings}),
           "catalog_brand_listings": in_catalog,
           "trusted": trusted,
           "trusted_share": round(100 * trusted / in_catalog, 1) if in_catalog else 0.0,
           "review_only": sum(1 for l in data.listings if l.get("catalog_match_method") == "jev_review"),
           "no_brand": sum(1 for l in data.listings if not l.get("scraped_brand"))}
    for kind, _ in SECTIONS:
        out[f"findings_{kind}"] = sum(1 for f in findings if f.kind == kind)
    return out


# ---------------------------------------------------------------------------
# Memory: snapshots and dismissals
# ---------------------------------------------------------------------------

def visible(findings: list[Finding], dismissals: dict[str, dict]) -> tuple[list[Finding], list[Finding]]:
    """(shown, hidden): a dismissed finding stays hidden while its evidence is no more
    than it was when dismissed."""
    shown, hidden = [], []
    for f in findings:
        d = dismissals.get(f.key)
        (hidden if d and f.evidence <= int(d["evidence"]) else shown).append(f)
    return shown, hidden


def previous_snapshot() -> dict | None:
    import db_http
    rows = db_http.select("data_health_snapshots", "select=*&order=taken_at.desc&limit=1")
    return rows[0] if rows else None


def load_dismissals() -> dict[str, dict]:
    import db_http
    return {r["finding_key"]: r for r in db_http.select_all("data_health_dismissals", "select=*")}


def save_snapshot(m: dict, findings: list[Finding]) -> None:
    import db_http
    db_http.insert("data_health_snapshots", {"metrics": m, "findings": {f.key: f.evidence for f in findings}})


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def _delta(now, before) -> str:
    if before is None or now == before:
        return ""
    diff = now - before
    return f" ({'+' if diff > 0 else ''}{round(diff, 1) if isinstance(diff, float) else diff})"


def render(m: dict, findings: list[Finding], dismissals: dict[str, dict], prev: dict | None,
           now: datetime, top: int = TOP, memory_note: str = "") -> str:
    pm = (prev or {}).get("metrics") or {}
    seen_before = set(((prev or {}).get("findings") or {}).keys())
    since = f" · vs {str(prev['taken_at'])[:16].replace('T', ' ')} UTC" if prev else " · no earlier snapshot"
    out = [f"# Data health · {now:%Y-%m-%d %H:%M} UTC{since}"]
    if memory_note:
        out.append(f"({memory_note})")
    out += ["",
            "## Numbers",
            f"- active listings {m['active_listings']:,}{_delta(m['active_listings'], pm.get('active_listings'))}"
            f" at {m['stores']} stores{_delta(m['stores'], pm.get('stores'))}",
            f"- brands with a catalog: {m['catalog_brand_listings']:,} listings; trusted match "
            f"{m['trusted']:,} = {m['trusted_share']}%{_delta(m['trusted_share'], pm.get('trusted_share'))}; "
            f"review-only {m['review_only']:,}{_delta(m['review_only'], pm.get('review_only'))}",
            f"- listings with no brand {m['no_brand']:,}{_delta(m['no_brand'], pm.get('no_brand'))}"]
    shown, hidden = visible(findings, dismissals)
    new = [f for f in shown if f.key not in seen_before]
    out += ["", f"## Findings · {len(shown)} open"
                + (f", {len(new)} new" if prev else "")
                + (f", {len(hidden)} dismissed (hidden)" if hidden else "")]
    for kind, title in SECTIONS:
        mine = sorted((f for f in shown if f.kind == kind), key=lambda f: f.rank, reverse=True)
        gone = sum(1 for f in hidden if f.kind == kind)
        out.append(f"\n### {title} · {len(mine)}" + (f" (+{gone} dismissed)" if gone else ""))
        for f in mine[:top]:
            d = dismissals.get(f.key)
            tags = (["NEW"] if prev and f.key not in seen_before else []) + \
                   ([f"dismissed at {d['evidence']}, now {f.evidence}"] if d else [])
            out.append(f"- {'[' + ', '.join(tags) + '] ' if tags else ''}{f.text}")
            out.append(f"  key: {f.key}")
            if f.look:
                out.append(f"  look: {f.look}")
        if len(mine) > top:
            out.append(f"- ... and {len(mine) - top} more (--top {len(mine)} lists them)")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="today's numbers and findings")
    rep.add_argument("--save", action="store_true", help="keep a snapshot for the next report's deltas")
    rep.add_argument("--top", type=int, default=TOP, help="findings printed per section")
    dis = sub.add_parser("dismiss", help="record a finding as not a problem")
    dis.add_argument("key")
    dis.add_argument("--reason", required=True)
    und = sub.add_parser("undismiss", help="show a dismissed finding again")
    und.add_argument("key")
    args = ap.parse_args(argv)

    import db_http
    if args.command == "undismiss":
        gone = db_http.delete("data_health_dismissals", f"finding_key=eq.{urllib.parse.quote(args.key, safe='')}")
        print("undismissed" if gone else f"no dismissal for {args.key}")
        return 0

    data = load()
    findings = detect(data)
    if args.command == "dismiss":
        hit = next((f for f in findings if f.key == args.key), None)
        if hit is None:
            print(f"{args.key} is not a current finding; nothing dismissed", file=sys.stderr)
            return 1
        db_http.upsert("data_health_dismissals", {"finding_key": hit.key, "reason": args.reason,
                                                  "evidence": hit.evidence}, on_conflict="finding_key")
        print(f"dismissed {hit.key} at evidence {hit.evidence}: {args.reason}")
        return 0

    m = metrics(data, findings)
    note = ""
    try:
        prev, dismissals = previous_snapshot(), load_dismissals()
    except db_http.DbHttpError as exc:      # migration 0009 not applied yet
        prev, dismissals, note = None, {}, f"no memory: {str(exc)[:120]}"
    print(render(m, findings, dismissals, prev, data.now, args.top, note))
    if args.save and not note:
        save_snapshot(m, findings)
        print(f"\nsnapshot saved ({data.now:%Y-%m-%d %H:%M} UTC)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
