#!/usr/bin/env python3
"""
audits.py — The admin audits' work, done by the worker (scripts/audit_worker.py) for the
admin pages (routes/admin/audits.py). The API only writes rows and queues jobs; every
step that reads the pipeline's data or changes the catalog is here, over Supabase's REST
API (db_http), next to the scripts it reuses.

  build_run       flag the run's brands (data_health: price-outlier, odd-title, price),
                  add a random sample of trusted listings, store each item's evidence;
                  then judge them when the run has a judge model
  judge_run       the LLM judge (audit_judge.py) on every item without a verdict
  measure         a proposal's dry run: the matcher before and after
                  (catalog_fix.measure_data), stored on the proposal
  apply           an approved proposal: write it (catalog_fix ops or the listing /
                  reading_examples row), sync the catalog grid, re-match the brand
                  (rematch_brand.rematch), log before and after (audit_log)

Trusted, for the sample: catalog_entry_id set and catalog_match_method 'attributes' or
'manual' (data_health.TRUSTED). Nothing is applied that an admin has not approved.
"""
from __future__ import annotations

import copy
import random
import sys
import urllib.parse
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_store  # noqa: E402
import data_health  # noqa: E402
from brand_catalog import norm_name  # noqa: E402

FLAG_KINDS = ("price-outlier", "odd-title", "price")    # data_health's listing-level detectors
FLAG_DETECTORS = (data_health.trusted_price_outliers, data_health.odd_titles, data_health.price_outliers)
TRUSTED = data_health.TRUSTED                           # ('attributes', 'manual')
MAX_FLAGS = 40          # flagged items per brand per run; the worst first
SIBLINGS = 12           # other listings on the same entry shown as evidence
CANDIDATES = 8          # other entries of the brand offered to the judge
DESCRIPTION_CHARS = 800

CATALOG_KINDS = ("add-product", "add-size", "rekey", "set-subtype", "deactivate")
EXAMPLE_KINDS = ("add-example", "remove-example")
PROPOSAL_KINDS = (*CATALOG_KINDS, "manual-match", *EXAMPLE_KINDS)


class Refused(Exception):
    """A proposal that cannot be measured or applied as it stands; the message says why."""


def now() -> str:
    """A timestamp for the audit tables' `timestamp` columns (naive UTC, as models.utcnow)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _q(value) -> str:
    return urllib.parse.quote(str(value), safe="")


# ---------------------------------------------------------------------------
# Building a run: flags, sample, evidence
# ---------------------------------------------------------------------------

def load_brand(brand: str, catalogs: dict) -> tuple[dict, list[dict], dict]:
    """(catalog, the brand's active listings, dispensaries by id)."""
    import db_http
    catalog = catalog_store.for_brand(catalogs, brand)
    if catalog is None:
        raise Refused(f"no catalog for brand {brand!r}")
    listings = db_http.select_all(
        "listings", f"select={data_health.LISTING_COLS},image_url&is_active=is.true"
                    f"&scraped_brand=ilike.{_q(catalog['brand_name'])}&order=id")
    stores = {d["id"]: d for d in db_http.select_all("dispensaries", "select=id,name,slug,is_active")}
    return catalog, listings, stores


def flags_for(catalogs: dict, listings: list[dict], stores: dict, dismissals: dict) -> dict[str, list[dict]]:
    """{listing id: [{"kind", "text"}]} from the listing-level detectors, leaving out
    findings dismissed in data_health (data_health.visible)."""
    data = data_health.Data(listings, catalogs, stores, data_health.brand_aliases(), datetime.now(timezone.utc))
    found = [f for detector in FLAG_DETECTORS for f in detector(data)]
    shown, _ = data_health.visible(found, dismissals)
    out: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(shown, key=lambda f: f.rank, reverse=True):
        out[f.key.split(":", 1)[1]].append({"kind": f.kind, "text": f.text, "rank": list(f.rank)})
    return dict(out)


def trusted(listing: dict) -> bool:
    return bool(listing.get("catalog_entry_id")) and listing.get("catalog_match_method") in TRUSTED


def sample(listings: list[dict], n: int, exclude: set[str], rng: random.Random | None = None) -> list[dict]:
    pool = [l for l in listings if trusted(l) and str(l["id"]) not in exclude]
    rng = rng or random.Random()
    return rng.sample(pool, min(n, len(pool)))


def _entry_view(e: dict | None) -> dict | None:
    if not e:
        return None
    return {k: e.get(k) for k in ("id", "name", "product_line", "strain", "category", "subtype", "variant",
                                   "image_url", "is_active", "source")}


def _words(*texts) -> set[str]:
    return set(norm_name(" ".join(t or "" for t in texts)).split()) - {"the", "and", "with", "pack", "mg", "g"}


def evidence(listing: dict, catalog: dict, by_entry: dict[str, list[dict]], stores: dict,
             flags: list[dict]) -> dict:
    """What a judge (person or model) sees: the listing, its entry and that product's
    other sizes, the other listings on the entry, a few entries it might be instead."""
    entries = {str(e["id"]): e for e in catalog.get("entries") or []}
    entry = entries.get(str(listing.get("catalog_entry_id") or ""))
    key = (entry or {}).get("product_key") or (catalog_store._product_key(entry) if entry else None)
    sizes_of = [e for e in entries.values() if entry and e is not entry and e.get("is_active", True)
                and (e.get("product_key") or catalog_store._product_key(e)) == key]
    store = lambda l: (stores.get(l.get("dispensary_id")) or {}).get("name")  # noqa: E731
    siblings = [l for l in by_entry.get(str(listing.get("catalog_entry_id")), []) if l["id"] != listing["id"]]
    words = _words(listing.get("scraped_name")) - _words(catalog.get("brand_name"))
    category = (entry or {}).get("category") or listing.get("scraped_category")
    scored = []
    for e in entries.values():
        if e is entry or not e.get("is_active", True) or (category and e.get("category") != category):
            continue
        shared = len(words & _words(e.get("strain"), e.get("name"), e.get("product_line")))
        if shared:
            scored.append((-shared, e.get("name") or "", e.get("variant") or "", e))
    description = (listing.get("description") or "").strip()
    return {
        "brand": catalog.get("brand_name"),
        "flags": [{"kind": f["kind"], "text": f["text"]} for f in flags],
        "listing": {
            "id": str(listing["id"]), "name": listing.get("scraped_name"), "store": store(listing),
            "category": listing.get("scraped_category"), "size_field": listing.get("variant"),
            "page_size": listing.get("size"), "price_cents": listing.get("price_cents"),
            "url": listing.get("url"), "image_url": listing.get("image_url"),
            "description": description[:DESCRIPTION_CHARS] or None,
            "match_method": listing.get("catalog_match_method"),
            "reading": {k: (listing.get("reading") or {}).get(k)
                        for k in ("category", "subtype", "product_line", "strain", "size")},
        },
        "entry": _entry_view(entry),
        "product_other_sizes": [_entry_view(e) for e in sizes_of],
        "siblings": [{"name": l.get("scraped_name"), "store": store(l), "price_cents": l.get("price_cents"),
                      "size_field": l.get("variant"), "url": l.get("url"), "match_method": l.get("catalog_match_method")}
                     for l in sorted(siblings, key=lambda l: l.get("price_cents") or 0)[:SIBLINGS]],
        "siblings_total": len(siblings),
        "candidates": [_entry_view(e) for *_, e in sorted(scored, key=lambda s: s[:3])[:CANDIDATES]],
    }


def items_for_brand(brand: str, catalogs: dict, n: int, dismissals: dict, settled: set[str],
                    rng: random.Random | None = None) -> list[dict]:
    """The audit items (rows for audit_items, without run_id) for one brand: its flagged
    listings, worst first, up to MAX_FLAGS, then `n` sampled trusted listings. `settled`:
    listings an earlier audit found right or a store error; their flags are left out."""
    catalog, listings, stores = load_brand(brand, catalogs)
    by_entry: dict[str, list[dict]] = defaultdict(list)
    for l in listings:
        if l.get("catalog_entry_id"):
            by_entry[str(l["catalog_entry_id"])].append(l)
    flags = {lid: f for lid, f in flags_for(catalogs, listings, stores, dismissals).items() if lid not in settled}
    by_id = {str(l["id"]): l for l in listings}
    flagged = sorted((lid for lid in flags if lid in by_id),
                     key=lambda lid: max(f["rank"] for f in flags[lid]), reverse=True)[:MAX_FLAGS]
    picked = [(by_id[lid], "flag", flags[lid]) for lid in flagged]
    picked += [(l, "sample", []) for l in sample(listings, n, set(flagged), rng)]
    return [{"id": str(uuid.uuid4()), "listing_id": str(l["id"]), "brand": catalog["brand_name"],
             "source": source, "flags": [{"kind": f["kind"], "text": f["text"]} for f in fl],
             "evidence": evidence(l, catalog, by_entry, stores, fl), "created_at": now()}
            for l, source, fl in picked]


def settled_listings() -> set[str]:
    """Listings an earlier audit judged right, or fixed as a store error."""
    import db_http
    rows = db_http.select_all("audit_items", "select=listing_id,verdict,fix&or=(verdict.eq.right,fix.not.is.null)")
    return {str(r["listing_id"]) for r in rows
            if r.get("verdict") == "right" or (r.get("fix") or {}).get("action") == "store-error"}


def build_run(run_id: str, rng: random.Random | None = None) -> dict:
    import db_http
    run = _one("audit_runs", run_id)
    db_http.update("audit_runs", f"id=eq.{run_id}", {"status": "building", "error": None})
    catalogs = catalog_store.load_all("db")
    try:
        dismissals = data_health.load_dismissals()
    except Exception:                       # the table is optional here
        dismissals = {}
    settled = settled_listings()
    items, skipped = [], []
    for brand in run.get("brands") or []:
        try:
            items += items_for_brand(brand, catalogs, int(run.get("sample_size") or 0), dismissals, settled, rng)
        except Refused as exc:
            skipped.append(str(exc))
    for i in range(0, len(items), 100):
        db_http.insert("audit_items", [{**it, "run_id": run_id} for it in items[i:i + 100]])
    judge = bool(run.get("judge_model")) and bool(items)
    db_http.update("audit_runs", f"id=eq.{run_id}", {
        "total_items": len(items), "status": "judging" if judge else "ready",
        "error": "; ".join(skipped) or None, **({} if judge else {"finished_at": now()})})
    if judge:
        judge_run(run_id)
    return {"items": len(items), "skipped": skipped}


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------

def judge_run(run_id: str, client=None) -> dict:
    """Judge every item of the run without a verdict, with the run's model, keeping the
    run's progress and spend current after each item."""
    import audit_judge
    import db_http
    run = _one("audit_runs", run_id)
    model = run.get("judge_model") or audit_judge.DEFAULT_MODEL
    db_http.update("audit_runs", f"id=eq.{run_id}", {"status": "judging", "judge_model": model})
    try:
        client = client or audit_judge.make_client()
    except audit_judge.JudgeUnavailable as exc:
        db_http.update("audit_runs", f"id=eq.{run_id}", {"status": "failed", "error": str(exc), "finished_at": now()})
        return {"judged": 0, "error": str(exc)}
    items = db_http.select_all("audit_items", f"select=id,evidence,verdict&run_id=eq.{run_id}&order=created_at")
    spent = {k: run.get(k) or 0 for k in ("input_tokens", "output_tokens", "cost_usd")}
    judged = sum(1 for it in items if it.get("verdict"))
    errors = []
    for it in items:
        if it.get("verdict"):
            continue
        try:
            v = audit_judge.judge(it.get("evidence") or {}, model, client)
        except Exception as exc:               # one bad item does not stop the run
            errors.append(f"{it['id']}: {exc}")
            continue
        db_http.update("audit_items", f"id=eq.{it['id']}", {
            "verdict": v.verdict, "cause": v.cause, "explanation": v.explanation, "proposed_fix": v.fix,
            "judged_by": f"llm:{v.model}", "judged_at": now()})
        judged += 1
        spent["input_tokens"] += v.input_tokens
        spent["output_tokens"] += v.output_tokens
        spent["cost_usd"] = round(spent["cost_usd"] + v.cost_usd, 6)
        db_http.update("audit_runs", f"id=eq.{run_id}", {**spent, "judged_items": judged})
    # Every item still unjudged because its call failed (a bad key, an outage): the run
    # failed, so the page says so instead of showing a ready run with no verdicts.
    failed = bool(errors) and judged == 0
    db_http.update("audit_runs", f"id=eq.{run_id}", {
        "status": "failed" if failed else "ready", "finished_at": now(), "judged_items": judged,
        "error": (f"{len(errors)} item(s) failed: " + "; ".join(errors[:3])) if errors else None})
    return {"judged": judged, "errors": errors, **spent}


# ---------------------------------------------------------------------------
# Proposals: plan, measure, apply
# ---------------------------------------------------------------------------

def _one(table: str, row_id: str) -> dict:
    import db_http
    rows = db_http.select(table, f"select=*&id=eq.{row_id}")
    if not rows:
        raise Refused(f"no {table} row {row_id}")
    return rows[0]


def catalog_edit(kind: str, params: dict) -> dict:
    """A catalog proposal as one catalog_fix plan edit ({"op": ..., ...})."""
    if kind not in CATALOG_KINDS:
        raise Refused(f"{kind} is not a catalog edit")
    edit = {"op": kind}
    for k in ("entry", "entries", "into", "size", "subtype", "category", "line", "strain", "sizes", "only"):
        if params.get(k) not in (None, "", []):
            edit[k] = params[k]
    if kind == "rekey" and "line" in params and params["line"] == "":
        edit["line"] = ""               # "" clears the line
    return edit


def _examples_rows(slug: str) -> list[dict]:
    import db_http
    return db_http.select_all("reading_examples", f"select=*&brand_slug=eq.{_q(slug)}&order=position")


def _examples_after(kind: str, params: dict, catalog: dict) -> tuple[dict, list[dict]]:
    """(the examples every brand reads with after the proposal, the brand's rows now).
    The table must hold the examples already (scripts/import_reading_examples.py):
    catalog_reading reads the file while the table is empty, so one new row would
    replace all of the file's."""
    import catalog_reading
    import db_http
    if not db_http.select("reading_examples", "select=id&limit=1"):
        raise Refused("the reading_examples table is empty: run scripts/import_reading_examples.py --write first")
    slug = catalog.get("brand_slug") or ""
    rows = _examples_rows(slug)
    every = catalog_reading.examples_from_rows(db_http.select_all(
        "reading_examples", "select=brand_slug,position,listing,size_field,entry,is_active&is_active=is.true"))
    mine = [r for r in rows if r.get("is_active", True)]
    if kind == "add-example":
        selector = params.get("entry") or {}
        if not params.get("listing") or not selector:
            raise Refused("add-example needs a listing title and an entry selector")
        active = [e for e in catalog.get("entries") or [] if e.get("is_active", True)]
        hits = [e for e in active if all((e.get(catalog_reading._SELECTOR.get(k, k)) or None) == (v or None)
                                         for k, v in selector.items())]
        if len(hits) != 1:
            raise Refused(f"the selector {selector} names {len(hits)} active entries; it must name one")
        new = {"listing": params["listing"], "entry": selector,
               **({"size_field": params["size_field"]} if params.get("size_field") else {})}
        every[slug] = every.get(slug, []) + [new]
    else:
        gone = str(params.get("example_id") or "")
        if not any(str(r["id"]) == gone for r in mine):
            raise Refused(f"no active reading example {gone} for {slug}")
        every[slug] = catalog_reading.examples_from_rows(
            [r for r in mine if str(r["id"]) != gone]).get(slug, [])
    return every, rows


def _listing(listing_id: str) -> dict:
    import db_http
    rows = db_http.select("listings", "select=id,scraped_name,scraped_brand,catalog_entry_id,catalog_match_method,"
                                      f"catalog_match_confidence&id=eq.{listing_id}")
    if not rows:
        raise Refused(f"no listing {listing_id}")
    return rows[0]


def measure(proposal: dict, catalogs: dict | None = None) -> dict:
    """The proposal's measured effect: trusted before and after over the brand's active
    listings (of the edited category), the trusted matches lost or moved, the listings
    that change. Raises Refused for one that cannot be planned."""
    import catalog_fix
    kind, params, brand = proposal["kind"], proposal.get("params") or {}, proposal["brand"]
    if kind not in PROPOSAL_KINDS:
        raise Refused(f"unknown proposal kind {kind!r}")
    if kind == "manual-match":
        listing = _listing(params.get("listing_id"))
        catalogs = catalogs or catalog_store.load_all("db")
        catalog = catalog_store.for_brand(catalogs, brand)
        entry = next((e for e in (catalog or {}).get("entries") or [] if str(e["id"]) == str(params.get("entry"))), None)
        if entry is None:
            raise Refused(f"entry {params.get('entry')} is not an active entry of {brand}'s catalog")
        was = "trusted" if listing.get("catalog_match_method") in catalog_fix.cm.OVERLAY_METHODS else "none"
        return {"brand": brand, "listings": 1, "trusted_before": int(was == "trusted"), "trusted_after": 1,
                "tally": {"trusted gained": int(was != "trusted")}, "noise": 0, "risky": [], "more": 0,
                "changes": [{"listing_id": str(listing["id"]), "name": listing.get("scraped_name"),
                             "before": {"trust": listing.get("catalog_match_method"), "entry": listing.get("catalog_entry_id")},
                             "after": {"trust": "manual", "entry": f"{entry.get('name')} {entry.get('variant') or ''}"},
                             "move": None}],
                "notes": [f"manual match \"{listing.get('scraped_name')}\" -> {entry.get('name')} {entry.get('variant') or ''}"]}
    catalogs = catalogs or catalog_fix.for_edit(catalog_store.load_all("db"))
    try:
        if kind in CATALOG_KINDS:
            plan = catalog_fix.apply_plan(catalogs, {"brand": brand, "edits": [catalog_edit(kind, params)]})
            return catalog_fix.measure_data(plan)
        catalog = catalog_fix.catalog_of(catalogs, brand)
        every, _ = _examples_after(kind, params, catalog)
        category = (params.get("entry") or {}).get("category") if kind == "add-example" else None
        plan = catalog_fix.Plan(catalog, copy.deepcopy(catalog), category)
        plan.notes.append(f"{kind}: {params.get('listing') or params.get('example_id')}")
        return catalog_fix.measure_data(plan, examples_after=every)
    except catalog_fix.Refused as exc:
        raise Refused(str(exc)) from None


def measure_proposal(proposal_id: str) -> dict:
    import db_http
    proposal = _one("audit_proposals", proposal_id)
    try:
        m = measure(proposal)
    except Refused as exc:
        db_http.update("audit_proposals", f"id=eq.{proposal_id}",
                       {"status": "failed", "error": f"refused: {exc}", "measured_at": now()})
        return {"refused": str(exc)}
    db_http.update("audit_proposals", f"id=eq.{proposal_id}",
                   {"status": "measured", "measure": m, "measured_at": now(), "error": None})
    return m


def log(actor: str, action: str, brand: str | None, target_kind: str, target_id: str,
        before: dict | None, after: dict | None) -> None:
    import db_http
    db_http.insert("audit_log", {"id": str(uuid.uuid4()), "actor": actor, "action": action, "brand": brand,
                                 "target_kind": target_kind, "target_id": str(target_id),
                                 "before": before, "after": after, "created_at": now()})


def apply(proposal: dict) -> dict:
    """Write an approved proposal, keep the catalog a full grid, re-match the brand.
    Returns {"before", "after", "writes", "rematch"} for the log."""
    import catalog_fix
    import catalog_reading
    import db_http
    import rematch_brand
    kind, params, brand = proposal["kind"], proposal.get("params") or {}, proposal["brand"]
    if proposal.get("status") not in ("approved", "applying"):
        raise Refused(f"the proposal is {proposal.get('status')}, not approved")
    trusted_before = _trusted_count(brand)
    writes: list = []
    if kind == "manual-match":
        listing = _listing(params.get("listing_id"))
        measure(proposal)                    # refuses an entry not in the brand's catalog
        cols = {"catalog_entry_id": params["entry"], "catalog_match_method": "manual",
                "catalog_match_confidence": 1.0}
        db_http.update("listings", f"id=eq.{listing['id']}", cols)
        writes.append({"listing": str(listing["id"]), "before": {k: listing.get(k) for k in cols}, "after": cols})
    elif kind in CATALOG_KINDS:
        catalogs = catalog_fix.for_edit(catalog_store.load_all("db"))
        try:
            plan = catalog_fix.apply_plan(catalogs, {"brand": brand, "edits": [catalog_edit(kind, params)]})
            catalog_fix.write(plan)
        except catalog_fix.Refused as exc:
            raise Refused(str(exc)) from None
        writes = [{"op": op, "table": table, "query": query, "row": row} for op, table, query, row in plan.writes]
    else:
        catalog = catalog_fix.catalog_of(catalog_store.load_all("db"), brand)
        _, rows = _examples_after(kind, params, catalog)
        if kind == "add-example":
            row = {"id": str(uuid.uuid4()), "brand_slug": catalog.get("brand_slug"),
                   "position": max([r.get("position") or 0 for r in rows] or [-1]) + 1,
                   "listing": params["listing"], "size_field": params.get("size_field"),
                   "entry": params["entry"], "is_active": True, "source": f"audit proposal {proposal['id']}",
                   "created_at": now()}
            db_http.insert("reading_examples", row)
            writes.append({"insert": row})
        else:
            db_http.update("reading_examples", f"id=eq.{params['example_id']}", {"is_active": False})
            writes.append({"deactivated": params["example_id"]})
        catalog_reading.reload_examples()
    try:
        r = rematch_brand.rematch(brand, write_changes=True)
        rematch = {k: r[k] for k in ("listings", "trusted_before", "trusted_after", "written", "stored_readings")}
        rematch["changed"] = len(r["changes"])
    except LookupError as exc:
        rematch = {"error": str(exc)}
    result = {"before": {"trusted": trusted_before}, "after": {"trusted": _trusted_count(brand)},
              "writes": writes, "rematch": rematch}
    log(proposal.get("decided_by") or "admin", f"apply:{kind}", brand, "proposal", proposal["id"],
        {"trusted": trusted_before, "params": params}, {"trusted": result["after"]["trusted"], "writes": writes})
    return result


def apply_proposal(proposal_id: str) -> dict:
    import db_http
    proposal = _one("audit_proposals", proposal_id)
    db_http.update("audit_proposals", f"id=eq.{proposal_id}", {"status": "applying"})
    try:
        result = apply({**proposal, "status": "applying"})
    except Refused as exc:
        db_http.update("audit_proposals", f"id=eq.{proposal_id}", {"status": "failed", "error": f"refused: {exc}"})
        return {"refused": str(exc)}
    db_http.update("audit_proposals", f"id=eq.{proposal_id}",
                   {"status": "applied", "applied_at": now(), "result": result, "error": None})
    return result


def _trusted_count(brand: str) -> int:
    import catalog_match as cm
    import db_http
    rows = db_http.select_all("listings", f"select=catalog_match_method&is_active=is.true"
                                          f"&scraped_brand=ilike.{_q(brand)}")
    return sum(1 for r in rows if r.get("catalog_match_method") in cm.OVERLAY_METHODS)
