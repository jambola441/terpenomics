#!/usr/bin/env python3
"""
run_review.py — Measures the review agent (scripts/review_agent.py) on the fixed queues
in evals/review/cases/: per field, how often its answer matches the label, beside the
first pass it would replace (Jev-only) and, where recorded, today's production path.

    python evals/review/run_review.py --models claude-sonnet-5-5,claude-opus-5-5
    python evals/review/run_review.py --models claude-sonnet-5-5 --limit 5     # smoke run

Needs ANTHROPIC_API_KEY, and the database (DB_VIA_HTTP=1 or DATABASE_URL) for the
catalogs, other stores' listings and prices. Writes results/<model>.json (answers,
scores, usage, each conversation's trace) and results/summary.md.

Scoring: a field counts when the answer is one of the label's accepted values (case
and surrounding spaces aside); a field the label leaves out is not scored, nor a
subtype where the category keeps none. "Applied" is what the pipeline would write: the
agent's answer, or the first pass's when the agent was unsure or answered nothing.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import review_agent  # noqa: E402
import review_tools  # noqa: E402
import taxonomy  # noqa: E402

FIELDS = ["category", "subtype", "strain", "product_line", "variant"]


def norm(v) -> str:
    return (v if v is not None else "").strip().lower()


def gold_labels() -> dict[str, dict]:
    labels = {}
    for path in glob.glob(str(ROOT / "evals" / "enrich" / "cases" / "*.json")):
        suite = json.loads(Path(path).read_text())
        if suite.get("eval_type") != "identity_cluster":
            labels.update({c["id"]: c["expect"] for c in suite["cases"]})
    return labels


def load_cases(patterns: list[str]) -> list[dict]:
    gold = gold_labels()
    cases = []
    for pat in patterns:
        for path in sorted(glob.glob(pat if Path(pat).is_absolute() else str(ROOT / pat))):
            for c in json.loads(Path(path).read_text())["cases"]:
                if c.get("labels") == "gold":
                    c = {**c, "expect": gold[c["id"]]}
                cases.append({**c, "_file": Path(path).name})
    return cases


def wanted(case: dict) -> dict[str, list]:
    """field -> the values that count."""
    out = {f: [v] for f, v in case["expect"].items() if f in FIELDS}
    out.update({f: list(v) for f, v in (case.get("accept") or {}).items()})
    category = case["expect"].get("category") or case["listing"].get("category")
    if "subtype" in out and not taxonomy.keeps_subtype(category):
        del out["subtype"]
    return out


def answer_fields(answer: dict | None) -> dict | None:
    if answer is None:
        return None
    return {"category": answer.get("category"), "subtype": answer.get("subtype"), "strain": answer.get("strain"),
            "product_line": answer.get("product_line"), "variant": answer.get("size")}


def score_case(case: dict, answer: dict | None) -> dict:
    first = case.get("first_pass") or {}
    agent = answer_fields(answer)
    unsure = answer is None or answer.get("confidence") == "unsure"
    applied = first if unsure else agent
    ok = lambda vals, got: norm(got) in {norm(v) for v in vals}  # noqa: E731
    fields = {}
    for f, vals in wanted(case).items():
        row = {"want": vals, "first_pass": first.get(f), "agent": agent.get(f) if agent else None,
               "ok_first": ok(vals, first.get(f)), "ok_agent": agent is not None and ok(vals, agent.get(f)),
               "ok_applied": ok(vals, applied.get(f))}
        if "today" in case:
            row["ok_today"] = ok(vals, case["today"].get(f))
        fields[f] = row
    return {"id": case["id"], "slice": case.get("slice", "flagged"), "file": case.get("_file"),
            "confidence": answer.get("confidence") if answer else None,
            "evidence": answer.get("evidence") if answer else None, "fields": fields,
            "all_first": all(r["ok_first"] for r in fields.values()),
            "all_applied": all(r["ok_applied"] for r in fields.values())}


def summarize(scored: list[dict]) -> dict:
    """Counts over scored cases: fields right for each source, listings fully right,
    fixes and breaks against the first pass, and accuracy by stated confidence."""
    s = Counter()
    per_field = {f: Counter() for f in FIELDS}
    by_conf = {c: Counter() for c in ("sure", "likely", "unsure", None)}
    for sc in scored:
        s["listings"] += 1
        s["unsure"] += sc["confidence"] == "unsure"
        s["unanswered"] += sc["confidence"] is None
        s["all_first"] += sc["all_first"]
        s["all_applied"] += sc["all_applied"]
        for f, r in sc["fields"].items():
            s["fields"] += 1
            for k in ("ok_first", "ok_agent", "ok_applied", "ok_today"):
                if k in r:
                    s[k] += r[k]
                    per_field[f][k] += r[k]
            s["has_today"] += "ok_today" in r
            per_field[f]["n"] += 1
            s["fixed"] += r["ok_applied"] and not r["ok_first"]
            s["broke"] += r["ok_first"] and not r["ok_applied"]
            by_conf[sc["confidence"]]["n"] += 1
            by_conf[sc["confidence"]]["ok"] += r["ok_agent"]
    return {"totals": dict(s), "per_field": {f: dict(c) for f, c in per_field.items() if c["n"]},
            "by_confidence": {str(k): dict(c) for k, c in by_conf.items() if c["n"]}}


def as_listing(case: dict, store_ids: dict[str, str]) -> dict:
    l = case["listing"]
    return {"id": case["id"], "brand": l.get("brand") or "", "name": l.get("name") or "",
            "category": l.get("category"), "raw_category": l.get("raw_category"), "size_field": l.get("size_field"),
            "price_cents": l.get("price_cents"), "description": l.get("description"), "url": l.get("url"),
            "store": store_ids.get(case.get("store") or "", ""), "first_pass": case.get("first_pass"),
            "p": case.get("p")}


def run_model(model: str, cases: list[dict], base: review_tools.ReviewContext, *, workers: int, effort: str,
              web: bool, fallbacks: bool, client=None) -> list[review_agent.BatchResult]:
    store_ids = {slug: sid for sid, slug in base.stores.items()}
    listings = [as_listing(c, store_ids) for c in cases]
    groups = review_agent.batches(listings)
    client = client or review_agent.make_client()
    results, done = [], 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(review_agent.review_batch, base.for_batch({l["id"]: l for l in g}), g, model,
                               client=client, effort=effort, web=web, fallbacks=fallbacks): g for g in groups}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            done += 1
            print(f"  [{done}/{len(groups)}] {model} {','.join(r.listing_ids)[:70]:<70} "
                  f"{r.seconds:5.0f}s ${r.cost_usd:.3f}{'  ERROR ' + r.error if r.error else ''}", flush=True)
    return results


def pct(a, b) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "-"


def report(model: str, summary: dict, results: list[review_agent.BatchResult], scored: list[dict]) -> str:
    t = summary["totals"]
    cost = sum(r.cost_usd for r in results)
    secs = sum(r.seconds for r in results)
    usage = Counter()
    for r in results:
        usage.update(r.usage)
    tools = Counter()
    for r in results:
        tools.update(r.tool_calls)
    served = sorted({m for r in results for m in r.served_by})
    errors = [f"{','.join(r.listing_ids)}: {r.error}" for r in results if r.error]
    lines = [f"## {model}", "",
             f"- listings: {t.get('listings', 0)} in {len(results)} conversations; unsure {t.get('unsure', 0)}, "
             f"unanswered {t.get('unanswered', 0)}",
             f"- fields right: first pass {pct(t.get('ok_first', 0), t.get('fields', 0))}, agent "
             f"{pct(t.get('ok_agent', 0), t.get('fields', 0))}, applied (unsure keeps the first pass) "
             f"{pct(t.get('ok_applied', 0), t.get('fields', 0))}"
             + (f", today's path {pct(t.get('ok_today', 0), t.get('has_today', 0))} (of its fields)"
                if t.get("has_today") else ""),
             f"- listings fully right: first pass {pct(t.get('all_first', 0), t.get('listings', 0))}, applied "
             f"{pct(t.get('all_applied', 0), t.get('listings', 0))}",
             f"- fields fixed {t.get('fixed', 0)}, broken {t.get('broke', 0)} (against the first pass)",
             f"- cost ${cost:.2f} (${cost / max(t.get('listings', 1), 1):.3f} a listing); "
             f"{secs / max(len(results), 1):.0f}s a conversation; tokens in {usage['input_tokens']:,}, "
             f"cache read {usage['cache_read_tokens']:,}, cache write {usage['cache_write_tokens']:,}, "
             f"out {usage['output_tokens']:,}; web searches {usage['web_searches']}, fetches {usage['web_fetches']}",
             f"- tool calls: {dict(tools.most_common())}", f"- served by: {served}"]
    if errors:
        lines.append(f"- errors: {errors}")
    lines += ["", "| field | n | first pass | agent | applied |", "|---|---|---|---|---|"]
    for f, c in summary["per_field"].items():
        lines.append(f"| {f} | {c['n']} | {c.get('ok_first', 0)} | {c.get('ok_agent', 0)} | {c.get('ok_applied', 0)} |")
    lines += ["", "| stated confidence | fields | right |", "|---|---|---|"]
    for k, c in summary["by_confidence"].items():
        lines.append(f"| {k} | {c['n']} | {pct(c.get('ok', 0), c['n'])} |")
    by_slice = Counter((sc["slice"], sc["all_first"], sc["all_applied"]) for sc in scored)
    lines += ["", "By slice (listings fully right, first pass -> applied): " + ", ".join(
        f"{sl}: {sum(n for (s2, a, b), n in by_slice.items() if s2 == sl and a)} -> "
        f"{sum(n for (s2, a, b), n in by_slice.items() if s2 == sl and b)} of "
        f"{sum(n for (s2, a, b), n in by_slice.items() if s2 == sl)}" for sl in sorted({k[0] for k in by_slice}))]
    misses = [sc for sc in scored if not sc["all_applied"]]
    if misses:
        lines += ["", "Wrong after review:", ""]
        for sc in misses:
            bad = {f: (r["agent"] if sc["confidence"] not in (None, "unsure") else r["first_pass"], r["want"])
                   for f, r in sc["fields"].items() if not r["ok_applied"]}
            lines.append(f"- {sc['id']} ({sc['confidence']}): "
                         + "; ".join(f"{f} {got!r}, want {want}" for f, (got, want) in bad.items()))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=review_agent.DEFAULT_MODEL)
    ap.add_argument("--cases", default="evals/review/cases/*.json")
    ap.add_argument("--ids", default="", help="comma-separated case ids to run (default all)")
    ap.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--no-web", action="store_true", help="leave out web search and fetch")
    ap.add_argument("--no-fallbacks", action="store_true", help="no server-side fallback model on a refusal")
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args()

    cases = load_cases([args.cases])
    if args.ids:
        keep = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in keep]
    if args.limit:
        cases = cases[:args.limit]
    print(f"{len(cases)} cases; loading catalogs, listings and prices...", flush=True)
    t = time.time()
    base = review_tools.ReviewContext.from_db(sorted({c["listing"]["brand"] for c in cases}))
    print(f"  {len(base.catalogs)} catalogs, {len(base.listings)} listings of these brands "
          f"({time.time() - t:.0f}s)", flush=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sections = [f"# Review agent on {len(cases)} queued listings ({time.strftime('%Y-%m-%d')})", "",
                f"effort {args.effort}; web {'off' if args.no_web else 'on'}; cases {args.cases}", ""]
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"\n{model}:", flush=True)
        results = run_model(model, cases, base, workers=args.workers, effort=args.effort, web=not args.no_web,
                            fallbacks=not args.no_fallbacks)
        answers = {i: a for r in results for i, a in r.answers.items()}
        scored = [score_case(c, answers.get(c["id"])) for c in cases]
        summary = summarize(scored)
        (out / f"{model}.json").write_text(json.dumps(
            {"model": model, "effort": args.effort, "summary": summary, "scored": scored,
             "batches": [r.to_dict() for r in results]}, indent=1, ensure_ascii=False, default=str))
        section = report(model, summary, results, scored)
        print("\n" + section, flush=True)
        sections += [section, ""]
    (out / "summary.md").write_text("\n".join(sections))
    print(f"\nwrote {out}/summary.md", flush=True)


if __name__ == "__main__":
    main()
