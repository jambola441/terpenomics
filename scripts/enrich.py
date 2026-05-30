"""
enrich.py — Post-scrape enrichment: subtype + strain + product line.

classify_by_token gives a cheap rule-based subtype hint.  A single Haiku call
then confirms/corrects the subtype and extracts strain and product_line.
Results are cached in data/enrich_cache.json keyed by "dispensary_slug:sku".

    from enrich import enrich
    rows = enrich(rows)
"""

import json
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper_common import normalize_variant  # noqa: E402

_DATA_DIR = Path(__file__).parent.parent / "data"


# ---------------------------------------------------------------------------
# Token patterns — cheap subtype hint
# ---------------------------------------------------------------------------

_TOKENS: dict[str, OrderedDict] = {
    "vaporizers": OrderedDict([
        ("all-in-one", re.compile(r"\ball[\s-]*in[\s-]*one\b|\baio\b|\bdisposable\b", re.I)),
        ("cart",       re.compile(r"\b(cart|510|cartridge|preload|reload)\b", re.I)),
        ("pod",        re.compile(r"\bpod\b", re.I)),
        ("battery",    re.compile(r"\b(battery|starter\s*kit)\b", re.I)),
    ]),
    "edible": OrderedDict([
        ("beverage",  re.compile(r"\b(beverage|sparkling\s+water|tea\s+sachet|drink)\b", re.I)),
        ("gummy",     re.compile(r"\bgumm|\bchews?\b|\brope\b|\bpearl\b", re.I)),
        ("chocolate", re.compile(r"\bchocolate\b|\bbar\b", re.I)),
        ("tablet",    re.compile(r"\btablet\b|\bprotab\b|\bcapsule\b|\bpill\b|\bbean\b|\bdrop\b", re.I)),
    ]),
    "preroll": OrderedDict([
        ("infused", re.compile(r"\b(infused|kief|diamond|hash\s*hole|live\s*resin|live\s*rosin)\b", re.I)),
        ("pack",    re.compile(r"\bpack\b|\bvariety\b|\b\d+\s*pk\b", re.I)),
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

_CATEGORY_DEFAULTS: dict[str, str | None] = {
    "vaporizers":  None,
    "edible":      None,
    "preroll":     "single",
    "flower":      "flower",
    "concentrate": None,
    "tinctures":   "tincture",
    "topical":     "topical",
    "merch":       "merch",
    "other":       "other",
}


def classify_by_token(category: str, name: str) -> str | None:
    patterns = _TOKENS.get(category)
    if not patterns:
        return None
    for subtype, pat in patterns.items():
        if pat.search(name):
            return subtype
    return None


def _hint_subtype(row: dict) -> str | None:
    """Token match first, then category default. May return None."""
    sub = classify_by_token(row.get("category", ""), row.get("name", ""))
    if sub:
        return sub
    return _CATEGORY_DEFAULTS.get(row.get("category", ""))


# ---------------------------------------------------------------------------
# Cache — one file per dispensary: data/enrich_cache/{slug}.json
# ---------------------------------------------------------------------------

_CACHE_DIR = _DATA_DIR / "enrich_cache"


def _cache_key(row: dict) -> str | None:
    sku = (row.get("sku") or "").strip()
    return sku if sku else None


def _slug_for_rows(rows: list[dict]) -> str | None:
    for row in rows:
        slug = (row.get("dispensary_slug") or "").strip()
        if slug:
            return slug
    return None


def _load_cache(slug: str) -> dict:
    path = _CACHE_DIR / f"{slug}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict, slug: str) -> None:
    _CACHE_DIR.mkdir(exist_ok=True)
    (_CACHE_DIR / f"{slug}.json").write_text(
        json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Haiku
# ---------------------------------------------------------------------------

def _load_api_key() -> str | None:
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return key
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


_ENRICH_PROMPT = """\
You enrich cannabis dispensary product listings with five fields.

For each listing:
  category     — top-level product category (correct hint_category if wrong)
  subtype      — the product sub-format within its category
  strain       — the specific strain, flavor, or differentiator for this product
  product_line — the named sub-brand or product series, if one exists (else null)
  variant      — the canonical size/dose for this product (see rules below)

Allowed categories: flower, preroll, vaporizers, edible, concentrate, tinctures, topical, merch, other
hint_category is the scraper's best guess — confirm it if correct, override if not.
Common misclassifications to fix:
- "Live Rosin AIO", "Live Resin Cart", anything with vape/cart/pod/aio/disposable in name → vaporizers (even if hint says concentrate)
- "Pills", "Tablets", "Capsules" → edible
- Accessories (grinders, papers, lighters) → merch

Subtypes by category:
  vaporizers:  cart, all-in-one, pod, battery, other
  edible:      gummy, chocolate, beverage, tablet, other
  concentrate: rosin, resin, hash, rso, other
  preroll:     single, infused, pack
  flower:      flower, smalls, preground, infused
  tinctures:   tincture
  topical:     topical
  merch:       merch
  other:       other

hint_subtype is a rule-based guess — confirm it if correct, override if not.

For variant:
- hint_variant is the scraper's best guess — confirm it if correct, fix it if not
- Edibles: TOTAL package THC in mg (e.g. 10pk × 10mg/piece = "100mg")
  Use description to find per-piece dose and pack count when hint is wrong
  Physical weight (grams) is wrong for edibles unless it's a whole-food product with no THC dose
- Flower / preroll / concentrate / vaporizers: weight or volume in compact form ("3.5g", "1g", "0.5g")
  Fluid ounces (fl oz, oz liquid) must NOT be converted to grams — return as-is (e.g. "12oz")
- Tinctures: volume if stated, else total mg
- Merch / accessories with no meaningful size: return ""
- If genuinely unsure, return hint_variant unchanged

For strain:
- Strip brand name and pure format words (Cart, Pre-Roll, Tincture, Gummy, Disposable, etc.) and size/qty
- Normalize to Title Case; crosses use " x " separator
- Preserve cannabis abbreviations in all-caps: OG, AK, RSO, CBD, THC, BC, NYC, LA
- Do not correct other spellings — keep source spelling (e.g. "Tie Die", "Perisimmon")
- If Sativa/Indica/Hybrid is the only differentiator left, use it as strain
- Return null only for merch/accessories with no cannabis identifier

For product_line:
- A word/phrase the brand uses to group a family of products (e.g. "Releaf", "Protab", "22's")
- Return null if no named line exists within the brand

Reply ONLY with a JSON array, no explanation, no markdown fences:
[{"id": "0", "category": "edible", "subtype": "gummy", "strain": "Watermelon Lemonade", "product_line": null, "variant": "100mg"}, ...]
"""


_HAIKU_COST = {
    "input":        0.80  / 1_000_000,
    "output":       4.00  / 1_000_000,
    "cache_write":  1.00  / 1_000_000,
    "cache_read":   0.08  / 1_000_000,
}


def _call_batch(
    client,
    chunk: list[tuple[int, dict]],
    batch_num: int,
    total_batches: int,
    hint_subtypes: list[str | None],
    print_lock,
) -> tuple[dict, dict]:
    """Call Haiku for one batch. Returns (items_by_local_id, usage_dict). Thread-safe."""
    payload = [
        {
            "id":            str(i),
            "hint_category": r.get("category", ""),
            "brand":         r.get("brand", ""),
            "name":          r.get("name", ""),
            "description":   r.get("description", ""),
            "hint_subtype":  hint_subtypes[orig_idx],
            "hint_variant":  r.get("variant", ""),
        }
        for i, (orig_idx, r) in enumerate(chunk)
    ]

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=[{"type": "text", "text": _ENRICH_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        items = {item["id"]: item for item in json.loads(text)}
        u = resp.usage
        batch_usage = {
            "input_tokens":       u.input_tokens,
            "output_tokens":      u.output_tokens,
            "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
            "cache_read_tokens":  getattr(u, "cache_read_input_tokens", 0) or 0,
        }
    except Exception as exc:
        with print_lock:
            print(f"  [model error] batch {batch_num}: {exc}", file=sys.stderr)
        items = {}
        batch_usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}

    with print_lock:
        print(f"    enrich batch {batch_num}/{total_batches} done")

    return items, batch_usage


def _run_haiku(
    pending: list[tuple[int, dict]],
    cache: dict,
    slug: str,
    categories: list[str | None],
    subtypes: list[str | None],
    strains: list[str | None],
    product_lines: list[str | None],
    variants: list[str | None],
    batch_size: int = 50,
) -> dict:
    import anthropic
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    api_key = _load_api_key()
    if not api_key:
        print("  [warn] ANTHROPIC_API_KEY not set", file=sys.stderr)
        return {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}

    client = anthropic.Anthropic(api_key=api_key)
    batches = [pending[s : s + batch_size] for s in range(0, len(pending), batch_size)]
    total_batches = len(batches)
    print_lock = threading.Lock()
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}

    # Fire all batches concurrently; each thread is pure (no shared writes).
    # Results are applied by the main thread after all futures complete.
    max_workers = min(total_batches, 8)
    batch_results: dict[int, tuple[dict, dict]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                _call_batch, client, chunk, i + 1, total_batches, subtypes, print_lock
            ): (i, chunk)
            for i, chunk in enumerate(batches)
        }
        for future in as_completed(future_to_idx):
            i, chunk = future_to_idx[future]
            items, batch_usage = future.result()
            batch_results[i] = (chunk, items)
            for k in usage:
                usage[k] += batch_usage[k]

    # Apply results in batch order, then save cache once.
    for i in sorted(batch_results):
        chunk, items = batch_results[i]
        for local_id, (orig_idx, row) in enumerate(chunk):
            item         = items.get(str(local_id), {})
            category     = item.get("category") or categories[orig_idx] or row.get("category", "other")
            sub          = item.get("subtype") or subtypes[orig_idx] or "other"
            strain       = item.get("strain")
            product_line = item.get("product_line")
            variant      = item.get("variant") if "variant" in item else row.get("variant", "")

            categories[orig_idx]    = category
            subtypes[orig_idx]      = sub
            strains[orig_idx]       = strain
            product_lines[orig_idx] = product_line
            variants[orig_idx]      = variant

            key = _cache_key(row)
            if key:
                cache[key] = {
                    "category": category, "subtype": sub, "strain": strain,
                    "product_line": product_line, "variant": variant,
                }

    _save_cache(cache, slug)
    return usage


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich(rows: list[dict], batch_size: int = 50, no_enrich: bool = False) -> dict:
    """Enrich every row in place: corrects category, adds subtype/strain/product_line/variant.

    Returns a token usage dict: {input_tokens, output_tokens, cache_write_tokens,
    cache_read_tokens, cost_usd}. All zeros when everything was cached.
    """
    if no_enrich:
        for row in rows:
            row.setdefault("subtype", "other")
            row.setdefault("strain", "")
            row.setdefault("product_line", None)
        return {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0}

    slug = _slug_for_rows(rows) or "unknown"
    cache = _load_cache(slug)

    categories:    list[str | None] = []
    subtypes:      list[str | None] = []
    strains:       list[str | None] = []
    product_lines: list[str | None] = []
    variants:      list[str | None] = []
    pending:       list[tuple[int, dict]] = []

    for i, row in enumerate(rows):
        key = _cache_key(row)
        entry = cache.get(key) if key else None
        # Re-enrich if not cached or cache pre-dates variant/category fields
        if entry and "variant" in entry and "category" in entry:
            categories.append(entry.get("category"))
            subtypes.append(entry.get("subtype"))
            strains.append(entry.get("strain"))
            product_lines.append(entry.get("product_line"))
            variants.append(entry.get("variant"))
        else:
            categories.append(None)
            subtypes.append(_hint_subtype(row))
            strains.append(None)
            product_lines.append(None)
            variants.append(None)
            pending.append((i, row))

    cached_count = len(rows) - len(pending)
    if pending:
        print(f"  enrich: {cached_count} cached, {len(pending)} → Haiku")
        usage = _run_haiku(pending, cache, slug, categories, subtypes, strains, product_lines, variants, batch_size)
    else:
        print(f"  enrich: {cached_count} cached, 0 → Haiku")
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}

    for i, row in enumerate(rows):
        row["category"]     = categories[i] or row.get("category", "other")
        row["subtype"]      = subtypes[i] or "other"
        row["strain"]       = strains[i] or ""
        row["product_line"] = product_lines[i] or None
        v = variants[i] if variants[i] is not None else row.get("variant", "")
        row["variant"]      = normalize_variant(v) if v else v

    cost = (
        usage["input_tokens"]         * _HAIKU_COST["input"]
        + usage["output_tokens"]      * _HAIKU_COST["output"]
        + usage["cache_write_tokens"] * _HAIKU_COST["cache_write"]
        + usage["cache_read_tokens"]  * _HAIKU_COST["cache_read"]
    )
    usage["cost_usd"] = round(cost, 4)
    return usage


def write_usage(usage: dict, csv_path: str) -> None:
    """Write usage dict as a sidecar .usage.json next to the CSV."""
    path = Path(csv_path).with_suffix(".usage.json")
    path.write_text(json.dumps(usage, indent=2))
