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
from canonical import canonicalize, find_format_category  # noqa: E402

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
        ("diamonds", re.compile(r"\bdiamonds?\b", re.I)),
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


def _hint_category(row: dict) -> str:
    """The scraper's category, overridden by a curated device/format token when one
    is present ("Select Briq V2" is a vape, whatever the source category said).
    Used both as the hint sent to the model and as the value the model's answer is
    overruled by, so category, subtype and variant are all settled consistently."""
    forced = find_format_category(row.get("brand", ""), row.get("name", ""))
    return forced or row.get("category", "")


def _hint_subtype(row: dict) -> str | None:
    """Token match first, then category default. May return None."""
    category = _hint_category(row)
    sub = classify_by_token(category, row.get("name", ""))
    if sub:
        return sub
    return _CATEGORY_DEFAULTS.get(category)


# ---------------------------------------------------------------------------
# Cache — one file per dispensary: data/enrich_cache/{slug}.json
# ---------------------------------------------------------------------------

_CACHE_DIR = _DATA_DIR / "enrich_cache"

# Bump when a prompt, rail, or token rule changes in a way that should invalidate
# previously cached answers. Cache entries stamped with a different version are
# re-enriched instead of trusted, so a taxonomy change reaches old rows without
# anyone hand-deleting cache files.
#   1 — baseline
#   2 — 'diamonds' concentrate subtype; beverages dosed in mg not volume; topical
#       scent names are strains; version suffixes ("2.0") kept in strain
#   3 — data/format_tokens.json settles the category for brand device names
#   4 — beverage variant rule scoped so it stops pulling subtype toward 'beverage';
#       pack multiply-out scoped to mg doses so it stops overriding weight hints
_ENRICH_VERSION = 4


def _cache_key(row: dict) -> str | None:
    """Key on sku + scraped variant: platforms reuse one SKU across weight tiers,
    and a bare-sku key would let tiers overwrite each other's cache entry. Uses the
    scraper's variant (pre-enrichment), which is stable across runs for a given row."""
    sku = (row.get("sku") or "").strip()
    if not sku:
        return None
    return f"{sku}|{(row.get('variant') or '').strip()}"


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

def _load_key(env_name: str) -> str | None:
    """Read a key from the environment, falling back to the repo-root .env file."""
    if key := os.environ.get(env_name):
        return key
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(f"{env_name}="):
                return line.split("=", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# Model registry — select with enrich(..., model="<id>")
#
#   provider "anthropic"  → native SDK, prompt caching on the system prompt
#   provider "openrouter" → OpenAI-compatible gateway (Claude, MiMo, Gemini, ...)
#                           needs OPENROUTER_API_KEY and `pip install openai`
#
# cost is USD per token. Cache costs only apply to the anthropic provider.
# Find exact OpenRouter slugs + live pricing at https://openrouter.ai/models
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "haiku"

# Per-request defaults; a model entry may override "timeout"/"max_tokens".
_DEFAULT_TIMEOUT = 90      # seconds — a stalled batch fails fast instead of hanging
_DEFAULT_MAX_TOKENS = 4096

MODELS: dict[str, dict] = {
    "haiku": {
        "provider":  "anthropic",
        "api_model": "claude-haiku-4-5-20251001",
        "cost": {"input": 0.80 / 1e6, "output": 4.00 / 1e6,
                 "cache_write": 1.00 / 1e6, "cache_read": 0.08 / 1e6},
    },
    # ---- comparison models (via OpenRouter) ----
    # TODO: confirm the exact slug + pricing from openrouter.ai/models.
    "mimo": {
        "provider":  "openrouter",
        "api_model": "xiaomi/mimo-v2.5",        # non-reasoning MiMo on OpenRouter
        # OpenRouter pricing. cache_read is tracked only on the anthropic path,
        # so the $0.0036/M cached-input rate doesn't apply to this OpenAI-style call.
        "cost": {"input": 0.14 / 1e6, "output": 0.28 / 1e6},
        # MiMo returned empty/truncated JSON on 50-item batches, nulling most fields.
        # Use a SMALL batch_size (fewer items per call → shorter, complete output)
        # and keep max_tokens generous so a full batch's JSON is never cut off.
        # Firm timeout so a stalled batch fails fast instead of hanging the run.
        "batch_size": 15, "timeout": 120, "max_tokens": 8192,
    },
    "deepseek": {
        "provider":  "openrouter",
        "api_model": "deepseek/deepseek-v4-flash",   # <-- verify slug on OpenRouter
        "cost": {"input": 0.09 / 1e6, "output": 0.18 / 1e6},
        # Truncated/nulled the extract pass at the default 50-item batch. Small
        # batch + generous max_tokens keeps each batch's JSON complete (same fix
        # that stabilized mimo).
        "batch_size": 15, "max_tokens": 8192,
    },
}


def _make_client(model_cfg: dict):
    """Build the SDK client for a model's provider. Returns None if its key is missing."""
    if model_cfg["provider"] == "anthropic":
        import anthropic
        key = _load_key("ANTHROPIC_API_KEY")
        if not key:
            print("  [warn] ANTHROPIC_API_KEY not set", file=sys.stderr)
            return None
        return anthropic.Anthropic(api_key=key)
    # openrouter — OpenAI-compatible. Cap SDK retries so a slow batch can't
    # silently multiply its wait (default is 2 retries with backoff).
    from openai import OpenAI
    key = _load_key("OPENROUTER_API_KEY")
    if not key:
        print("  [warn] OPENROUTER_API_KEY not set", file=sys.stderr)
        return None
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, max_retries=1)


# ---------------------------------------------------------------------------
# Rails — the only answers each enum field is allowed to take. Code validates
# every model response against these; anything off-list snaps to a hint/default.
# ---------------------------------------------------------------------------

CATEGORIES = ["flower", "preroll", "vaporizers", "edible", "concentrate",
              "tinctures", "topical", "merch", "other"]

SUBTYPES: dict[str, list[str]] = {
    "vaporizers":  ["cart", "all-in-one", "pod", "battery", "other"],
    "edible":      ["gummy", "chocolate", "beverage", "tablet", "other"],
    "concentrate": ["diamonds", "rosin", "resin", "hash", "rso", "other"],
    "preroll":     ["single", "infused", "pack"],
    "flower":      ["flower", "smalls", "preground", "infused"],
    "tinctures":   ["tincture"],
    "topical":     ["topical"],
    "merch":       ["merch"],
    "other":       ["other"],
}

_CATEGORY_LIST = ", ".join(CATEGORIES)
_SUBTYPE_LINES = "\n".join(f"  {c}: {', '.join(s)}" for c, s in SUBTYPES.items())

# ---------------------------------------------------------------------------
# Prompts — one targeted prompt per pass. The classification pass has two
# variants: a "trust the hints" prompt for rows the rule engine could tag, and
# a "decide from scratch" prompt for rows with no reliable sub-format hint.
# ---------------------------------------------------------------------------

_CLASSIFY_BODY = f"""\
category — choose EXACTLY one of: {_CATEGORY_LIST}
  Override hint_category only when the name clearly contradicts it:
  - vape / cart / pod / aio / disposable in the name → vaporizers (even if hint says concentrate)
  - pills / tablets / capsules → edible
  - grinders / papers / lighters / apparel → merch

subtype — choose EXACTLY one from the chosen category's list:
{_SUBTYPE_LINES}

variant — the canonical size/dose, in compact form:
  - edible: TOTAL package THC in mg (10pk × 10mg/piece = "100mg"); grams are wrong unless the
    item has no THC dose or the quantity is at least 0.5g, in which case it must be reported as grams. 
    Use the description for per-piece dose and pack count. Non standard reporting like "halfgram" 
    should be reported as their standard equivalent. A per-piece mg DOSE written next to a pack
    count MUST be multiplied out ("20MG x 2PK" = "40mg", "5mg 20pk" = "100mg") — reporting the
    per-piece dose alone is wrong. This multiply-out rule is for mg doses only: for a
    flower/preroll/vape WEIGHT, prefer hint_variant when it disagrees with your own per-unit
    math, since source names misplace decimals ("5 x .05g" with hint_variant "2.5g" → "2.5g").
    This applies to a drinkable edible too: its variant is the THC dose in mg, never the
    liquid volume — a 12oz can holding 5mg THC has variant "5mg", not "12oz" and not "355ml".
    Fall back to the volume only when no dose appears in the name or description. (This is a
    rule about VARIANT only — it says nothing about which subtype to choose.)
  - flower / preroll / concentrate / vaporizers: weight ("3.5g", "1g", "0.5g").
  - tinctures: total mg ("1000mg") — never converted to grams.
  - merch / no meaningful size: ""

Reply ONLY with a JSON array, no prose, no markdown fences:
[{{"id": "0", "category": "edible", "subtype": "gummy", "variant": "100mg"}}, ...]"""

_CLASSIFY_PROMPT_HINTED = f"""\
You classify a cannabis dispensary product into three fields: category, subtype, variant.
Each item includes hint_category (scraper guess), hint_subtype (rule-based guess) and
hint_variant. These hints are usually correct — TRUST them and confirm them; only override
when the name or description clearly contradicts the hint. If unsure about variant, return
hint_variant unchanged.

{_CLASSIFY_BODY}"""

_CLASSIFY_PROMPT_FRESH = f"""\
You classify a cannabis dispensary product into three fields: category, subtype, variant.
No reliable sub-format hint is available for these items, so DECIDE from scratch: read the
name and description carefully. hint_category and hint_variant may be present but are weak —
treat them as loose suggestions, not answers.

{_CLASSIFY_BODY}"""

_EXTRACT_PROMPT = """\
You extract two fields from a cannabis product whose category is already known: strain and
product_line.

strain — the specific strain, flavor, or differentiator. A FLAVOR IS A STRAIN: for edibles,
beverages, vapes, and any product without a cannabis strain name, the flavor name is the strain
(e.g. "Limeade", "Watermelon Lemonade", "Blue Razz", "Wild Cherry"). Always extract it — never
return null just because the product is a drink, gummy, or other flavored item.
- Strip the brand name, pure format words (Cart, Pre-Roll, Tincture, Gummy, Disposable, etc.)
  and any size/quantity.
- The strain is ONLY the strain/flavor. NEVER fold the product_line / sub-brand into it — if you
  put a value in product_line, it must NOT also appear in strain
  ("Night Cap Elderberry Sage" → strain "Elderberry Sage", product_line "Night Cap").
- Strip cannabinoid ratios and potency from the strain: ratios like "1:2:3", "5:10:15mg",
  "THC:CBD:CBN", and mg/percent amounts are NOT part of the strain
  ("Elderberry Sage 1:2:3 THC:CBD:CBN" → "Elderberry Sage").
- Normalize to Title Case; crosses use " x " as the separator.
- KEEP version/edition suffixes — they distinguish real products ("Creamsicle x Rainbow
  Beltz 2.0" keeps the "2.0"). Only pure size/format words are stripped.
- Preserve cannabis abbreviations in all-caps: OG, AK, RSO, CBD, THC, BC, NYC, LA.
- Do NOT correct other spellings — keep the source spelling (e.g. "Tie Die", "Perisimmon").
- If Sativa / Indica / Hybrid is the only differentiator left, use that as the strain.
- Topicals DO have strains: a balm's scent or blend name is its strain ("Ayrloom Balm - Revive"
  → "Revive"). Treat it exactly like a flavor.
- Return null ONLY when category is merch, or nothing but the brand and a format/size
  word remains (no flavor, scent, strain, or other differentiator at all).

product_line — a word/phrase the brand uses to group a family of products (e.g. "Releaf",
"Protab", "22's"). Assign one ONLY when the product name actually contains that line's text;
otherwise return null. Never infer a line just because the brand has one.

Some items carry known_strains / known_product_lines — values ALREADY recorded for this brand
in our catalog. Use them to stay consistent:
- If the product is clearly the SAME strain as one of known_strains, REUSE that exact spelling.
  This overrides "keep source spelling": it consolidates typos/variants ("Blu Dreem" → "Blue Dream").
- They are a shortlist, not a constraint — if none genuinely matches, extract the strain normally.
- For product_line, every value in known_product_lines already appears in this product's name —
  reuse the matching one's exact spelling; if the list is absent/empty, return null.

Reply ONLY with a JSON array, no prose, no markdown fences:
[{"id": "0", "strain": "Watermelon Lemonade", "product_line": null}, ...]"""


_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}


# ---------------------------------------------------------------------------
# Validators — clamp every model answer to a legal value (rails enforcement).
# ---------------------------------------------------------------------------

def _valid_category(answer: str | None, hint: str | None) -> str:
    a = (answer or "").strip().lower()
    if a in CATEGORIES:
        return a
    h = (hint or "").strip().lower()
    return h if h in CATEGORIES else "other"


def _valid_subtype(answer: str | None, category: str, hint: str | None) -> str:
    allowed = SUBTYPES.get(category, ["other"])
    for cand in (answer, hint, _CATEGORY_DEFAULTS.get(category)):
        c = (cand or "").strip().lower()
        if c in allowed:
            return c
    return "other" if "other" in allowed else allowed[0]


# ---------------------------------------------------------------------------
# Model call — one targeted call (one pass, one batch). Thread-safe.
# ---------------------------------------------------------------------------

def _call_llm(
    client, provider: str, api_model: str, system_prompt: str,
    payload: list[dict], timeout: float, max_tokens: int,
    label: str, print_lock,
) -> tuple[dict | None, dict]:
    """Returns (items_by_local_id, usage_dict). items is None on any failure —
    callers must treat those rows as unanswered (fall back to hints, do NOT cache)."""
    try:
        if provider == "anthropic":
            resp = client.messages.create(
                model=api_model, max_tokens=max_tokens, timeout=timeout,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            text = (resp.content[0].text or "").strip()
            u = resp.usage
            usage = {
                "input_tokens":       u.input_tokens,
                "output_tokens":      u.output_tokens,
                "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                "cache_read_tokens":  getattr(u, "cache_read_input_tokens", 0) or 0,
            }
        else:  # openrouter — OpenAI-compatible chat completions
            resp = client.chat.completions.create(
                model=api_model, max_tokens=max_tokens, timeout=timeout,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": json.dumps(payload)},
                ],
            )
            text = (resp.choices[0].message.content or "").strip()
            u = resp.usage
            usage = {
                "input_tokens":       u.prompt_tokens,
                "output_tokens":      u.completion_tokens,
                "cache_write_tokens": 0,
                "cache_read_tokens":  0,
            }
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        items = {item["id"]: item for item in json.loads(text)}
    except Exception as exc:
        with print_lock:
            print(f"  [model error] {label}: {exc}", file=sys.stderr)
        items, usage = None, dict(_ZERO_USAGE)

    with print_lock:
        print(f"    {label} done")
    return items, usage


def _chunks(items: list, n: int) -> list[list]:
    return [items[s : s + n] for s in range(0, len(items), n)]


def _load_brand_examples(brands: set[str] | None = None) -> dict[str, dict]:
    """brand(lowercased) -> {"strains": [...], "product_lines": [...]} from the DB listings
    table — strains/lines already recorded for each brand across every dispensary.

    `brands` (lowercased) scopes the query to just the brands in the batch; None loads all.
    Best-effort: returns {} when DATABASE_URL is unset or the query fails, so enrichment
    still runs (just without the consistency nudge) anywhere the DB isn't reachable.
    """
    db_url = _load_key("DATABASE_URL")
    if not db_url:
        return {}
    if brands is not None and not brands:
        return {}
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        try:
            cur = conn.cursor()
            sql = ("SELECT scraped_brand, strain, product_line FROM listings "
                   "WHERE scraped_brand IS NOT NULL AND strain IS NOT NULL")
            params: tuple = ()
            if brands is not None:
                sql += " AND lower(scraped_brand) = ANY(%s)"
                params = (list(brands),)
            cur.execute(sql, params)
            idx: dict[str, dict] = {}
            for brand, strain, pline in cur.fetchall():
                e = idx.setdefault(brand.strip().lower(), {"strains": set(), "product_lines": set()})
                if strain:
                    e["strains"].add(strain)
                if pline:
                    e["product_lines"].add(pline)
        finally:
            conn.close()
        out = {b: {"strains": sorted(v["strains"]), "product_lines": sorted(v["product_lines"])}
               for b, v in idx.items()}
        print(f"    brand examples: {len(out)} brand(s) loaded from DB")
        return out
    except Exception as exc:
        print(f"  [warn] brand-examples lookup skipped: {exc}", file=sys.stderr)
        return {}


def _nearest(name: str, pool: list[str], n: int = 5) -> list[str]:
    """Up to n catalog strains most similar to the product name (the shortlist to nudge with)."""
    import difflib
    if len(pool) <= n:
        return list(pool)
    return difflib.get_close_matches(name, pool, n=n, cutoff=0.0)


def _squash(s: str) -> str:
    """Lowercase and drop all non-alphanumerics, so 'Night Cap' / 'Nightcap' / 'night-cap' match."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _run_enrich(
    pending: list[tuple[int, dict]],
    cache: dict,
    slug: str,
    categories: list[str | None],
    subtypes: list[str | None],
    strains: list[str | None],
    product_lines: list[str | None],
    variants: list[str | None],
    model_cfg: dict,
    batch_size: int = 50,
    brand_examples: dict[str, dict] | None = None,
) -> dict:
    """Field-decomposed enrichment in two dependent passes:
      A) classify category+subtype+variant (hinted rows and fresh rows get different prompts)
      B) extract strain+product_line, conditioned on the category decided in A, and nudged
         toward known_strains/known_product_lines already recorded for the brand
    Every answer is clamped to a legal value by the validators above.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    client = _make_client(model_cfg)
    if client is None:
        return dict(_ZERO_USAGE)

    # Rows whose batch errored or whose id the model dropped (truncation). They
    # still get hint/default values for this run's output, but are excluded from
    # the cache so the next run retries them instead of freezing the fallback.
    failed_rows: set[int] = set()

    provider, api_model = model_cfg["provider"], model_cfg["api_model"]
    timeout    = model_cfg.get("timeout", _DEFAULT_TIMEOUT)
    max_tokens = model_cfg.get("max_tokens", _DEFAULT_MAX_TOKENS)
    batch_size = model_cfg.get("batch_size", batch_size)  # per-model override (small for flaky models)
    print_lock = threading.Lock()
    usage = dict(_ZERO_USAGE)

    def run_phase(tasks: list[tuple]) -> None:
        """tasks = [(label, system_prompt, payload, on_result), ...]; runs them concurrently."""
        if not tasks:
            return
        with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as ex:
            futs = {
                ex.submit(_call_llm, client, provider, api_model, sp, pl, timeout, max_tokens, label, print_lock): onr
                for (label, sp, pl, onr) in tasks
            }
            for fut in as_completed(futs):
                items, u = fut.result()
                for k in usage:
                    usage[k] += u[k]
                futs[fut](items)

    # ---- Pass A: classification, split by hint availability ----
    hinted   = [(oi, r) for (oi, r) in pending if _hint_subtype(r) is not None]
    fresh    = [(oi, r) for (oi, r) in pending if _hint_subtype(r) is None]

    def classify_payload(chunk):
        return [
            {
                "id":            str(i),
                "hint_category": _hint_category(r),
                "brand":         r.get("brand", ""),
                "name":          r.get("name", ""),
                "description":   r.get("description", ""),
                "hint_subtype":  _hint_subtype(r),
                "hint_variant":  r.get("variant", ""),
            }
            for i, (oi, r) in enumerate(chunk)
        ]

    def classify_applier(chunk):
        def on_result(items):
            for local_id, (oi, row) in enumerate(chunk):
                it = (items or {}).get(str(local_id))
                if it is None:
                    failed_rows.add(oi)
                    it = {}
                # A curated device token is a string fact about the name, so it wins
                # over the model; _valid_subtype then snaps the subtype into that
                # category's rail.
                forced = find_format_category(row.get("brand", ""), row.get("name", ""))
                cat = forced or _valid_category(it.get("category"), row.get("category"))
                categories[oi] = cat
                subtypes[oi]   = _valid_subtype(it.get("subtype"), cat, _hint_subtype(row))
                v = it.get("variant")
                variants[oi]   = v if v is not None else row.get("variant", "")
        return on_result

    classify_tasks = []
    for kind, bucket, prompt in (("hinted", hinted, _CLASSIFY_PROMPT_HINTED),
                                 ("fresh",  fresh,  _CLASSIFY_PROMPT_FRESH)):
        for bi, chunk in enumerate(_chunks(bucket, batch_size)):
            classify_tasks.append(
                (f"classify[{kind}] {bi + 1}", prompt, classify_payload(chunk), classify_applier(chunk))
            )

    print(f"    pass A: classify {len(pending)} item(s) "
          f"({len(hinted)} hinted, {len(fresh)} fresh) → {api_model}")
    run_phase(classify_tasks)

    # ---- Pass B: extraction, conditioned on the now-known category ----
    # Brand index: known strains/lines already in our catalog, to nudge for consistency.
    # OFF by default (the product_line vocabulary still needs canonicalizing). It only
    # auto-loads from the DB when ENRICH_BRAND_NUDGE=1; callers may also inject a dict.
    if brand_examples is None:
        if os.environ.get("ENRICH_BRAND_NUDGE") == "1":
            batch_brands = {(r.get("brand") or "").strip().lower() for (_, r) in pending}
            batch_brands.discard("")
            brand_examples = _load_brand_examples(batch_brands)
        else:
            brand_examples = {}

    def extract_applier(chunk):
        def on_result(items):
            for local_id, (oi, row) in enumerate(chunk):
                it = (items or {}).get(str(local_id))
                if it is None:
                    failed_rows.add(oi)
                    it = {}
                strains[oi]       = it.get("strain")
                product_lines[oi] = it.get("product_line")
        return on_result

    def extract_payload_item(i, oi, r):
        item = {
            "id":          str(i),
            "brand":       r.get("brand", ""),
            "name":        r.get("name", ""),
            "category":    categories[oi] or r.get("category", "other"),
            "description": r.get("description", ""),
        }
        ex = brand_examples.get((r.get("brand") or "").strip().lower())
        if ex:
            name = r.get("name", "")
            known_s = _nearest(name, ex["strains"])
            # product_line nudge: surface lines that appear in the name, matched on a
            # normalized form (case/space/punctuation-insensitive) so a known "Night Cap"
            # still matches a listing that writes it "Nightcap" / "night-cap".
            name_sq = _squash(name)
            known_pl = [pl for pl in ex["product_lines"] if _squash(pl) and _squash(pl) in name_sq][:5]
            if known_s:
                item["known_strains"] = known_s
            if known_pl:
                item["known_product_lines"] = known_pl
        return item

    extract_tasks = []
    for bi, chunk in enumerate(_chunks(pending, batch_size)):
        payload = [extract_payload_item(i, oi, r) for i, (oi, r) in enumerate(chunk)]
        extract_tasks.append((f"extract {bi + 1}", _EXTRACT_PROMPT, payload, extract_applier(chunk)))

    print(f"    pass B: extract strain/product_line for {len(pending)} item(s) → {api_model}")
    run_phase(extract_tasks)

    # ---- Write cache once, both passes applied ----
    # Rows in failed_rows carry fallback values, not model answers — leaving them
    # out of the cache means the next run re-enriches them instead of trusting junk.
    if failed_rows:
        print(f"  [warn] {len(failed_rows)} row(s) not cached (model error/truncation); "
              f"will retry next run", file=sys.stderr)
    for (oi, row) in pending:
        if oi in failed_rows:
            continue
        key = _cache_key(row)
        if key:
            cache[key] = {
                "v": _ENRICH_VERSION,
                "category": categories[oi], "subtype": subtypes[oi], "strain": strains[oi],
                "product_line": product_lines[oi], "variant": variants[oi],
            }

    _save_cache(cache, slug)
    return usage


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich(rows: list[dict], batch_size: int = 50, no_enrich: bool = False,
           model: str = DEFAULT_MODEL, brand_examples: dict[str, dict] | None = None) -> dict:
    """Enrich every row in place: corrects category, adds subtype/strain/product_line/variant.

    `model` selects an entry from MODELS (default "haiku"). Each non-default model
    gets its own cache file so a comparison run never reads another model's answers.

    `brand_examples` injects a brand→{strains, product_lines} index to nudge strain/line
    consistency. The nudge is OFF by default; when brand_examples is None it auto-loads from
    the DB only if ENRICH_BRAND_NUDGE=1. Pass an explicit dict to force-use it, or {} to disable.

    Returns a token usage dict: {input_tokens, output_tokens, cache_write_tokens,
    cache_read_tokens, cost_usd}. All zeros when everything was cached.
    """
    if no_enrich:
        for row in rows:
            row.setdefault("subtype", "other")
            row.setdefault("strain", "")
            row.setdefault("product_line", None)
        return {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0}

    if model not in MODELS:
        raise ValueError(f"unknown model '{model}'; choose from {', '.join(MODELS)}")
    model_cfg = MODELS[model]

    base_slug = _slug_for_rows(rows) or "unknown"
    # Keep the default model on the original slug (preserves existing cache);
    # isolate every other model so comparisons don't cross-contaminate.
    slug = base_slug if model == DEFAULT_MODEL else f"{base_slug}.{model}"
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
        # Re-enrich if not cached, if the cache pre-dates the variant/category
        # fields, or if it was written under an older prompt/taxonomy version.
        if entry and "variant" in entry and "category" in entry \
                and entry.get("v") == _ENRICH_VERSION:
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
        print(f"  enrich: {cached_count} cached, {len(pending)} → {model}")
        usage = _run_enrich(pending, cache, slug, categories, subtypes, strains, product_lines, variants, model_cfg, batch_size, brand_examples)
    else:
        print(f"  enrich: {cached_count} cached, 0 → {model}")
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}

    for i, row in enumerate(rows):
        row["category"]     = categories[i] or row.get("category", "other")
        row["subtype"]      = subtypes[i] or "other"
        row["strain"]       = strains[i] or ""
        row["product_line"] = product_lines[i] or None
        v = variants[i] if variants[i] is not None else row.get("variant", "")
        # Pass the settled category: an edible/tincture dose must not be run through
        # the weight conversions (1000mg is a dose, not 1g).
        row["variant"]      = normalize_variant(v, row["category"]) if v else v

    # Deterministic canonicalization last: curated product lines and strain aliases
    # override the model, so identity is consistent across dispensaries and runs.
    # Applied to cached rows too — adding a map entry takes effect without re-enriching.
    canon_stats = canonicalize(rows)
    if any(canon_stats.values()):
        print("  canonical: " + ", ".join(f"{k}={v}" for k, v in canon_stats.items() if v))

    c = model_cfg["cost"]
    cost = (
        usage["input_tokens"]         * c.get("input", 0)
        + usage["output_tokens"]      * c.get("output", 0)
        + usage["cache_write_tokens"] * c.get("cache_write", 0)
        + usage["cache_read_tokens"]  * c.get("cache_read", 0)
    )
    usage["cost_usd"] = round(cost, 4)
    return usage


def write_usage(usage: dict, csv_path: str) -> None:
    """Write usage dict as a sidecar .usage.json next to the CSV."""
    path = Path(csv_path).with_suffix(".usage.json")
    path.write_text(json.dumps(usage, indent=2))
