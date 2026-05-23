#!/usr/bin/env python3
"""
classify_subtype.py — Three-pass subtype classifier for listing CSVs.

Pass 1: Regex token matching on the 'name' column
Pass 2: Brand lookup table (for brand=format brands like Camino, Wyld)
Pass 3: Haiku model fallback for residual ambiguous listings

Usage:
  python scripts/classify_subtype.py                    # both prototype CSVs
  python scripts/classify_subtype.py path/to/file.csv   # specific file(s)
  python scripts/classify_subtype.py --dry-run          # skip model calls
  python scripts/classify_subtype.py --out out.csv      # write classified CSV
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path


# ---------------------------------------------------------------------------
# Pass 1 — Token patterns
# ---------------------------------------------------------------------------
# Each entry is an OrderedDict: subtype → compiled regex.
# First match wins. Patterns are checked against the cleaned 'name' field.

TOKENS: dict[str, OrderedDict] = {
    "vaporizers": OrderedDict([
        ("all-in-one", re.compile(r"\ball[\s-]*in[\s-]*one\b|\bail-in-one\b|\baio\b|\bdisposable\b", re.I)),
        ("cart",       re.compile(r"\b(cart|510|cartridge|preload|reload)\b", re.I)),
        ("pod",        re.compile(r"\bpod\b", re.I)),
        ("battery",    re.compile(r"\b(battery|starter\s*kit)\b", re.I)),
    ]),
    "edible": OrderedDict([
        # beverage first — catches "Beverage Enhancer Drops" before tablet sees "drop"
        ("beverage",  re.compile(r"\b(beverage|sparkling\s+water|tea\s+sachet|drink)\b", re.I)),
        ("gummy",     re.compile(r"\bgumm|\bchews?\b|\brope\b|\bpearl\b", re.I)),
        ("chocolate", re.compile(r"\bchocolate\b|\bbar\b", re.I)),
        ("tablet",    re.compile(r"\btablet\b|\bprotab\b|\bcapsule\b|\bpill\b|\bbean\b|\bdrop\b", re.I)),
    ]),
    "preroll": OrderedDict([
        ("infused", re.compile(r"\b(infused|kief|diamond|hash\s*hole|live\s*resin|live\s*rosin)\b", re.I)),
        ("pack",    re.compile(r"\bpack\b|\bvariety\b", re.I)),
    ]),
    "flower": OrderedDict([
        ("smalls",    re.compile(r"\bsmalls?\b|\bsmall\s+bud", re.I)),
        ("preground", re.compile(r"\bpre-?ground\b|\bground\s+flower\b|\bready\s*-?\s*to\s*-?\s*roll\b", re.I)),
        ("infused",   re.compile(r"\bdiamond\s+infused\b|\binfused\b", re.I)),
    ]),
    "concentrate": OrderedDict([
        ("rosin", re.compile(r"\brosin\b", re.I)),
        ("resin", re.compile(r"\bresin\b", re.I)),
        ("hash",  re.compile(r"\bhash\b", re.I)),
        ("rso",   re.compile(r"\brso\b", re.I)),
    ]),
}

# Default subtype when no token matches.
# None means "no confident default — send to model".
CATEGORY_DEFAULTS: dict[str, str | None] = {
    "vaporizers":  None,        # bare "Brand | Strain" is ambiguous
    "edible":      None,        # same
    "preroll":     "single",    # non-infused, non-pack = standard single
    "flower":      "flower",    # standard whole buds
    "concentrate": None,        # ambiguous without extraction token
    "tinctures":   "tincture",
    "topical":     "topical",
    "merch":       "merch",
    "other":       "other",
}


# ---------------------------------------------------------------------------
# Pass 2 — Brand lookup
# ---------------------------------------------------------------------------
# Per-category dicts mapping brand_lowercase → subtype.
# None value = explicitly ambiguous (skip to model).

BRAND_DEFAULTS: dict[str, dict[str, str | None]] = {
    "edible": {
        "camino":                   "gummy",
        "wyld":                     "gummy",
        "lost farm":                "gummy",
        "good tide":                "gummy",
        "rythm":                    "gummy",
        "papa & barkley":           "gummy",
        "heavy hitters":            "gummy",
        "highland goat":            "gummy",
        "finca":                    "gummy",
        "ruby":                     "gummy",
        "off hours":                "gummy",
        "wana":                     "gummy",
        "eaton botanicals":         "gummy",
        "mfny":                     "gummy",
        "pax":                      "gummy",
        "level":                    "tablet",
        "layup":                    "beverage",
        "weed water":               "beverage",
        "harney brothers cannabis": "beverage",
        "beboe":                    "other",
        "myhi":                     "other",
        "select":                   "tablet",
        "1906":                     "tablet",
        "incredibles":              None,   # makes both gummies and chocolate
    },
}


def _brand_key(brand: str | None) -> str:
    return (brand or "").lower().strip()


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

def classify_by_token(category: str, name: str) -> str | None:
    patterns = TOKENS.get(category)
    if not patterns:
        return None
    for subtype, pat in patterns.items():
        if pat.search(name):
            return subtype
    return None


def classify_by_brand(category: str, brand: str | None) -> str | None:
    """Returns subtype or None. None means ambiguous OR brand not in table."""
    cat_map = BRAND_DEFAULTS.get(category, {})
    key = _brand_key(brand)
    if key not in cat_map:
        return None
    return cat_map[key]  # may itself be None (explicitly ambiguous)


def classify_row(row: dict) -> tuple[str, str]:
    """
    Returns (subtype, method) where method ∈ {token, brand, default, model}.
    subtype = "?" signals the row needs a model call.
    """
    category = row.get("category", "")
    name     = row.get("name", "")
    brand    = row.get("brand", "")

    subtype = classify_by_token(category, name)
    if subtype:
        return subtype, "token"

    subtype = classify_by_brand(category, brand)
    if subtype:
        return subtype, "brand"

    default = CATEGORY_DEFAULTS.get(category)
    if default is not None:
        return default, "default"

    return "?", "model"


# ---------------------------------------------------------------------------
# Pass 3 — Haiku model
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You classify cannabis dispensary product listings into subtypes.
Given a JSON array of listings, return a JSON array of classifications.

Subtypes by category:
  vaporizers:  cart, all-in-one, pod, battery, other
  edible:      gummy, chocolate, beverage, tablet, other
  concentrate: rosin, resin, hash, rso, other

Rules:
- Reply ONLY with a JSON array, no explanation, no markdown fences.
- Each element: {"id": <same id as input>, "subtype": "<subtype>"}
- If genuinely uncertain, use "other".
"""


def _call_haiku(batch: list[dict]) -> dict[str, str]:
    """Send one batch to Haiku. Returns {str(local_id): subtype}."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY") or _load_env_key()
    if not api_key:
        print("  [warn] ANTHROPIC_API_KEY not set — skipping model batch", file=sys.stderr)
        return {}

    client = anthropic.Anthropic(api_key=api_key)
    payload = [
        {"id": str(i), "category": r["category"], "brand": r["brand"], "name": r["name"]}
        for i, r in enumerate(batch)
    ]
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        text = resp.content[0].text.strip()
        results = json.loads(text)
        return {item["id"]: item["subtype"] for item in results}
    except Exception as exc:
        print(f"  [model error] {exc}", file=sys.stderr)
        return {}


def _load_env_key() -> str | None:
    """Fallback: read ANTHROPIC_API_KEY from .env in project root."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    return None


def classify_with_model(
    pending: list[tuple[int, dict]], batch_size: int = 20
) -> dict[int, str]:
    """Classify pending rows in batches. Returns {original_index: subtype}."""
    results: dict[int, str] = {}
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        orig_indices = [idx for idx, _ in chunk]
        rows = [row for _, row in chunk]
        batch_result = _call_haiku(rows)
        for local_id, orig_idx in enumerate(orig_indices):
            results[orig_idx] = batch_result.get(str(local_id), "other")
        print(f"  batches {start//batch_size + 1}/{-(-len(pending)//batch_size)} done")
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(csv_paths: list[str], dry_run: bool, out_path: str | None) -> None:
    # Read all CSVs
    all_rows: list[dict] = []
    for path in csv_paths:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
            all_rows.extend(rows)
            print(f"  {len(rows):4d} rows  {path}")

    print(f"\nTotal: {len(all_rows)} rows\n")

    # Passes 1 + 2
    classified: list[tuple[str, str]] = []
    model_pending: list[tuple[int, dict]] = []

    for i, row in enumerate(all_rows):
        subtype, method = classify_row(row)
        if method == "model":
            model_pending.append((i, row))
        classified.append((subtype, method))

    method_counts = Counter(m for _, m in classified)
    print("Pass 1+2 method breakdown:")
    for method in ("token", "brand", "default", "model"):
        n = method_counts[method]
        print(f"  {method:10s}  {n:4d}  ({n / len(all_rows) * 100:.0f}%)")

    # Pass 3 — model
    if model_pending:
        if dry_run:
            print(f"\n--dry-run: skipping model for {len(model_pending)} rows")
            print("  Sample needing model:")
            for _, row in model_pending[:8]:
                print(f"    [{row.get('category'):14s}] {row.get('brand') or '(no brand)':20s} | {row.get('name')}")
        else:
            print(f"\nPass 3: Haiku ({len(model_pending)} rows, "
                  f"{-(-len(model_pending) // 20)} batch(es))...")
            model_results = classify_with_model(model_pending)
            for orig_idx, subtype in model_results.items():
                classified[orig_idx] = (subtype, "model")

    # Summary
    print(f"\n{'─'*52}")
    print("Subtype distribution:")
    subtype_counts = Counter(s for s, _ in classified)
    for subtype, count in subtype_counts.most_common():
        bar = "█" * (count * 30 // len(all_rows))
        print(f"  {subtype:20s}  {count:4d}  {bar}")

    print("\nBy category:")
    cat_subtypes: dict[str, Counter] = {}
    for row, (subtype, _) in zip(all_rows, classified):
        cat = row.get("category", "?")
        cat_subtypes.setdefault(cat, Counter())[subtype] += 1
    for cat in sorted(cat_subtypes):
        counts = cat_subtypes[cat]
        total = sum(counts.values())
        parts = "  ".join(f"{s}={n}" for s, n in counts.most_common())
        print(f"  {cat:14s} ({total:3d})  {parts}")

    # Residual
    still_unknown = [(row, s, m) for row, (s, m) in zip(all_rows, classified) if s == "?"]
    if still_unknown:
        print(f"\nResidual (still '?'): {len(still_unknown)}")
        for row, _, __ in still_unknown[:10]:
            print(f"  [{row.get('category'):14s}] {row.get('brand') or '':20s} | {row.get('name')}")

    # Write output
    if out_path:
        fields = list(all_rows[0].keys()) + ["subtype", "classify_method"]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row, (subtype, method) in zip(all_rows, classified):
                writer.writerow({**row, "subtype": subtype, "classify_method": method})
        print(f"\nOutput written to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify listing subtypes (3-pass)")
    parser.add_argument("csvs", nargs="*", help="CSV files (default: both prototype CSVs)")
    parser.add_argument("--dry-run", action="store_true", help="Skip Haiku model calls")
    parser.add_argument("--out", default=None, metavar="PATH", help="Write classified CSV here")
    args = parser.parse_args()

    if not args.csvs:
        base = Path(__file__).parent.parent / "prototypes"
        args.csvs = [
            str(base / "travel-agency-scraper" / "travel_agency_listings.csv"),
            str(base / "alleaves-scraper" / "brooklynorganicbuds_listings.csv"),
        ]

    run(args.csvs, dry_run=args.dry_run, out_path=args.out)
