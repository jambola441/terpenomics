"""Score an enrichment eval run the way its listings would land: after the catalog match.

run_eval.py scores what enrichment writes. The importer then matches every listing to
its brand's catalog and, on a trusted match, takes the entry's subtype, strain and
product line (import_listings._overlay). This applies that match to each labelled case
of a results file and scores both: enrichment alone, and after the match.

The match reads the live catalogs (read-only; the match cache is off) and asks Jev for
listings the exact tier does not settle, about $0.01 for the whole suite. Catalogs
change, so a re-score on another day can differ for reasons outside enrichment.

    python evals/enrich/score_after_match.py evals/enrich/results/haiku-or.json
    python evals/enrich/score_after_match.py run1/haiku-or.json run2/haiku-or.json --show
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))

import catalog_match  # noqa: E402
import catalog_store  # noqa: E402
import jev  # noqa: E402
from catalog_enricher import _is_masked  # noqa: E402

FIELDS = ["category", "subtype", "strain", "product_line", "variant"]
norm = lambda v: (v if v is not None else "").strip().lower()  # noqa: E731


def load_inputs() -> dict[str, tuple[dict, dict]]:
    """case id -> (input, expect), from the case files as they are now, so a run scored
    after a relabel is scored against the new labels."""
    out = {}
    for f in glob.glob(str(HERE / "cases" / "*.json")):
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        for it in (data if isinstance(data, list) else data.get("cases", [])):
            if isinstance(it, dict) and "input" in it and "expect" in it:
                out[it["id"]] = (it["input"], it["expect"])
    return out


def overlay(got: dict, entry: dict, name: str) -> dict:
    """The fields a trusted match gives the listing, as import_listings._overlay does."""
    after = dict(got)
    subtype = catalog_match.matched_subtype(entry, name)
    if subtype:
        after["subtype"] = subtype
    if entry.get("strain") and not _is_masked(entry["strain"]):
        after["strain"] = entry["strain"]
    after["product_line"] = entry.get("product_line")
    return after


def score(path: str, catalogs: dict, inputs: dict, usage: jev.Usage, show: bool) -> Counter:
    res = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = [(it["id"], *inputs[it["id"]], it["got"])
             for items in res["scores"].values() for it in items
             if "expect" in it and it["id"] in inputs]
    by_brand: dict[str, list[dict]] = {}
    for cid, inp, _, got in cases:
        key = catalog_store.brand_key(inp.get("brand"))
        if key in catalogs:
            by_brand.setdefault(key, []).append(
                {"id": cid, "name": inp.get("name") or "", "category": got.get("category"),
                 "subtype": got.get("subtype"), "variant": got.get("variant"),
                 "description": inp.get("description")})
    decisions = {}
    for key, listings in by_brand.items():
        for d in catalog_match.resolve(catalogs[key], listings, use_jev=True, cache=None, usage=usage):
            decisions[d.listing["id"]] = d
    c = Counter()
    for cid, inp, exp, got in cases:
        d = decisions.get(cid)
        trusted = d is not None and d.method in catalog_match.OVERLAY_METHODS and d.entry
        after = overlay(got, d.entry, inp.get("name") or "") if trusted else got
        ok_before = all(norm(got.get(f)) == norm(v) for f, v in exp.items())
        ok_after = all(norm(after.get(f)) == norm(v) for f, v in exp.items())
        c["cases"] += 1
        c["matched"] += bool(trusted)
        c["passed, enrichment"] += ok_before
        c["passed, after match"] += ok_after
        for f, v in exp.items():
            c[f"field {f}"] += 1
            c[f"right {f}, after match"] += norm(after.get(f)) == norm(v)
        if show and ok_before != ok_after:
            bad = {f: (got.get(f), after.get(f), v) for f, v in exp.items()
                   if norm(got.get(f)) != norm(v) or norm(after.get(f)) != norm(v)}
            print(f"  {'fixed' if ok_after else 'broke'} {cid}: {bad}")
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("results", nargs="+", help="run_eval.py results files (<model>.json)")
    ap.add_argument("--show", action="store_true", help="print cases the match fixes or breaks")
    args = ap.parse_args()
    os.environ.setdefault("DB_VIA_HTTP", "1")
    catalogs = catalog_store.load_all("db")
    inputs = load_inputs()
    usage = jev.Usage()
    runs = [score(p, catalogs, inputs, usage, args.show) for p in args.results]
    mean = lambda k: sum(r[k] for r in runs) / len(runs)  # noqa: E731
    print(f"{len(runs)} run(s), {runs[0]['cases']} labelled cases, {mean('matched'):.1f} with a trusted match")
    print(f"  passed, enrichment alone: {mean('passed, enrichment'):.1f}")
    print(f"  passed, after the match:  {mean('passed, after match'):.1f}")
    for f in FIELDS:
        if runs[0][f"field {f}"]:
            print(f"    {f:<13} {mean(f'right {f}, after match'):6.1f} / {runs[0][f'field {f}']}")
    print("  " + usage.summary())


if __name__ == "__main__":
    main()
