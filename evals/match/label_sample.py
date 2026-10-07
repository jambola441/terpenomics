#!/usr/bin/env python3
"""
label_sample.py — Labels the matcher test set (cases/sample.json) with the review agent
in its match mode: for each listing, the catalog entry it is, the product with its size
missing from the catalog, or none. The agent never sees what the matcher decided (its
other-stores tool hides recorded matches), so the labels are its own reading.

Labels are written into the file with the model that gave them; cases/spot_check.md
lists 30 for a person to check before the set is used.

    DB_VIA_HTTP=1 python evals/match/label_sample.py --model claude-sonnet-5-5
    DB_VIA_HTTP=1 python evals/match/label_sample.py --limit 10          # a smoke run

Needs ANTHROPIC_API_KEY and the database.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
import catalog_store  # noqa: E402
import review_agent  # noqa: E402
import review_tools  # noqa: E402

SAMPLE = HERE / "cases" / "sample.json"
SPOT_CHECK = HERE / "cases" / "spot_check.md"


def kind(label: dict | None) -> str:
    if not label:
        return "unlabelled"
    if label.get("confidence") == "unsure":
        return "unsure"
    return "entry" if label.get("entry_id") else "product" if label.get("product_entry_id") else "none"


def entry_text(entries: dict, eid: str | None) -> str:
    e = entries.get(eid or "")
    return f"{e.get('name')} [{e.get('variant') or 'no size'}]" if e else "—"


def spot_check(cases: list[dict], catalogs: dict, n: int = 30, seed: int = 7) -> str:
    """n labelled cases for a person: a third where the label and the matcher's last
    decision disagree, the rest spread over the label kinds."""
    rng = random.Random(seed)
    labelled = [c for c in cases if kind(c.get("label")) in ("entry", "product", "none")]
    differs = [c for c in labelled if (c["label"].get("entry_id") or None) != (c["recorded"].get("entry_id") or None)]
    picked = rng.sample(differs, min(len(differs), n // 3))
    rest = [c for c in labelled if c not in picked]
    rng.shuffle(rest)
    by_kind = {k: [c for c in rest if kind(c["label"]) == k] for k in ("entry", "none", "product")}
    while len(picked) < n and any(by_kind.values()):
        for k, pool in by_kind.items():
            if pool and len(picked) < n:
                picked.append(pool.pop())
    lines = ["# Matcher test set: spot check", "",
             "For each, is the label right? The matcher's last decision is shown for comparison only.", ""]
    for i, c in enumerate(picked[:n], 1):
        entries = {e.get("id"): e for e in (catalogs.get(catalog_store.brand_key(c["brand"])) or {}).get("entries", [])}
        l, lab = c["listing"], c["label"]
        lines += [f"{i}. **{c['brand']}**: {l['name']} (size field {l.get('size_field')!r}, "
                  f"{'$%.2f' % (l['price_cents'] / 100) if l.get('price_cents') else 'no price'}; {c['store']})",
                  f"   - label ({kind(lab)}, {lab.get('confidence')}): "
                  f"{entry_text(entries, lab.get('entry_id') or lab.get('product_entry_id'))}: {lab.get('evidence')}",
                  f"   - matcher: {c['recorded'].get('method')} {c['recorded'].get('p')}: "
                  f"{entry_text(entries, c['recorded'].get('entry_id'))}",
                  f"   - case {c['id']}", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=review_agent.DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=0, help="label only the first N unlabelled cases")
    ap.add_argument("--relabel", action="store_true", help="label cases that already have a label too")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--effort", default="medium")
    args = ap.parse_args()

    data = json.loads(SAMPLE.read_text())
    cases = data["cases"]
    todo = [c for c in cases if args.relabel or not c.get("label")]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} of {len(cases)} cases to label with {args.model}", flush=True)
    base = review_tools.ReviewContext.from_db(sorted({c["listing"]["brand"] for c in cases}))
    base.blind_matches = True
    store_ids = {slug: sid for sid, slug in base.stores.items()}
    by_id = {c["id"]: c for c in cases}
    listings = [{"id": c["id"], **{k: c["listing"].get(k) for k in
                                    ("brand", "name", "category", "size_field", "price_cents", "description", "url")},
                 "store": store_ids.get(c["store"], "")} for c in todo]
    groups = review_agent.batches(listings, by_store=False)
    client = review_agent.make_client()
    lock, cost, errors, done = threading.Lock(), 0.0, [], 0
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(review_agent.review_batch, base.for_batch({l["id"]: l for l in g}), g, args.model,
                               client=client, effort=args.effort, task="match", trace=False) for g in groups]
        for fut in as_completed(futures):
            r = fut.result()
            with lock:
                done += 1
                cost += r.cost_usd
                if r.error:
                    errors.append(f"{','.join(r.listing_ids)}: {r.error}")
                for lid, answer in r.answers.items():
                    by_id[lid]["label"] = {**answer, "by": args.model, "on": time.strftime("%Y-%m-%d")}
                SAMPLE.write_text(json.dumps(data, indent=1, ensure_ascii=False))   # keep what is done so far
                print(f"  [{done}/{len(groups)}] {r.seconds:4.0f}s ${r.cost_usd:.3f} "
                      f"{','.join(r.listing_ids)[:60]}{'  ERROR ' + r.error if r.error else ''}", flush=True)
    SPOT_CHECK.write_text(spot_check(cases, base.catalogs))
    print(f"\nlabels: {dict(Counter(kind(c.get('label')) for c in cases))}; cost ${cost:.2f}; "
          f"{time.time() - started:.0f}s; errors {len(errors)}", flush=True)
    for e in errors:
        print("  " + e)
    print(f"wrote {SAMPLE} and {SPOT_CHECK}")


if __name__ == "__main__":
    main()
