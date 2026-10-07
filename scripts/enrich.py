"""
enrich.py — Post-scrape enrichment: category, subtype, strain, product line, size.

Each row is answered by the cheapest thing that can answer it, in this order:
  1. a human's verified claim (verification.py)                          no model
  2. a category owner that reads the name — merch (enrichers.py)         no model
  3. this store's cache of earlier answers                               no model
  4. Jev picks category and subtype (jev_classify.py); code writes the size where
     the store's figure is unambiguous (stated_size); Jev picks strain and product
     line from the name's phrases (jev_extract.py; ENRICH_JEV_TEXT=0 turns it off).
     Whatever is still open goes to one Haiku call, which sees the rows Jev settled
     as context
  5. rows Jev is unsure of (below ENRICH_JEV_MIN_CONFIDENCE): Haiku's two calls —
     pass A classifies and sizes, pass B extracts strain and product line
ENRICH_CLASSIFIER=llm sends every model-bound row down 5, as before Jev.
A listing that names a catalog product takes the catalog's identity at import
(import_listings.apply_catalog), whatever enrichment wrote.
Answers are cached per store in data/enrich_cache/<slug>.json, or in Postgres with
ENRICH_CACHE=db (enrich_cache_db.py) where there is no persistent disk.

    from enrich import enrich
    usage = enrich(rows)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper_common import normalize_variant  # noqa: E402
from canonical import canonicalize, find_format_category  # noqa: E402
import verification  # noqa: E402
import attributes as attribute_registry  # noqa: E402
import enrichers  # noqa: E402
import taxonomy  # noqa: E402
import catalog_enricher  # noqa: E402
import jev  # noqa: E402
import jev_classify  # noqa: E402
import jev_extract  # noqa: E402

_DATA_DIR = Path(__file__).parent.parent / "data"


# ---------------------------------------------------------------------------
# Token patterns — cheap subtype hint
# ---------------------------------------------------------------------------

# The rule-based subtype tokens live with every other per-category definition,
# in taxonomy.py, so the catalog paths read the same rules.
_TOKENS = taxonomy.SUBTYPE_TOKENS

# Merch identity — size, pack, colour, flavour — used to live here as a block of
# module-level helpers. It moved to MerchEnricher (scripts/enrichers.py) and
# scripts/attributes.py, which is why merch is no longer named in this file
# outside the rails below.
# ---------------------------------------------------------------------------

# Defined in scripts/taxonomy.py, with every other per-category attribute.
_CATEGORY_DEFAULTS: dict[str, str | None] = taxonomy.default_subtypes()


classify_by_token = taxonomy.token_subtype


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
# Pass A description cap  —  MEASURED, LEFT OFF (0)
#
# Pass A (category/subtype) decides mostly from the name's format words, while
# Pass B (strain/product_line) needs the full text for edible pack math, so
# capping Pass A alone looked like a ~25% cost saving. Measured on the gold
# suites it is worth 3-5%, because output tokens are 53% of cost, bill at 5x
# input, and do not shrink when the input does. Accuracy also drops and its
# run-to-run variance grows ~9x at cap=60. Not a good trade — keep it at 0.
#
# Retained as an instrument: gold-set descriptions are pre-truncated at 300
# chars, so that measurement is a floor. Production descriptions are ~4x longer
# and the arithmetic may differ; re-test against real scrape CSVs before
# adopting. Set ENRICH_PASS_A_DESC_CAP=<chars> to A/B it. See evals/enrich/README.md.
# ---------------------------------------------------------------------------

def _pass_a_desc_cap() -> int:
    try:
        return max(0, int(os.environ.get("ENRICH_PASS_A_DESC_CAP", "0")))
    except ValueError:
        return 0


def _cap_desc(text: str, cap: int) -> str:
    """Truncate on a word boundary so a cut never invents a token ('choc' from
    'chocolate') that the classifier could read as a format word."""
    if not cap or len(text) <= cap:
        return text
    cut = text[:cap]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > cap // 2 else cut).rstrip() + "\u2026"


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
#   5 — a format word alone is not a strain ("Milk Chocolate" on a chocolate bar),
#       so lineage is reached when nothing else differentiates
#   6 — merch gets a real identity: form-factor subtypes (cone, paper, grinder,
#       ...), pack/size in variant, and colour or flavour in strain. Before this,
#       every accessory was subtype "merch" with strain and variant blank, so the
#       products VIEW grouped merch on brand alone — 1,514 listings collapsed into
#       223 product rows.
#   7 — merch variant is a composite of size and pack ("1 1/4 33ct"), with width
#       normalised (KS / King Size / Slim KS were splitting one paper three ways).
#       Papers differ by width at a constant count, cones by count at one size, so
#       neither field alone separates both.
#   (no 8) — merch subtypes were widened again (bowl, downstem, and ~180 more rows
#       settled by name tokens) and the merch helpers moved to MerchEnricher, but
#       merch rows now bypass the cache entirely, so their entries are never read.
#       Exactly ONE live row reaches the merch path with a cached answer — a row the
#       scraper called something else that the model moves into merch — and the new
#       `*/Vaporizer` format token settles that one before it gets there. Bumping
#       would re-enrich all 16,031 listings (~$5-6) to fix nothing.
_ENRICH_VERSION = 7


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


def _cache_in_db() -> bool:
    """ENRICH_CACHE=db keeps the cache in Postgres instead of data/enrich_cache/, for
    runs with no persistent disk: a Render cron job, a sandbox (enrich_cache_db.py)."""
    return os.environ.get("ENRICH_CACHE", "").strip().lower() == "db"


def _load_cache(slug: str) -> dict:
    """The store's cache, or {} — never an exception.

    A cache that cannot be parsed (a write cut off by a deploy restarting the worker,
    a full disk) used to raise here, after the whole menu had been scraped, and keep
    raising every day until someone deleted the file. It is set aside instead, so the
    run re-enriches that store once and the evidence is kept for a look.
    """
    if _cache_in_db():
        import enrich_cache_db
        return enrich_cache_db.load(slug)
    path = _CACHE_DIR / f"{slug}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        bad = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        try:
            path.rename(bad)
        except OSError:
            bad = path
        print(f"  [warn] unreadable enrich cache {path.name} ({exc}); moved to {bad.name}, "
              f"starting empty", file=sys.stderr)
        return {}


def _save_cache(cache: dict, slug: str) -> None:
    """Write via a temp file and rename, so a kill mid-write leaves the old cache
    intact rather than a truncated one."""
    if _cache_in_db():
        import enrich_cache_db
        enrich_cache_db.save(cache, slug)
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{slug}.json"
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, path)


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
# cost is USD per token. cache_write/cache_read apply wherever a call reports cache
# tokens — always on the anthropic path, on openrouter only for a model the gateway
# caches by itself — and an entry that gives no rate for them bills them as plain input.
# Find exact OpenRouter slugs + live pricing at https://openrouter.ai/models
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "haiku"

# Per-request defaults; a model entry may override "timeout"/"max_tokens". It may also
# carry "params": extra chat-completions parameters sent on every request to that model
# (openrouter provider only), for a model whose request needs more than the defaults —
# a reasoning model's "reasoning_effort", say. Nothing is sent unless an entry names it.
_DEFAULT_TIMEOUT = 90      # seconds — a stalled batch fails fast instead of hanging
_DEFAULT_MAX_TOKENS = 4096

MODELS: dict[str, dict] = {
    "haiku": {
        "provider":  "anthropic",
        "api_model": "claude-haiku-4-5-20251001",
        "cost": {"input": 0.80 / 1e6, "output": 4.00 / 1e6,
                 "cache_write": 1.00 / 1e6, "cache_read": 0.08 / 1e6},
    },
    # Same model, OpenRouter transport. For environments that have
    # OPENROUTER_API_KEY but no ANTHROPIC_API_KEY. Scores from this entry are
    # comparable to "haiku" on accuracy but NOT on cost: OpenRouter's rate is
    # $1.00/$5.00 per M vs Anthropic's $0.80/$4.00, ~25% higher. There is also
    # nothing to cache-account on this path (no cache_control is sent, and the
    # system prompts sit under the minimum cacheable length anyway).
    "haiku-or": {
        "provider":  "openrouter",
        "api_model": "anthropic/claude-haiku-4.5",
        "cost": {"input": 1.00 / 1e6, "output": 5.00 / 1e6},
    },
    # NOTE: anthropic/claude-haiku-4.5:batch is half price ($0.50/$2.50 per M) and
    # is the SAME weights, so it cannot differ on accuracy — but it is not reachable
    # from here. OpenRouter rejects it on /chat/completions with
    #   "This model is only available through the Batch API. Use /api/beta/batches"
    # so adopting it means submit-poll-retrieve against an async endpoint (24h SLA),
    # not a MODELS entry. Worth doing for a nightly scrape->enrich->import run,
    # where latency is free; it is a plumbing change, not a model choice.
    # ---- comparison models (via OpenRouter) ----
    # TODO: confirm the exact slug + pricing from openrouter.ai/models.
    "mimo": {
        "provider":  "openrouter",
        "api_model": "xiaomi/mimo-v2.5",        # non-reasoning MiMo on OpenRouter
        # OpenRouter pricing. No cache_read rate is given here, so cached input
        # bills as plain input rather than at the $0.0036/M cached-input rate.
        "cost": {"input": 0.14 / 1e6, "output": 0.28 / 1e6},
        # MiMo returned empty/truncated JSON on 50-item batches, nulling most fields.
        # Use a SMALL batch_size (fewer items per call → shorter, complete output)
        # and keep max_tokens generous so a full batch's JSON is never cut off.
        # Firm timeout so a stalled batch fails fast instead of hanging the run.
        "batch_size": 15, "timeout": 120, "max_tokens": 8192,
    },
    # DeepSeek v4 Pro. MEASURED 2026-08-25 on the gold suites: 85.3% vs haiku's
    # 93.2%, i.e. WORSE than its own cheaper sibling deepseek-v4-flash (89.0%), at
    # 9x the cost and 36x the wall clock. Kept only so the result stays reproducible.
    # The dated -0813 pin is worse still (51.1%, $0.41/run) and is not worth an entry.
    "deepseek-pro": {
        "provider":  "openrouter",
        "api_model": "deepseek/deepseek-v4-pro",
        "cost": {"input": 0.556 / 1e6, "output": 1.112 / 1e6},
        "batch_size": 15, "max_tokens": 8192,
    },
    "deepseek": {
        "provider":  "openrouter",
        "api_model": "deepseek/deepseek-v4-flash",   # verified live on OpenRouter 2026-08-25
        "cost": {"input": 0.077 / 1e6, "output": 0.154 / 1e6},   # live catalogue price
        # Truncated/nulled the extract pass at the default 50-item batch. Small
        # batch + generous max_tokens keeps each batch's JSON complete (same fix
        # that stabilized mimo).
        "batch_size": 15, "max_tokens": 8192,
    },
    # OpenAI GPT-6 Luna — a CANDIDATE, not the default. MEASURED 2026-10-06 against
    # haiku-or, all nine case files (302 cases), the production path (--classifier jev),
    # three runs each, interleaved:
    #   cases passed  286.7 (284-290) vs 287.7 (287-289): level. On the llm path, where
    #                 the model answers every row: 273.0 (272-274) vs 279.7 (278-281)
    #   $/run         $0.035 vs $0.086 (Jev is $0.031 of both; the model alone is $0.005
    #                 vs $0.056). s/run 46 vs 51. Failed rows 0 vs 0
    #   stability     rows whose answer changed across the 3 runs, any field: 44 vs 26
    #                 of 333 (product_line 13 vs 0, variant 22 vs 12)
    # Cheaper, not better, and less steady; no request knob fixes that (seed and
    # temperature leave identical requests answering differently). evals/enrich/README.md.
    "luna": {
        "provider":  "openrouter",
        # Pinned; resolves to openai/gpt-6-luna-20260922. Never ~openai/gpt-luna-latest.
        "api_model": "openai/gpt-6-luna",
        # OpenRouter bills this model's prompt cache too — $0.125/M to write, $0.01/M to
        # read — and reports both counts, so both are priced.
        "cost": {"input": 0.10 / 1e6, "output": 0.50 / 1e6,
                 "cache_write": 0.125 / 1e6, "cache_read": 0.01 / 1e6},
        # A reasoning model: its thinking is billed as output (completion_tokens already
        # counts it) and it takes no temperature. Left alone it reasons about as much as
        # "medium" does, ~4x the reasoning tokens of "low" and 1.5-2x the wall clock, for
        # no better score; "low" was picked on the Plug suite (evals/enrich/README.md).
        "params": {"reasoning_effort": "low"},
        # Reasoning counts against max_tokens. The longest 50-row call at "low" used
        # 1,196 of it; the rest is headroom for a long think, and is a cap, not a charge.
        "max_tokens": 8192,
    },
    # NOTE: openai/gpt-6-luna:batch is half price ($0.05/$0.25 per M) and is the SAME
    # weights, but, like the Haiku :batch above, it is not reachable from here: OpenRouter
    # answers a /chat/completions request with 404 "cannot be used with the
    # chat/completions endpoint (adapter OpenAIBatchAdapter)". Adopting it would be a
    # submit-poll-retrieve rewrite, not a MODELS entry.
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

# Both come from scripts/taxonomy.py, which defines every category's attributes in
# one place. Their order is the prompt's — scripts/test_taxonomy.py pins the prompt
# text byte for byte, because a rail edit is a prompt edit.
CATEGORIES = list(taxonomy.CATEGORY_ORDER)

SUBTYPES: dict[str, list[str]] = taxonomy.rails()

_CATEGORY_LIST = ", ".join(CATEGORIES)
# Only the categories the model actually answers. A category whose owner declares
# needs_model = False is settled from the name before a batch is formed, so listing
# its rail here would pay for tokens on every call to describe a decision the model
# never makes — and, worse, couple it to every other answer: adding "bowl" and
# "downstem" to the merch rail edited this prompt for all 268 gold cases and cost
# 3.05 cases (t = -3.2 over 4 runs), none of them merch. Measured, then fixed here.
_SUBTYPE_LINES = "\n".join(
    f"  {c}: {', '.join(s)}" for c, s in SUBTYPES.items()
    if not enrichers.skips_model(c)
)

# ---------------------------------------------------------------------------
# Prompts — one targeted prompt per pass. The classification pass has two
# variants: a "trust the hints" prompt for rows the rule engine could tag, and
# a "decide from scratch" prompt for rows with no reliable sub-format hint.
# ---------------------------------------------------------------------------

# The size rules, shared by pass A (where the LLM classifies) and the sized extract
# prompt (where Jev classified and the LLM writes the size instead).
_VARIANT_RULES = """\
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
  - merch / no meaningful size: \"\""""

_CLASSIFY_BODY = f"""\
category — choose EXACTLY one of: {_CATEGORY_LIST}
  Override hint_category only when the name clearly contradicts it:
  - vape / cart / pod / aio / disposable in the name → vaporizers (even if hint says concentrate)
  - pills / tablets / capsules → edible
  - grinders / papers / lighters / apparel → merch

subtype — choose EXACTLY one from the chosen category's list:
{_SUBTYPE_LINES}

{_VARIANT_RULES}

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

_EXTRACT_RULES = """\
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
- A candidate that only restates the product's own FORMAT is not a differentiator: "Milk
  Chocolate" on a chocolate bar, "Gummies" on a gummy, "Cart" on a cartridge. Skip it and
  keep looking. This applies only when the format word is the WHOLE candidate — a strain
  that merely contains one is real and must be kept ("Chocolate Diesel", "Gummy Bearz").
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

"""

_EXTRACT_PROMPT = (
    "You extract two fields from a cannabis product whose category is already known: strain and\n"
    "product_line.\n\n"
    + _EXTRACT_RULES
    + "Reply ONLY with a JSON array, no prose, no markdown fences:\n"
    '[{"id": "0", "strain": "Watermelon Lemonade", "product_line": null}, ...]'
)

# Pass B for rows Jev classified (jev_classify.py) whose size code could not read
# (stated_size): Jev cannot write text, so the size pass A would have written is asked
# for here, under the same rules, with the category already settled.
_EXTRACT_PROMPT_SIZED = (
    "You extract three fields from a cannabis product whose category is already known: strain,\n"
    "product_line and variant.\n\n"
    + _EXTRACT_RULES
    + _VARIANT_RULES
    + "\n  Each item carries hint_variant, the size the store listed; if unsure, return it unchanged.\n\n"
    "Reply ONLY with a JSON array, no prose, no markdown fences:\n"
    '[{"id": "0", "strain": "Watermelon Lemonade", "product_line": null, "variant": "100mg"}, ...]'
)


# input_tokens is the UNCACHED prompt; cache_write/cache_read are billed at their own
# rates. output_tokens is everything billed as output, a reasoning model's hidden
# reasoning included; reasoning_tokens is the share of it that was reasoning, reported
# for visibility and never added to the cost a second time.
_ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0,
               "cache_read_tokens": 0, "reasoning_tokens": 0}


# When Jev has settled some of a store's rows (jev_extract.py), the LLM sees only the
# hard remainder — and measured, it reads those worse without the easy ones beside it
# ("Lemon Candy Runtz" lost its brand word, "Unscented" became a strain). So the
# settled answers ride along as context: name and answer only, no description, so
# they cost a few input tokens and no output.
_CONTEXT_NOTE = (
    "\n\nThe request is a JSON object. `items` are the products to answer. `answered` lists "
    "other products from the same store whose strain and product_line are already settled: "
    "they are context only — never answer them — but read the items consistently with them.")
_CONTEXT_EXAMPLES = 30


def _with_context(prompt: str) -> str:
    head, sep, reply = prompt.rpartition("\n\nReply ONLY")
    return head + _CONTEXT_NOTE + sep + reply


def stated_size(row: dict, category: str | None) -> str | None:
    """The listing's size when code can read it without guessing — or None, and the
    size chooser (or a model) reads it.

    weight  the store's own figure (the variant field): "2pk" beside "1g" is as often
            the pack as each joint, and the store's field is the better guess — unless
            the name states a different weight ("Runtz - 28G" filed as 1/8 oz), a
            conflict for the chooser. With the field empty, the name's figure when it
            states exactly one weight.
    dose    only when every reading of the size field, name and description agrees
            (size_candidates.assess "settled"). "3pk - 30mg" can be the pack or each
            stick, and a field can hold THC plus CBD; those go to the chooser.

    Measured on 598 listings a model read blind (evals/sizes):
      weights  answers 83%, agrees with the reader on 97.4%. Sending the field-vs-pack
               cases to the chooser instead (100% on 73%) lost pre-roll packs on the
               gold suites: without a price Jev doubles "2pk" + "1g" to 2g.
      doses    answers 54%, agrees on 98.7%. The rule this replaced (a dose times the
               pack count under the 100mg cap) answered 56% and agreed on 72.4%.
    """
    import sizes
    spec = taxonomy.spec(category)
    if spec is None:
        return None
    if spec.measure == "weight":
        stated = sizes.parse(row.get("variant"), category=category)
        named = sizes.parse(row.get("name"), category=category)
        if not stated.grams:
            # No figure in the size field: the name's, when it states exactly one
            # weight ("... POD 0.5G", "Papaya Eighth") — pack math there is the
            # name's own ("5pk x 0.6g"), not a guess about the field.
            weights = sizes.weight_mentions(row.get("name"))
            if not named.grams or len(weights) > 1 and not named.pack:
                return None
            return normalize_variant(f"{named.grams:g}g", category)
        if named.grams and sizes.same_size(named, stated) is False:
            return None
        return normalize_variant(f"{stated.grams:g}g", category)
    if spec.measure == "dose":
        import size_candidates
        a = size_candidates.assess({"variant": row.get("variant"), "scraped_name": row.get("name"),
                                    "description": row.get("description"), "scraped_category": category})
        if a.status != "settled" or not a.values:
            return None
        return normalize_variant(f"{a.values[0]:g}mg", category)
    return None


def code_size(row: dict, category: str | None) -> str | None:
    """stated_size, unless the listing's price rules the weight out: Hold Up Roll Up's
    $150 "Sour Diesel - 32PK 1G Prerolls" with "1g" in its size field is 15 times Herb's
    usual price per gram, so the size goes to the chooser (whose price check finds 32g).
    Uses the run's price snapshot (size_choice.prices_for_run); without one, or for a
    dose, it is stated_size."""
    size = stated_size(row, category)
    spec = taxonomy.spec(category)
    if size is None or spec is None or spec.measure != "weight":
        return size
    import size_choice
    import sizes
    price = str(row.get("price_cents") or "")
    item = size_choice.Item(name=row.get("name", ""), category=category, variant=row.get("variant"),
                            description=row.get("description"), brand=row.get("brand"),
                            price_cents=int(price) if price.isdigit() else None)
    grams = sizes.parse(size, category=category).grams
    if grams and not size_choice.prices_for_run().fits(item, grams):
        return None
    return size


# ---------------------------------------------------------------------------
# Who decides category and subtype — Jev or the LLM's pass A
# ---------------------------------------------------------------------------

# "jev": jev_classify.py answers category and subtype, code writes the size where it
#        can (stated_size), the LLM writes strain and product line — and the size where
#        code could not — in one call, and rows Jev is unsure of take the full LLM path
#        instead. "llm": pass A for every row, as before.
# Read per call so one process (the eval harness) can compare both.
def _classifier() -> str:
    return os.environ.get("ENRICH_CLASSIFIER", "jev").strip().lower()


# A Jev answer below this probability — for the category, or for the subtype within
# it — is not taken; the row goes to the LLM's pass A. Measured on the gold suites
# (evals/enrich/README.md): 0.80 sends ~7% of rows to the LLM and every wrong Jev
# answer was among them.
JEV_MIN_CONFIDENCE = float(os.environ.get("ENRICH_JEV_MIN_CONFIDENCE", "0.80"))


# Strain and product line picked by Jev from the name's phrases (jev_extract.py), for
# rows Jev classified and code sized — those then reach no LLM at all. A strain is
# taken at JEV_TEXT_MIN (0.90: Jev's picks there are 99.4% right on the gold suites), a
# named line at JEV_LINE_MIN, "no line" at the lower JEV_NO_LINE_MIN — a missing line
# costs less than a wrong one. ENRICH_JEV_TEXT=0 sends these rows to the LLM as before.
def _jev_text() -> bool:
    return os.environ.get("ENRICH_JEV_TEXT", "1").strip() != "0"


# ENRICH_LLM=0 sends nothing to an LLM: Jev and code answer every field
# (_run_without_llm). Measured level with the LLM path on the gold suites, at less than
# half the run-to-run churn and 40% of the cost (evals/enrich/README.md, "Jev only").
def _llm_enabled() -> bool:
    return os.environ.get("ENRICH_LLM", "1").strip() != "0"


JEV_TEXT_MIN = float(os.environ.get("ENRICH_JEV_TEXT_MIN", "0.90"))
JEV_LINE_MIN = float(os.environ.get("ENRICH_JEV_LINE_MIN", "0.80"))
JEV_NO_LINE_MIN = float(os.environ.get("ENRICH_JEV_NO_LINE_MIN", "0.50"))


def _extract_with_jev(rows: list[tuple[int, dict]], categories: list, strains: list,
                      product_lines: list, subtypes: list
                      ) -> tuple[list[tuple[int, dict]], jev.Usage]:
    """Settle strain and line with Jev where it is confident; returns the rows settled.

    The same phrase picked as both strain and line is a contradiction, not an answer,
    and leaves the row to the LLM.
    """
    usage = jev.Usage()
    answers = jev_extract.extract([(row, categories[oi], subtypes[oi]) for oi, row in rows],
                                  usage=usage)
    settled = []
    for (oi, row), a in zip(rows, answers):
        if a is None or a.strain is None or a.p_strain < JEV_TEXT_MIN:
            continue
        if a.line is None:
            if a.p_line < JEV_NO_LINE_MIN:
                continue
        elif a.p_line < JEV_LINE_MIN or a.line.lower() == a.strain.lower():
            continue
        strains[oi] = enrichers.for_category(categories[oi]).strain(
            row.get("name", ""), jev_extract.tidy(a.strain))
        product_lines[oi] = a.line
        settled.append((oi, row))
    return settled, usage


def _classify_with_jev(pending: list[tuple[int, dict]], categories: list, subtypes: list,
                       min_confidence: float | None = None, probs: dict | None = None,
                       ) -> tuple[list[tuple[int, dict]], list[tuple[int, dict]], jev.Usage]:
    """Settle category and subtype with Jev where it is confident.

    Returns (classified, rest, usage). `rest` — failed calls and answers below
    JEV_MIN_CONFIDENCE — goes through pass A unchanged. The overrides are the ones
    pass A's applier makes, in the same order: a curated device token fixes the
    category, the owning enricher's name tokens and the rails fix the subtype.
    """
    bar = JEV_MIN_CONFIDENCE if min_confidence is None else min_confidence
    usage = jev.Usage()
    items = [(row, _hint_category(row), _hint_subtype(row)) for _, row in pending]
    answers = jev_classify.classify(items, usage=usage)
    classified, rest = [], []
    for (oi, row), (_, _, hint_sub), a in zip(pending, items, answers):
        if a is None:
            rest.append((oi, row))
            continue
        name = row.get("name", "")
        forced = find_format_category(row.get("brand", ""), name)
        cat = forced or _valid_category(a.category, row.get("category"))
        owner = enrichers.for_category(cat)
        sub_answer, p_sub = a.subtype_for(cat)
        if len(SUBTYPES.get(cat, ())) <= 1 or not owner.needs_model:
            p_sub = 1.0          # nothing to choose, or the owner's tokens decide (merch)
        if min(1.0 if forced else a.p_category, p_sub) < bar:
            rest.append((oi, row))
            continue
        if probs is not None:
            probs[oi] = (1.0 if forced else a.p_category, p_sub)
        categories[oi] = cat
        subtypes[oi] = _valid_subtype(sub_answer, cat, owner.token_subtype(name) or hint_sub)
        classified.append((oi, row))
    return classified, rest, usage


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
    label: str, print_lock, params: dict | None = None,
) -> tuple[dict | None, dict]:
    """Returns (items_by_local_id, usage_dict). items is None on any failure —
    callers must treat those rows as unanswered (fall back to hints, do NOT cache)."""
    for attempt in range(_MAX_ATTEMPTS):
        items, usage, retry_after = _call_llm_once(
            client, provider, api_model, system_prompt, payload,
            timeout, max_tokens, label, print_lock, params)
        if items is not None or retry_after is None:
            return items, usage
        # Transient: the gateway told us to wait (rate limit / in-flight budget).
        # Sleeping here holds this worker's slot, which is exactly the throttle we
        # want — it stops the pool from re-flooding the gateway.
        if attempt < _MAX_ATTEMPTS - 1:
            with print_lock:
                print(f"    {label} retrying in {retry_after:.0f}s "
                      f"(attempt {attempt + 2}/{_MAX_ATTEMPTS})", file=sys.stderr)
            time.sleep(retry_after)
    return None, dict(_ZERO_USAGE)


# Transient gateway failures worth waiting out rather than dropping the batch.
_MAX_ATTEMPTS = 3
_RETRY_STATUS = {402, 408, 429, 500, 502, 503, 504}
_DEFAULT_RETRY_AFTER = 30.0
_MAX_RETRY_AFTER = 180.0


def _retry_delay(exc: Exception) -> float | None:
    """Seconds to wait before retrying, or None if the error is not transient.
    Prefers the gateway's own Retry-After when it sends one."""
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
    if status not in _RETRY_STATUS:
        return None
    hinted = None
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers:
        try:
            hinted = float(headers.get("Retry-After") or headers.get("retry-after"))
        except (TypeError, ValueError):
            hinted = None
    if hinted is None:
        # OpenRouter nests it in the error body rather than the HTTP headers.
        m = re.search(r"'Retry-After':\s*'(\d+)'", str(exc))
        hinted = float(m.group(1)) if m else _DEFAULT_RETRY_AFTER
    return min(hinted, _MAX_RETRY_AFTER)


def _openai_usage(u) -> dict:
    """An OpenAI-style usage block, as the counters the anthropic branch reports.

    `prompt_tokens` includes the cached and cache-written tokens, which are billed at
    their own rates, so they are split out of input_tokens. `completion_tokens`
    already includes a reasoning model's reasoning tokens (checked against the
    gateway's own billed cost: output rate x completion_tokens, nothing on top), so
    reasoning is reported beside it and not added to it. Gateways that report no
    details leave every extra counter at 0.
    """
    def count(details, name: str) -> int:
        return getattr(details, name, 0) or 0

    prompt = getattr(u, "prompt_tokens_details", None)
    cached, written = count(prompt, "cached_tokens"), count(prompt, "cache_write_tokens")
    return {
        "input_tokens":       max(0, u.prompt_tokens - cached - written),
        "output_tokens":      u.completion_tokens,
        "cache_write_tokens": written,
        "cache_read_tokens":  cached,
        "reasoning_tokens":   count(getattr(u, "completion_tokens_details", None),
                                    "reasoning_tokens"),
    }


def _call_llm_once(
    client, provider: str, api_model: str, system_prompt: str,
    payload: list[dict], timeout: float, max_tokens: int,
    label: str, print_lock, params: dict | None = None,
) -> tuple[dict | None, dict, float | None]:
    """One attempt. Third element is the retry delay when the failure is transient."""
    finish = None
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
                "reasoning_tokens":   0,
            }
        else:  # openrouter — OpenAI-compatible chat completions
            resp = client.chat.completions.create(
                model=api_model, max_tokens=max_tokens, timeout=timeout,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": json.dumps(payload)},
                ],
                **(params or {}),       # the model entry's own knobs (MODELS "params")
            )
            finish = resp.choices[0].finish_reason
            text = (resp.choices[0].message.content or "").strip()
            usage = _openai_usage(resp.usage)
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        if isinstance(parsed, dict):        # a reply that echoed the request's shape
            parsed = parsed.get("items") or []
        # Entries without an id are not answers — e.g. a context row the model echoed.
        items = {str(item["id"]): item for item in parsed if isinstance(item, dict) and "id" in item}
    except Exception as exc:
        delay = _retry_delay(exc)
        # A reply cut off at max_tokens fails as bad JSON, or as no JSON at all when a
        # reasoning model spent the whole budget thinking; say which it was.
        cut = f" (cut off at max_tokens={max_tokens})" if finish == "length" else ""
        with print_lock:
            print(f"  [model error] {label}: {str(exc)[:200]}{cut}", file=sys.stderr)
        return None, dict(_ZERO_USAGE), delay

    with print_lock:
        print(f"    {label} done")
    return items, usage, None


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


def _run_without_llm(pending: list[tuple[int, dict]], cache: dict, slug: str, categories: list,
                     subtypes: list, strains: list, product_lines: list, variants: list) -> dict:
    """Jev and code only (ENRICH_LLM=0): every field is Jev's pick or code's, whatever
    Jev's confidence — measured on the gold suites, its best guess beats keeping the
    store's value (evals/enrich/README.md, "Jev only").

      category, subtype  Jev (jev_classify)
      size               code where it reads the size without guessing (stated_size), else
                         size_choice: size_candidates' readings, the run's prices, then Jev;
                         below the chooser's bar the store's size field stands
      strain, line       Jev from the name's phrases (jev_extract)

    Each answer is cached with Jev's probability per field ("p"), which the daily audit
    reads to review the unsure ones. A row whose Jev call failed is marked enrich_failed
    and not cached, so the next run asks again and the importer keeps what it holds.
    """
    import size_candidates
    import size_choice

    usage = dict(_ZERO_USAGE)
    probs: dict[int, tuple[float, float]] = {}
    by_jev, rest, cu = _classify_with_jev(pending, categories, subtypes, min_confidence=0.0, probs=probs)
    failed = {oi for oi, _ in rest}

    def category(oi, row):
        return categories[oi] or _hint_category(row)

    p_size: dict[int, tuple[float, str]] = {}
    items, open_rows = [], []
    for oi, row in pending:
        cat = category(oi, row)
        size = code_size(row, cat)
        if size is not None:
            variants[oi] = enrichers.for_category(cat).variant(row.get("name", ""), size) or size
            p_size[oi] = (1.0, "code")
        elif size_candidates.unit_of(cat):
            items.append(size_choice.Item(
                name=row.get("name", ""), category=cat, variant=row.get("variant"),
                description=row.get("description"), brand=row.get("brand"),
                price_cents=int(row["price_cents"]) if str(row.get("price_cents") or "").isdigit() else None))
            open_rows.append((oi, row, cat))
    su = jev.Usage()
    picks = size_choice.choose(items, size_choice.prices_for_run(), usage=su)
    for (oi, row, cat), pick in zip(open_rows, picks):
        p_size[oi] = (pick.p, pick.by)
        if pick.by != "field" and pick.value is not None:
            size = normalize_variant(f"{pick.value:g}{size_candidates.unit_of(cat)}", cat)
            variants[oi] = enrichers.for_category(cat).variant(row.get("name", ""), size) or size
        elif pick.value is None:
            # No size, and the store's field is none in the category's unit either:
            # Camino's 20-gummy pack filed as "72g", its net weight. Blank, not that.
            variants[oi] = ""

    xu = jev.Usage()
    answers = jev_extract.extract([(row, category(oi, row), subtypes[oi]) for oi, row in pending], usage=xu)
    p_text: dict[int, tuple[float, float]] = {}
    for (oi, row), a in zip(pending, answers):
        if a is None:
            if jev_extract.phrases(row.get("name", ""), row.get("brand")):
                failed.add(oi)          # a name with phrases and no answer: the call failed
            continue
        if a.strain:
            strains[oi] = enrichers.for_category(category(oi, row)).strain(
                row.get("name", ""), jev_extract.tidy(a.strain))
        if a.line and not (a.strain and a.line.lower() == a.strain.lower()):
            product_lines[oi] = a.line
        p_text[oi] = (a.p_strain, a.p_line)

    for oi, row in pending:
        if oi in failed:
            row["enrich_failed"] = True
            continue
        key = _cache_key(row)
        if not key:
            continue
        p_cat, p_sub = probs.get(oi, (1.0, 1.0))
        p_str, p_line = p_text.get(oi, (1.0, 1.0))
        p_sz, size_by = p_size.get(oi, (1.0, "none"))
        cache[key] = {
            "v": _ENRICH_VERSION, "category": categories[oi], "subtype": subtypes[oi],
            "strain": strains[oi], "product_line": product_lines[oi], "variant": variants[oi],
            "jq": jev_classify.QUESTION_VERSION, "jx": jev_extract.QUESTION_VERSION, "src": "jev",
            "size_by": size_by,
            "p": {"category": round(p_cat, 3), "subtype": round(p_sub, 3), "strain": round(p_str, 3),
                  "product_line": round(p_line, 3), "size": round(p_sz, 3)},
        }
    _save_cache(cache, slug)

    usage["jev_requests"] = cu.requests + su.requests + xu.requests
    usage["jev_cost_usd"] = cu.cost_usd + su.cost_usd + xu.cost_usd
    usage["jev_classified"] = len(by_jev)
    usage["sized_by_code"] = sum(1 for p, by in p_size.values() if by == "code")
    print(f"    jev only: {len(pending)} row(s); sized by code {usage['sized_by_code']}, by the chooser "
          f"{sum(1 for p in picks if p.by != 'field')} of {len(picks)}; {len(failed)} failed "
          f"(${usage['jev_cost_usd']:.4f})")
    return usage


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
    catalog_hints: bool = False,
) -> dict:
    """Field-decomposed enrichment in two dependent passes:
      A) classify category+subtype+variant (hinted rows and fresh rows get different prompts)
      B) extract strain+product_line, conditioned on the category decided in A, and nudged
         toward known_strains/known_product_lines already recorded for the brand
    Every answer is clamped to a legal value by the validators above.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    if not _llm_enabled():
        return _run_without_llm(pending, cache, slug, categories, subtypes, strains, product_lines, variants)

    client = _make_client(model_cfg)
    if client is None:
        # No key means no answers. Say so on every row, loudly: rows that leave here
        # unmarked look exactly like answered ones, and the importer would write their
        # fallback subtype/strain/product_line over a listing's stored identity.
        print(f"  [error] no client for {model_cfg['api_model']} — "
              f"{len(pending)} row(s) left unenriched and marked enrich_failed", file=sys.stderr)
        for _, row in pending:
            row["enrich_failed"] = True
        return dict(_ZERO_USAGE)

    # Rows whose batch errored or whose id the model dropped (truncation). They
    # still get hint/default values for this run's output, but are excluded from
    # the cache so the next run retries them instead of freezing the fallback.
    failed_rows: set[int] = set()

    provider, api_model = model_cfg["provider"], model_cfg["api_model"]
    timeout    = model_cfg.get("timeout", _DEFAULT_TIMEOUT)
    max_tokens = model_cfg.get("max_tokens", _DEFAULT_MAX_TOKENS)
    params     = model_cfg.get("params")        # extra request parameters, if the model needs any
    batch_size = model_cfg.get("batch_size", batch_size)  # per-model override (small for flaky models)
    print_lock = threading.Lock()
    usage = dict(_ZERO_USAGE)

    def run_phase(tasks: list[tuple]) -> None:
        """tasks = [(label, system_prompt, payload, on_result), ...]; runs them concurrently."""
        if not tasks:
            return
        # Concurrency is capped by ENRICH_MAX_WORKERS (default 8). Gateways that
        # meter *in-flight* tokens rather than requests — OpenRouter's in-flight
        # budget among them — reject whole batches with 402 when 8 full-description
        # batches are open at once. Lower it to 2-3 for a large fleet run.
        try:
            _workers = max(1, int(os.environ.get("ENRICH_MAX_WORKERS", "8")))
        except ValueError:
            _workers = 8
        with ThreadPoolExecutor(max_workers=min(len(tasks), _workers)) as ex:
            futs = {
                ex.submit(_call_llm, client, provider, api_model, sp, pl, timeout, max_tokens, label,
                          print_lock, params): onr
                for (label, sp, pl, onr) in tasks
            }
            for fut in as_completed(futs):
                items, u = fut.result()
                for k in _ZERO_USAGE:       # usage also carries jev_* totals
                    usage[k] += u[k]
                futs[fut](items)

    # ---- Pass A0: Jev classifies; what it is unsure of falls through to pass A ----
    by_jev: list[tuple[int, dict]] = []
    to_llm = pending
    if _classifier() == "jev" and jev.available():
        by_jev, to_llm, jev_usage = _classify_with_jev(pending, categories, subtypes)
        usage["jev_requests"] = jev_usage.requests
        usage["jev_cost_usd"] = jev_usage.cost_usd
        usage["jev_classified"] = len(by_jev)
        print(f"    pass A0: jev classified {len(by_jev)} of {len(pending)} item(s); "
              f"{len(to_llm)} below {JEV_MIN_CONFIDENCE:.2f} or failed → {api_model} "
              f"(${jev_usage.cost_usd:.4f})")
    # A size code can read (stated_size) needs no model either; only the rest are asked
    # for one, alongside strain and product line, in the sized pass B prompt.
    need_size: list[tuple[int, dict]] = []
    sized_by_code: list[tuple[int, dict]] = []
    for oi, row in by_jev:
        size = code_size(row, categories[oi])
        if size is None:
            need_size.append((oi, row))
            continue
        ov = enrichers.for_category(categories[oi]).variant(row.get("name", ""), size)
        variants[oi] = ov or size
        sized_by_code.append((oi, row))
    if by_jev:
        usage["sized_by_code"] = len(sized_by_code)
    by_jev_ids = {oi for oi, _ in by_jev}
    need_size_ids = {oi for oi, _ in need_size}

    # ---- Pass A1: Jev picks strain and line from the name — rows it settles are done ----
    settled: list[tuple[int, dict]] = []
    if sized_by_code and _jev_text():
        settled, text_usage = _extract_with_jev(sized_by_code, categories, strains,
                                                product_lines, subtypes)
        usage["jev_text_requests"] = text_usage.requests
        usage["jev_cost_usd"] = usage.get("jev_cost_usd", 0.0) + text_usage.cost_usd
        usage["jev_settled"] = len(settled)
        print(f"    pass A1: jev settled strain/line for {len(settled)} of {len(sized_by_code)} "
              f"item(s); the rest → {api_model} (${text_usage.cost_usd:.4f})")
    settled_ids = {oi for oi, _ in settled}

    # ---- Pass A: classification, split by hint availability ----
    hinted   = [(oi, r) for (oi, r) in to_llm if _hint_subtype(r) is not None]
    fresh    = [(oi, r) for (oi, r) in to_llm if _hint_subtype(r) is None]

    _cap_a = _pass_a_desc_cap()

    def classify_payload(chunk):
        return [
            {
                "id":            str(i),
                "hint_category": _hint_category(r),
                "brand":         r.get("brand", ""),
                "name":          r.get("name", ""),
                "description":   _cap_desc(r.get("description", ""), _cap_a),
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
                # A row hinted as something else can still come back as a category
                # that has an owner, so the owner gets the last word here too — not
                # only on the rows routed past the model entirely.
                owner = enrichers.for_category(cat)
                name = row.get("name", "")
                subtypes[oi]   = _valid_subtype(it.get("subtype"), cat,
                                                owner.token_subtype(name) or _hint_subtype(row))
                v = it.get("variant")
                variants[oi]   = v if v is not None else row.get("variant", "")
                # A size or pack count is a string fact about the name; where the
                # owner writes one, it wins over whatever the model returned.
                ov = owner.variant(name, variants[oi])
                if ov:
                    variants[oi] = ov
        return on_result

    classify_tasks = []
    for kind, bucket, prompt in (("hinted", hinted, _CLASSIFY_PROMPT_HINTED),
                                 ("fresh",  fresh,  _CLASSIFY_PROMPT_FRESH)):
        for bi, chunk in enumerate(_chunks(bucket, batch_size)):
            classify_tasks.append(
                (f"classify[{kind}] {bi + 1}", prompt, classify_payload(chunk), classify_applier(chunk))
            )

    print(f"    pass A: classify {len(to_llm)} item(s) "
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

    def extract_applier(chunk, sized=False):
        def on_result(items):
            for local_id, (oi, row) in enumerate(chunk):
                it = (items or {}).get(str(local_id))
                if it is None:
                    failed_rows.add(oi)
                    it = {}
                if sized:
                    # Jev classified this row, so the size pass A would have written
                    # comes from here — same rules, same owner override.
                    v = it.get("variant")
                    variants[oi] = v if v is not None else row.get("variant", "")
                    ov = enrichers.for_category(categories[oi]).variant(
                        row.get("name", ""), variants[oi])
                    if ov:
                        variants[oi] = ov
                product_lines[oi] = it.get("product_line")
                # The owner decides what `strain` means for its category — merch
                # returns None, because a cultivar is not what separates two
                # accessories; colour and flavour live in `attributes` instead.
                # That keeps `strain` meaning one thing everywhere it is set.
                strains[oi] = enrichers.for_category(categories[oi]).strain(
                    row.get("name", ""), it.get("strain"))
        return on_result

    def extract_payload_item(i, oi, r):
        item = {
            "id":          str(i),
            "brand":       r.get("brand", ""),
            "name":        r.get("name", ""),
            "category":    categories[oi] or r.get("category", "other"),
            "description": r.get("description", ""),
        }
        if oi in need_size_ids:
            item["hint_variant"] = r.get("variant", "")
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

        # Where we hold a catalog for this brand, its own product list is a better
        # source for the same slots than `listings` is: the DB hints above are our
        # previous model output, so they nudge toward consistency rather than toward
        # correctness. Catalog values win the overlap and add `catalog_products`, the
        # nearest real titles. Still only a hint — the model decides.
        if catalog_hints:
            item.update(catalog_enricher.hints(r.get("brand"), r.get("name", "")))
        return item

    extract_tasks = []
    plain = to_llm + [(oi, r) for oi, r in sized_by_code if oi not in settled_ids]
    answered = [{"name": r.get("name", ""), "strain": strains[oi],
                 "product_line": product_lines[oi]} for oi, r in settled]
    for kind, bucket, prompt, sized in (("", plain, _EXTRACT_PROMPT, False),
                                        ("+size ", need_size, _EXTRACT_PROMPT_SIZED, True)):
        for bi, chunk in enumerate(_chunks(bucket, batch_size)):
            payload = [extract_payload_item(i, oi, r) for i, (oi, r) in enumerate(chunk)]
            sp = prompt
            if answered:
                # The batch's own brands first: that is where reading consistently matters.
                brands = {(r.get("brand") or "").lower() for _, r in chunk}
                same = [i for i, (_, r) in enumerate(settled)
                        if (r.get("brand") or "").lower() in brands]
                rest = [i for i in range(len(settled)) if i not in set(same)]
                context = [answered[i] for i in (same + rest)[:_CONTEXT_EXAMPLES]]
                payload, sp = {"answered": context, "items": payload}, _with_context(prompt)
            extract_tasks.append((f"extract {kind}{bi + 1}", sp, payload,
                                  extract_applier(chunk, sized)))

    print(f"    pass B: extract strain/product_line for {len(plain) + len(need_size)} "
          f"item(s) → {api_model}")
    run_phase(extract_tasks)

    # ---- Write cache once, both passes applied ----
    # Rows in failed_rows carry fallback values, not model answers — leaving them
    # out of the cache means the next run re-enriches them instead of trusting junk.
    if failed_rows:
        print(f"  [warn] {len(failed_rows)} row(s) not cached (model error/truncation); "
              f"will retry next run", file=sys.stderr)
    for (oi, row) in pending:
        if oi in failed_rows:
            # Tell the caller which rows carry fallbacks rather than answers. A
            # caller writing back over an existing file — or the importer, writing
            # over a stored listing — needs to distinguish "empty because the batch
            # broke" from "empty on purpose": merch strain is deliberately null, and
            # so is any field the model legitimately declines. It is a CSV column
            # (scraper_common.CSV_COLUMNS), so the marker survives to the import.
            row["enrich_failed"] = True
            continue
        key = _cache_key(row)
        if key:
            cache[key] = {
                "v": _ENRICH_VERSION,
                "category": categories[oi], "subtype": subtypes[oi], "strain": strains[oi],
                "product_line": product_lines[oi], "variant": variants[oi],
            }
            if oi in by_jev_ids:
                cache[key]["jq"] = jev_classify.QUESTION_VERSION
            if oi in settled_ids:
                cache[key]["jx"] = jev_extract.QUESTION_VERSION

    _save_cache(cache, slug)
    return usage


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich(rows: list[dict], batch_size: int = 50, no_enrich: bool = False,
           model: str = DEFAULT_MODEL, brand_examples: dict[str, dict] | None = None,
           catalog_hints: bool = False) -> dict:
    """Enrich every row in place: corrects category, adds subtype/strain/product_line/variant.

    `model` selects an entry from MODELS (default "haiku"). Each non-default model
    gets its own cache file so a comparison run never reads another model's answers.

    `catalog_hints` adds the brand's real product list (data/catalogs/) to the pass-B
    prompt as context. A hint only — the model still decides, and nothing is written
    from the catalog directly.

    DEFAULT OFF, because measured it costs more than it returns. Over two eval runs
    each way: baseline 279/278, hint 277/275. The two standing Ayrloom failures it was
    built to fix (x-ayrloom-honeycrisp, holdup-044) do flip to passing — but they also
    flip on a second baseline run with no hint at all, so that is run-to-run variance,
    not evidence. Against it, three Camino cases lose product_line in both hinted runs
    and neither unhinted one, and Camino has no catalog: adding hint keys to some items
    in a 50-item batch moves the model's answers on its neighbours. Until that
    cross-item effect is understood, this stays opt-in.

    `brand_examples` injects a brand→{strains, product_lines} index to nudge strain/line
    consistency. The nudge is OFF by default; when brand_examples is None it auto-loads from
    the DB only if ENRICH_BRAND_NUDGE=1. Pass an explicit dict to force-use it, or {} to disable.

    Returns a token usage dict: {input_tokens (uncached), output_tokens (a reasoning
    model's reasoning included), cache_write_tokens, cache_read_tokens, reasoning_tokens
    (the share of output_tokens that was reasoning), cost_usd}. All zeros when everything
    was cached.
    """
    # The marker describes this run. A row read back from an earlier CSV may still
    # carry "True" from a run that failed; left in place, an answered row would look
    # failed (and have deliberate nulls "restored"), so it is cleared up front.
    for row in rows:
        row.pop("enrich_failed", None)

    if no_enrich:
        for row in rows:
            row.setdefault("subtype", "other")
            row.setdefault("strain", "")
            row.setdefault("product_line", None)
            # Attributes are read from the name, not asked of the model, so a
            # --no-enrich scrape has no reason to go without them.
            row.setdefault("attributes", attribute_registry.for_category(
                row.get("category"), row.get("name", "")) or None)
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
        # A row a human has signed off on entirely never reaches the model — the
        # answer is already known and better than anything the pipeline would
        # produce, so re-deriving it would only risk overwriting it. This also
        # makes verified rows free.
        if verification.is_fully_verified(row):
            v = verification.verified_fields(row)
            categories.append(v.get("category"))
            subtypes.append(v.get("subtype"))
            strains.append(v.get("strain"))
            product_lines.append(v.get("product_line"))
            variants.append(v.get("variant"))
            continue

        # A category whose owner declares needs_model = False is answered from the
        # name alone. Skipping here rather than filtering later means those rows
        # never enter a batch, so they cost nothing and cannot be perturbed by a
        # model's run-to-run variance.
        hint_cat = _hint_category(row)
        if enrichers.skips_model(hint_cat):
            owner = enrichers.for_category(hint_cat)
            name = row.get("name", "")
            categories.append(hint_cat)
            # row["subtype"] is normally absent on a fresh scrape; when a caller does
            # supply the stored value, a model answer the tokens do not cover survives.
            subtypes.append(owner.subtype(name, row.get("subtype")))
            strains.append(owner.strain(name, None))
            product_lines.append(owner.product_line(row.get("brand", ""), name, None))
            variants.append(owner.variant(name, row.get("variant")))
            continue

        key = _cache_key(row)
        entry = cache.get(key) if key else None
        # Re-enrich if not cached, if the cache pre-dates the variant/category
        # fields, or if it was written under an older prompt/taxonomy version.
        if entry and "variant" in entry and "category" in entry \
                and entry.get("v") == _ENRICH_VERSION \
                and entry.get("jq") in (None, jev_classify.QUESTION_VERSION) \
                and entry.get("jx") in (None, jev_extract.QUESTION_VERSION):
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

    no_model = sum(1 for r in rows if enrichers.skips_model(_hint_category(r)))
    cached_count = len(rows) - len(pending) - no_model
    if no_model:
        print(f"  deterministic: {no_model} row(s) answered from the name, no model call")
    if pending:
        print(f"  enrich: {cached_count} cached, {len(pending)} → {model}")
        usage = _run_enrich(pending, cache, slug, categories, subtypes, strains, product_lines, variants, model_cfg, batch_size, brand_examples, catalog_hints)
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
        # Category-specific identity, derived from the name. Only categories with a
        # shape in the registry get anything; the rest keep None.
        row["attributes"]   = attribute_registry.for_category(
            row["category"], row.get("name", "")) or None

    # Deterministic canonicalization last: curated product lines and strain aliases
    # override the model, so identity is consistent across dispensaries and runs.
    # Applied to cached rows too — adding a map entry takes effect without re-enriching.
    canon_stats = canonicalize(rows)
    if any(canon_stats.values()):
        print("  canonical: " + ", ".join(f"{k}={v}" for k, v in canon_stats.items() if v))

    # Human answers win over both the model and the curated maps, so they are
    # applied last. Partially verified rows land here: they still went through
    # enrichment for their unverified fields, and this restores the signed ones.
    verified_n = lapsed_n = 0
    for row in rows:
        if verification.verified_fields(row):
            verification.apply(row)
            verified_n += 1
        lapsed_n += bool(verification.lapsed_fields(row))
    if verified_n or lapsed_n:
        msg = f"  verified: {verified_n} row(s) protected"
        if lapsed_n:
            msg += f", {lapsed_n} lapsed (renamed since review — needs re-check)"
        print(msg)

    usage["failed_rows"] = sum(1 for row in rows if row.get("enrich_failed"))
    if usage["failed_rows"]:
        print(f"  [warn] {usage['failed_rows']} row(s) unenriched this run "
              f"(marked enrich_failed; the importer keeps their stored identity)", file=sys.stderr)

    c = model_cfg["cost"]
    # A cached or cache-written token the entry gives no rate for is billed as plain
    # input, which is what every gateway-routed model was charged before cache tokens
    # were split out of input_tokens. output_tokens already holds any reasoning.
    cost = (
        usage["input_tokens"]         * c.get("input", 0)
        + usage["output_tokens"]      * c.get("output", 0)
        + usage["cache_write_tokens"] * c.get("cache_write", c.get("input", 0))
        + usage["cache_read_tokens"]  * c.get("cache_read", c.get("input", 0))
    )
    usage["cost_usd"] = round(cost + usage.get("jev_cost_usd", 0.0), 4)
    return usage


def write_usage(usage: dict, csv_path: str) -> None:
    """Write usage dict as a sidecar .usage.json next to the CSV."""
    path = Path(csv_path).with_suffix(".usage.json")
    path.write_text(json.dumps(usage, indent=2))
