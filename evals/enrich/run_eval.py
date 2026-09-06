#!/usr/bin/env python3
"""
run_eval.py — Compare enrichment models on a suite of representative cases.

Each file in cases/ is one eval *type*:
  - per-item types (categorization, variant_fix, common_error): every case has an
    `expect` dict; a case passes when every expected field matches.
  - identity_cluster: every case is a GROUP of listings for the same product; it
    passes when all members converge to the same identity tuple (expect_same), and
    optionally match `canonical`.

Usage
-----
  python evals/enrich/run_eval.py --models haiku,deepseek
  python evals/enrich/run_eval.py --models haiku,mimo,deepseek,gemini-flash,gpt-mini
  python evals/enrich/run_eval.py --models haiku --cases cases/categorization.json

Outputs land in evals/enrich/results/: <model>.json, comparison.md, summary.md.
Model enrichment is run with brand_examples={} so results reflect the model alone
(no DB-dependent nudge). The eval dispensary cache is cleared each run so the CURRENT
prompts are always exercised.
"""

import argparse
import copy
import glob
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import enrich  # noqa: E402

FIELDS = ["category", "subtype", "strain", "product_line", "variant"]
EVAL_SLUG = "__enrich_eval"


def norm(v) -> str:
    return (v if v is not None else "").strip().lower()


def load_suites(patterns: list[str]) -> list[dict]:
    paths: list[str] = []
    for pat in patterns:
        p = pat if Path(pat).is_absolute() else str(HERE / pat)
        paths.extend(sorted(glob.glob(p)))
    suites = []
    for path in paths:
        suite = json.loads(Path(path).read_text())
        suite["_file"] = Path(path).name
        suites.append(suite)
    return suites


def suite_rows(suite: dict) -> list[tuple[str, dict]]:
    """Flatten a suite into (row_key, input_dict) pairs."""
    rows = []
    for case in suite["cases"]:
        if suite["eval_type"] == "identity_cluster":
            for i, m in enumerate(case["members"]):
                rows.append((f"{case['id']}#{i}", m))
        else:
            rows.append((case["id"], case["input"]))
    return rows


def model_cfg_slug(model: str) -> str:
    return (enrich.MODELS.get(model) or {}).get("api_model", "?")


def clear_eval_cache(model: str) -> None:
    for name in (f"{EVAL_SLUG}.json", f"{EVAL_SLUG}.{model}.json"):
        p = enrich._CACHE_DIR / name
        if p.exists():
            p.unlink()


def enrich_with_model(model: str, suites: list[dict], brand_nudge: bool = False,
                      catalog_hint: bool = False) -> tuple[dict, dict, float, str | None]:
    """Enrich every row across all suites with one model. Returns (key->enriched, usage, secs, error)."""
    rows, keys = [], []
    for suite in suites:
        for key, inp in suite_rows(suite):
            r = copy.deepcopy(inp)
            r["sku"] = key
            r["dispensary_slug"] = EVAL_SLUG
            rows.append(r)
            keys.append(key)

    # brand_examples={} isolates the model; None + ENRICH_BRAND_NUDGE=1 loads the brand
    # index from the DB (scoped to the batch's brands) so the consistency nudge is in play.
    if brand_nudge:
        os.environ["ENRICH_BRAND_NUDGE"] = "1"
        brand_examples = None
    else:
        brand_examples = {}

    clear_eval_cache(model)
    err = None
    t = time.time()
    try:
        usage = enrich.enrich(rows, model=model, brand_examples=brand_examples,
                              catalog_hints=catalog_hint)
    except Exception as e:  # registry guard, client build, etc.
        usage, err = {}, f"{type(e).__name__}: {e}"
    secs = time.time() - t
    clear_eval_cache(model)

    # A run that burned no tokens never reached the model — a bad OpenRouter slug or a
    # missing key. Without this the fallback hints still score (~10%), which reads like a
    # terrible model rather than a broken config. Fail loudly instead.
    if err is None and rows and not any(
        usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens")
    ):
        err = (f"no tokens used — the model was never called. Check the api_model slug "
               f"({model_cfg_slug(model)!r}) and the provider API key.")

    enriched = {k: {f: r.get(f) for f in FIELDS} for k, r in zip(keys, rows)}
    return enriched, usage, secs, err


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def score_item_suite(suite: dict, enriched: dict) -> list[dict]:
    out = []
    for case in suite["cases"]:
        got = enriched.get(case["id"], {})
        exp = case.get("expect", {})
        fails = [f for f, want in exp.items() if not norm(got.get(f)) == norm(want)]
        out.append({"id": case["id"], "got": got, "expect": exp, "passed": not fails, "fails": fails})
    return out


def score_cluster_suite(suite: dict, enriched: dict) -> list[dict]:
    out = []
    for case in suite["cases"]:
        members = [enriched.get(f"{case['id']}#{i}", {}) for i in range(len(case["members"]))]
        split = {}
        for f in case["expect_same"]:
            vals = {norm(m.get(f)) for m in members}
            if len(vals) > 1:
                split[f] = sorted({(m.get(f) if m.get(f) is not None else "") for m in members}, key=str)
        converged = not split
        canon = case.get("canonical", {})
        canon_fails = []
        if converged and canon:
            rep = members[0]
            canon_fails = [f for f, want in canon.items() if not norm(rep.get(f)) == norm(want)]
        out.append({
            "id": case["id"], "converged": converged, "split": split,
            "canonical_match": converged and not canon_fails, "canon_fails": canon_fails,
            "members": members,
        })
    return out


def score(suite: dict, enriched: dict) -> list[dict]:
    if suite["eval_type"] == "identity_cluster":
        return score_cluster_suite(suite, enriched)
    return score_item_suite(suite, enriched)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def fmt_expect(exp: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in exp.items())


def write_comparison(results: list[dict], suites: list[dict], out_dir: Path) -> None:
    models = [r["model"] for r in results]
    lines = ["# Enrich model comparison\n",
             f"Models: {', '.join(models)}\n"]
    for suite in suites:
        lines.append(f"\n## {suite['eval_type']} — {suite['_file']}\n")
        lines.append(f"_{suite['description']}_\n")
        if suite["eval_type"] == "identity_cluster":
            header = "| group | canonical | " + " | ".join(models) + " |"
            lines += [header, "|" + "---|" * (2 + len(models))]
            for ci, case in enumerate(suite["cases"]):
                canon = fmt_expect(case.get("canonical", {}))
                cells = []
                for r in results:
                    sc = r["scores"][suite["_file"]][ci]
                    if not sc["converged"]:
                        bad = "; ".join(f"{f}=[{'|'.join(map(str, vs))}]" for f, vs in sc["split"].items())
                        cells.append(f"✗ split: {bad}")
                    elif sc["canonical_match"]:
                        cells.append("✓ converged + canonical")
                    else:
                        cells.append(f"~ converged, off-canonical ({', '.join(sc['canon_fails'])})")
                lines.append(f"| {case['id']} | {canon} | " + " | ".join(cells) + " |")
        else:
            header = "| case | expected | " + " | ".join(models) + " |"
            lines += [header, "|" + "---|" * (2 + len(models))]
            for ci, case in enumerate(suite["cases"]):
                cells = []
                for r in results:
                    sc = r["scores"][suite["_file"]][ci]
                    if sc["passed"]:
                        cells.append("✓")
                    else:
                        got = sc["got"]
                        detail = "; ".join(f"{f}: {got.get(f)!r}→want {sc['expect'][f]!r}" for f in sc["fails"])
                        cells.append(f"✗ {detail}")
                lines.append(f"| {case['id']} | {fmt_expect(case['expect'])} | " + " | ".join(cells) + " |")
    (out_dir / "comparison.md").write_text("\n".join(lines) + "\n")


def write_summary(results: list[dict], suites: list[dict], out_dir: Path,
                  brand_nudge: bool = False, catalog_hint: bool = False) -> None:
    lines = ["# Enrich model eval — summary\n",
             f"brand-examples nudge: **{'on' if brand_nudge else 'off'}** "
             "(off = model only; on = DB brand index in play)\n",
             # Recorded because a hinted run and a baseline run are otherwise
             # indistinguishable in this file, and the two do not score the same.
             f"catalog hint: **{'on' if catalog_hint else 'off'}** "
             "(on = the brand's catalog is in the pass-B prompt)\n",
             "Score = passing cases / total (clusters: groups converged + canonical-matched).\n",
             "| model | api_model | time s | in tok | out tok | cost $ | "
             + " | ".join(s["eval_type"] for s in suites) + " | note |",
             "|" + "---|" * (7 + len(suites))]
    for r in results:
        u = r["usage"]
        per = []
        for s in suites:
            sc = r["scores"][s["_file"]]
            if s["eval_type"] == "identity_cluster":
                conv = sum(x["converged"] for x in sc)
                canon = sum(x["canonical_match"] for x in sc)
                per.append(f"{canon}/{len(sc)} ({conv} conv)")
            else:
                per.append(f"{sum(x['passed'] for x in sc)}/{len(sc)}")
        note = r["error"] or ("no tokens — bad slug?" if not (u.get("input_tokens") or u.get("output_tokens")) else "")
        lines.append(
            f"| {r['model']} | {enrich.MODELS[r['model']]['api_model']} | {r['secs']:.0f} | "
            f"{u.get('input_tokens',0):,} | {u.get('output_tokens',0):,} | {u.get('cost_usd',0):.4f} | "
            + " | ".join(per) + f" | {note} |"
        )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare enrichment models across the eval suite")
    ap.add_argument("--models", default="haiku", help="comma-separated model ids from MODELS")
    ap.add_argument("--cases", default="cases/*.json", help="glob(s) of case files, comma-separated")
    ap.add_argument("--brand-nudge", action="store_true",
                    help="enable the DB brand-examples nudge (default off, model-only)")
    ap.add_argument("--catalog-hint", action="store_true",
                    help="put the brand's real product list (data/catalogs/) in the "
                         "pass-B prompt (default off, so a model comparison measures "
                         "the model rather than the catalog)")
    args = ap.parse_args()

    suites = load_suites([c.strip() for c in args.cases.split(",")])
    if not suites:
        print("No case files matched.", file=sys.stderr)
        sys.exit(1)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)

    total_cases = sum(len(s["cases"]) for s in suites)
    print(f"Suites: {', '.join(s['_file'] for s in suites)}  ({total_cases} cases)"
          f"  brand_nudge={'on' if args.brand_nudge else 'off'}"
          f"  catalog_hint={'on' if args.catalog_hint else 'off'}")
    results = []
    for m in models:
        if m not in enrich.MODELS:
            print(f"  [skip] unknown model {m!r}")
            continue
        print(f"\n== {m} ({enrich.MODELS[m]['api_model']}) ==")
        enriched, usage, secs, err = enrich_with_model(
            m, suites, brand_nudge=args.brand_nudge, catalog_hint=args.catalog_hint)
        scores = {s["_file"]: score(s, enriched) for s in suites}
        results.append({"model": m, "usage": usage, "secs": secs, "error": err,
                        "enriched": enriched, "scores": scores})
        (out_dir / f"{m}.json").write_text(json.dumps(
            {"model": m, "api_model": enrich.MODELS[m]["api_model"], "secs": secs,
             "usage": usage, "error": err, "scores": scores}, indent=2))
        print(f"   {secs:.0f}s  cost=${usage.get('cost_usd',0):.4f}  err={err}")

    if results:
        write_comparison(results, suites, out_dir)
        write_summary(results, suites, out_dir, brand_nudge=args.brand_nudge,
                      catalog_hint=args.catalog_hint)
        print(f"\nWrote {out_dir}/comparison.md and summary.md")


if __name__ == "__main__":
    main()
