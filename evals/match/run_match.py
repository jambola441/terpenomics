#!/usr/bin/env python3
"""
run_match.py — Scores the catalog matcher on the labelled test set (cases/sample.json).
Re-runs the matcher live on each listing (lexical tiers, then Jev, no answer cache) and
compares its product with the label, at each probability bar a Jev pick could be
trusted at. Catalogs from a brand's own site and catalogs built from store listings are
reported apart: they have separate bars (catalog_match.AUTO, AUTO_BOOTSTRAP).

    DB_VIA_HTTP=1 python evals/match/run_match.py

Needs OPENROUTER_API_KEY (Jev) and the database. Unlabelled and unsure cases are left
out. Writes results/summary.md and results/decisions.json.

Precision at a bar: of the listings the matcher would trust (an exact name, or a Jev
pick at or above the bar), the share whose product is the label's. Recall: of the
listings whose product the catalog has, the share trusted with the right product. A
size the catalog lacks makes the right product the wrong entry; "entry right" counts
only listings the label puts in one entry.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import catalog_match  # noqa: E402
import catalog_store  # noqa: E402
import jev  # noqa: E402

BARS = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95]
SAMPLE = HERE / "cases" / "sample.json"


def group(case: dict) -> str:
    return "store-built" if case.get("catalog_source") == "listings_bootstrap" else "brand site"


def usable(case: dict) -> bool:
    label = case.get("label")
    return bool(label) and label.get("confidence") != "unsure"


def trusted(d: dict, bar: float) -> bool:
    return d["method"] == "exact" or (d["method"] in ("jev", "jev_review") and (d["p"] or 0) >= bar)


def score(rows: list[tuple[dict, dict]], bars: list[float] = BARS) -> dict:
    """rows: (case, decision) with decision {method, product_key, entry_id, p}. Per
    group and bar: listings trusted, right product, wrong, precision, recall, right
    entry; and the exact tier on its own."""
    out = {}
    for name in ("all", "brand site", "store-built"):
        sel = [(c, d) for c, d in rows if name == "all" or group(c) == name]
        has_product = sum(1 for c, _ in sel if c["label"].get("product_key"))
        g = {"listings": len(sel), "in_catalog": has_product,
             "exact": sum(d["method"] == "exact" for _, d in sel),
             "exact_wrong": sum(d["method"] == "exact" and d["product_key"] != c["label"].get("product_key")
                                for c, d in sel), "bars": {}}
        for bar in bars:
            t = [(c, d) for c, d in sel if trusted(d, bar)]
            right = [(c, d) for c, d in t if d["product_key"] and d["product_key"] == c["label"].get("product_key")]
            entry_labelled = [(c, d) for c, d in right if c["label"].get("entry_id")]
            g["bars"][bar] = {
                "trusted": len(t), "right": len(right), "wrong": len(t) - len(right),
                "precision": round(len(right) / len(t), 3) if t else None,
                "recall": round(len(right) / has_product, 3) if has_product else None,
                "entry_right": sum(d["entry_id"] == c["label"]["entry_id"] for c, d in entry_labelled),
                "entry_labelled": len(entry_labelled)}
        out[name] = g
    return out


def decide(cases: list[dict], catalogs: dict, usage: jev.Usage) -> dict[str, dict]:
    by_brand = defaultdict(list)
    for c in cases:
        l = c["listing"]
        by_brand[catalog_store.brand_key(c["brand"])].append(
            {"id": c["id"], "name": l.get("name") or "", "category": l.get("category"), "subtype": l.get("subtype"),
             "variant": l.get("size_field"), "description": l.get("description")})
    out = {}
    for key, listings in by_brand.items():
        for d in catalog_match.resolve(catalogs[key], listings, use_jev=True, cache=None, usage=usage):
            out[d.listing["id"]] = {"method": d.method, "product_key": d.product_key,
                                    "entry_id": (d.entry or {}).get("id"), "p": d.confidence}
    return out


def report(scores: dict, rows: list[tuple[dict, dict]], catalogs: dict) -> str:
    bars_now = {"brand site": catalog_match.AUTO, "store-built": catalog_match.AUTO_BOOTSTRAP}
    lines = [f"# Catalog matcher on {scores['all']['listings']} labelled listings", ""]
    for name in ("brand site", "store-built", "all"):
        g = scores[name]
        lines += [f"## {name}" + (f" (bar today {bars_now[name]})" if name in bars_now else ""), "",
                  f"{g['listings']} listings, {g['in_catalog']} whose product the catalog has; exact names "
                  f"{g['exact']} ({g['exact_wrong']} wrong).", "",
                  "| bar | trusted | right product | wrong | precision | recall | right entry |",
                  "|---|---|---|---|---|---|---|"]
        for bar, b in g["bars"].items():
            lines.append(f"| {bar} | {b['trusted']} | {b['right']} | {b['wrong']} | {b['precision']} | "
                         f"{b['recall']} | {b['entry_right']}/{b['entry_labelled']} |")
        lines.append("")
    names = {}
    for cat in catalogs.values():
        for e in cat.get("entries") or []:
            names.setdefault(e.get("product_key"), e.get("name"))
    wrong = [(c, d) for c, d in rows if trusted(d, bars_now[group(c)])
             and d["product_key"] != c["label"].get("product_key")]
    if wrong:
        lines += ["## Trusted today and wrong", ""]
        for c, d in wrong:
            lines.append(f"- {c['brand']}: {c['listing']['name']!r} -> {names.get(d['product_key'])!r} "
                         f"({d['method']} {d['p']}); label {names.get(c['label'].get('product_key'))!r}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args()
    if not jev.available():
        sys.exit("No OPENROUTER_API_KEY: the matcher's Jev tier needs it")
    cases = [c for c in json.loads(SAMPLE.read_text())["cases"] if usable(c)]
    if not cases:
        sys.exit("No labelled cases yet: run label_sample.py first")
    catalogs = catalog_store.load_all("db")
    usage = jev.Usage()
    decisions = decide(cases, catalogs, usage)
    rows = [(c, decisions[c["id"]]) for c in cases if c["id"] in decisions]
    scores = score(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decisions.json").write_text(json.dumps({c["id"]: d for c, d in rows}, indent=1))
    text = report(scores, rows, catalogs)
    (out / "summary.md").write_text(text + "\n")
    print(text)
    print(f"\nJev: {usage}; methods {dict(Counter(d['method'] for _, d in rows))}")


if __name__ == "__main__":
    main()
