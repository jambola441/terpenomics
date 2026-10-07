#!/usr/bin/env python3
"""
review_cli.py — The review agent's tools (review_tools.py) from a shell, so a Claude Code
session or subagent can do the review agent's job without the API: it reads the same
instructions (review_agent.system_prompt) and calls the same read-only tools.

Loading the catalogs, listings and prices takes about a minute, so it is done once:

    DB_VIA_HTTP=1 python scripts/review_cli.py build CONTEXT.pkl BRAND [BRAND ...]

Each batch of listings under review is a directory holding batch.json:

    {"context": "CONTEXT.pkl", "task": "labels", "listings": [{"id": ..., "brand": ..., ...}]}

and the tools are called against it, one call per command, arguments as JSON (or "-"
to read them from stdin, which spares quoting an apostrophe):

    python scripts/review_cli.py BATCH_DIR search_catalog '{"brand": "Grön", "query": "baja blaze"}'
    python scripts/review_cli.py BATCH_DIR submit_labels - <<'JSON'
    {"listing_id": "q1", "strain": "Mother's Milk", ...}
    JSON

The submit tools write BATCH_DIR/answers.json; proposed catalog fixes go to
BATCH_DIR/proposals.json. Nothing touches the database.
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_tools  # noqa: E402


def build(out: str, brands: list[str]) -> None:
    ctx = review_tools.ReviewContext.from_db(brands)
    Path(out).write_bytes(pickle.dumps(ctx))
    print(f"saved {len(ctx.catalogs)} catalogs, {len(ctx.listings)} listings to {out}")


def call(batch_dir: str, tool: str, args_json: str) -> str:
    d = Path(batch_dir)
    batch = json.loads((d / "batch.json").read_text())
    ctx = pickle.loads(Path(batch["context"]).read_bytes())
    ctx = ctx.for_batch({l["id"]: l for l in batch["listings"]})
    ctx.blind_matches = batch.get("task") == "match"
    answers_path, proposals_path = d / "answers.json", d / "proposals.json"
    if answers_path.exists():
        ctx.answers.update(json.loads(answers_path.read_text()))
    if proposals_path.exists():
        ctx.proposals.extend(json.loads(proposals_path.read_text()))
    other_task_tool = {"labels": "submit_match", "match": "submit_labels"}.get(batch.get("task", "labels"))
    if tool == other_task_tool:
        return json.dumps({"error": f"{tool} is not a tool of this task"})
    if args_json == "-":
        args_json = sys.stdin.read()
    try:
        args = json.loads(args_json or "{}")
    except ValueError as e:
        return json.dumps({"error": f"arguments are not JSON: {e}"})
    out = review_tools.run_tool(ctx, tool, args)
    answers_path.write_text(json.dumps(ctx.answers, indent=1, ensure_ascii=False))
    proposals_path.write_text(json.dumps(ctx.proposals, indent=1, ensure_ascii=False))
    return out


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3:])
        return
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    print(call(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else "{}"))


if __name__ == "__main__":
    main()
