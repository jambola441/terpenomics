"""
review_agent.py — Labels the listings Jev was unsure of, with a Claude model driving the
read-only tools in review_tools.py.

A batch is one to five listings from one store and brand, so catalog lookups are
shared. The model reads the labelling conventions (evals/enrich/CONVENTIONS.md) and the
taxonomy, works with the tools (the brand's catalog, other stores' listings, the size
readings, the listing's page, web search), and records one answer per listing with
submit_labels. Nothing is written anywhere: answers and proposed catalog fixes come
back to the caller, which decides what to apply.

    ctx = review_tools.ReviewContext.from_db(brands=["Grön"])
    for batch in batches(listings):
        result = review_batch(ctx.for_batch({l["id"]: l for l in batch}), batch)
        result.answers, result.proposals, result.cost_usd

Needs ANTHROPIC_API_KEY. Each listing dict is review_tools' shape plus, optionally,
"first_pass" (the five fields Jev wrote) and "p" (its probability for each).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import catalog_store
import review_tools
import taxonomy

ROOT = Path(__file__).resolve().parent.parent
CONVENTIONS = ROOT / "evals" / "enrich" / "CONVENTIONS.md"

DEFAULT_MODEL = "claude-sonnet-5-5"
# $ per million tokens; a cache write (five-minute) costs 1.25x input. Web search is $10
# per 1,000 searches; web fetch costs only its tokens.
PRICES = {
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
}
WEB_SEARCH_USD = 0.01
BATCH_SIZE = 5
MAX_TURNS = 40
MAX_TOKENS = 16000

FIELD_NAMES = {"category": "category", "subtype": "subtype", "strain": "strain",
               "product_line": "product line", "variant": "size"}
P_KEYS = {"variant": "size"}          # enrich's cache calls the size's probability "size"

SYSTEM_HEAD = """\
You label cannabis product listings from New York dispensary menus for a price-comparison
catalog. A first pass (a fast classifier) labelled each listing you are given but was unsure
of at least one field, and no catalog entry settled the listing. Your answer replaces the
first pass's.

A listing's identity is five fields: category, subtype, strain, product line and size. Two
listings with the same five fields are treated as the same product at different stores, so
agreeing with the brand's catalog and with how other stores name the product matters as much
as reading the listing itself.

## How to work

For each listing:

1. Read it: the name, the store's category, the store's size field, the price, the
   description. Store size fields are often wrong for edibles (a net weight like "72g" on a
   gummy pack) and for packs (one joint's weight on a 5-pack).
2. Search the brand's catalog (search_catalog). When an entry is this product, take its
   category, subtype, strain and product line, and its size when the listing's own figures
   agree. A catalog built from the brand's own site outranks one built from store listings.
   Make sure the entry really is this product: the same name in another format or strength
   is a different product.
3. When the catalog lacks the product or the name is unusual, look at how other stores list
   it (other_store_listings). Agreement across stores is good evidence; one store's
   spelling is weak.
4. For the size, call size_readings and choose among its readings. It does the pack
   arithmetic and shows what packages of each size typically sell for; the listing's price
   tells a single from a pack.
5. Use the web (web_search, web_fetch, or listing_page for the store's own page) only when
   the tools above leave a field open: a product name you can't place, a pack count nobody
   states. The brand's own site is the best source.
6. Record your answer with submit_labels, once per listing. When the catalog lacks the
   product or has it wrong, also call propose_catalog_fix; a person approves those.

The first pass's answers are shown with how sure it was. Check every field yourself: it is
most often wrong where it was unsure, and sometimes where it was sure.

Confidence:
- sure: the catalog, the brand's site, or several stores agree with your reading.
- likely: one good source or a clear reading of the listing, and nothing against it.
- unsure: the evidence conflicts or is missing. An unsure answer goes to a person; prefer
  it to a guess.

Use null for a strain or product line the product doesn't have, and for a size nobody
states. When you have recorded every listing, reply with one short line per listing: its id
and anything a person should double-check.
"""


def _taxonomy_text() -> str:
    lines = []
    for cat in taxonomy.CATEGORY_ORDER:
        rail = taxonomy.rails().get(cat, [])
        if taxonomy.keeps_subtype(cat):
            lines.append(f"- {cat}: {', '.join(rail)}")
        else:
            lines.append(f"- {cat}: no subtype (submit null)")
    return "\n".join(lines)


def system_prompt() -> str:
    """The labelling preamble: how to work, the conventions verbatim, the taxonomy.
    Identical across requests, so it caches."""
    return (f"{SYSTEM_HEAD}\n## Labelling conventions\n\n{CONVENTIONS.read_text().strip()}\n\n"
            f"## Taxonomy: categories and their subtypes\n\n{_taxonomy_text()}\n")


def tool_definitions(web: bool = True) -> list[dict]:
    tools = [{**t, "strict": True} for t in review_tools.TOOLS]
    if web:
        tools += [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5},
                  {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5,
                   "max_content_tokens": 8000}]
    return tools


def _money(cents) -> str | None:
    return f"${cents / 100:,.2f}" if cents else None


def listing_text(l: dict, store_name: str | None = None) -> str:
    """One listing as the model reads it."""
    rows = [("id", l["id"]), ("store", store_name), ("brand", l.get("brand")), ("name", l.get("name")),
            ("store category", l.get("raw_category") or l.get("category")),
            ("store size field", l.get("size_field")), ("price", _money(l.get("price_cents"))),
            ("url", l.get("url")), ("description", (l.get("description") or "").strip() or None)]
    out = [f"{k}: {v}" for k, v in rows if v]
    fp, p = l.get("first_pass") or {}, l.get("p") or {}
    if fp:
        parts = []
        for f, label in FIELD_NAMES.items():
            if f not in fp:
                continue
            val = fp.get(f) or "none"
            pf = p.get(P_KEYS.get(f, f))
            parts.append(f"{label} {val}" + (f" ({pf:.0%} sure)" if isinstance(pf, (int, float)) else ""))
        out.append("first pass: " + "; ".join(parts))
    return "<listing>\n" + "\n".join(out) + "\n</listing>"


def batch_prompt(listings: list[dict], stores: dict[str, str] | None = None) -> str:
    stores = stores or {}
    head = "Label this listing." if len(listings) == 1 else f"Label these {len(listings)} listings."
    return head + "\n\n" + "\n\n".join(listing_text(l, stores.get(l.get("store") or "", l.get("store")))
                                       for l in listings)


def batches(listings: list[dict], size: int = BATCH_SIZE) -> list[list[dict]]:
    """Groups of at most `size` from one store and brand, in first-seen order."""
    groups: dict[tuple, list[dict]] = {}
    for l in listings:
        groups.setdefault((l.get("store") or "", catalog_store.brand_key(l.get("brand"))), []).append(l)
    return [g[i:i + size] for g in groups.values() for i in range(0, len(g), size)]


@dataclass
class BatchResult:
    listing_ids: list[str]
    model: str
    answers: dict[str, dict] = field(default_factory=dict)
    proposals: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                                                 "cache_write_tokens": 0, "web_searches": 0, "web_fetches": 0})
    requests: int = 0
    served_by: set = field(default_factory=set)
    tool_calls: dict = field(default_factory=dict)
    seconds: float = 0.0
    error: str | None = None
    trace: list = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        price = PRICES.get(self.model)
        if not price:
            return 0.0
        u = self.usage
        return (u["input_tokens"] * price["input"] + u["output_tokens"] * price["output"]
                + u["cache_read_tokens"] * price["cache_read"] + u["cache_write_tokens"] * price["cache_write"]
                ) / 1e6 + u["web_searches"] * WEB_SEARCH_USD

    def to_dict(self) -> dict:
        return {"listing_ids": self.listing_ids, "model": self.model, "answers": self.answers,
                "proposals": self.proposals, "usage": self.usage, "requests": self.requests,
                "served_by": sorted(self.served_by), "tool_calls": self.tool_calls,
                "seconds": round(self.seconds, 1), "cost_usd": round(self.cost_usd, 4), "error": self.error,
                "trace": self.trace}


def make_client():
    """The Anthropic client. The base URL is set explicitly: in Claude Code's sandbox
    ANTHROPIC_BASE_URL points at Claude Code's own proxy, which this must not use."""
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(base_url="https://api.anthropic.com", max_retries=4)


def _add_usage(result: BatchResult, usage) -> None:
    if usage is None:
        return
    u = result.usage
    u["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
    u["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
    u["cache_read_tokens"] += getattr(usage, "cache_read_input_tokens", 0) or 0
    u["cache_write_tokens"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
    server = getattr(usage, "server_tool_use", None)
    if server is not None:
        u["web_searches"] += getattr(server, "web_search_requests", 0) or 0
        u["web_fetches"] += getattr(server, "web_fetch_requests", 0) or 0


def _trace_turn(response) -> dict:
    """What the model did in one response, for reading a run back (no signatures)."""
    steps = []
    for b in response.content:
        kind = getattr(b, "type", "")
        if kind == "thinking" and getattr(b, "thinking", ""):
            steps.append({"thinking": b.thinking[:2000]})
        elif kind == "text" and b.text.strip():
            steps.append({"text": b.text})
        elif kind in ("tool_use", "server_tool_use"):
            steps.append({"call": b.name, "input": b.input})
    return {"stop_reason": response.stop_reason, "model": getattr(response, "model", None), "steps": steps}


def review_batch(ctx: review_tools.ReviewContext, listings: list[dict], model: str = DEFAULT_MODEL, *,
                 client=None, effort: str = "medium", web: bool = True, fallbacks: bool = True,
                 max_turns: int = MAX_TURNS, trace: bool = True) -> BatchResult:
    """Run one conversation over `listings` (all in ctx.queue) and return what it recorded.

    The history only ever grows: each response's content is appended unchanged, all of
    a turn's tool results go back in one user message, a paused server-tool turn is
    re-sent as it stands. A listing left unanswered at the end gets one reminder."""
    client = client or make_client()
    result = BatchResult(listing_ids=[l["id"] for l in listings], model=model)
    params = dict(
        model=model, max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
        tools=tool_definitions(web),
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": effort},
        cache_control={"type": "ephemeral"},      # caches the growing conversation too
    )
    if fallbacks:      # a declined request is re-run on Anthropic's recommended fallback model
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["extra_body"] = {"fallbacks": "default"}
    messages = [{"role": "user", "content": batch_prompt(listings, ctx.stores)}]
    reminded = False
    started = time.time()
    try:
        for _ in range(max_turns):
            response = client.beta.messages.create(messages=messages, **params)
            result.requests += 1
            result.served_by.add(getattr(response, "model", model))
            _add_usage(result, getattr(response, "usage", None))
            if trace:
                result.trace.append(_trace_turn(response))
            messages.append({"role": "assistant", "content": response.content})
            stop = response.stop_reason
            if stop == "refusal":
                details = getattr(response, "stop_details", None)
                result.error = f"refusal ({getattr(details, 'category', None)})"
                break
            if stop == "max_tokens":
                result.error = "max_tokens"
                break
            if stop == "pause_turn":
                continue
            if stop == "tool_use":
                results = []
                for b in response.content:
                    if getattr(b, "type", "") != "tool_use":
                        continue
                    result.tool_calls[b.name] = result.tool_calls.get(b.name, 0) + 1
                    out = review_tools.run_tool(ctx, b.name, b.input)
                    block = {"type": "tool_result", "tool_use_id": b.id, "content": out}
                    if _is_error(out):
                        block["is_error"] = True
                    results.append(block)
                if trace:
                    result.trace.append({"results": [r["content"][:600] for r in results]})
                messages.append({"role": "user", "content": results})
                continue
            missing = [i for i in result.listing_ids if i not in ctx.answers]
            if missing and not reminded:
                reminded = True
                messages.append({"role": "user", "content":
                                 f"No answer was recorded for {', '.join(missing)}. Call submit_labels for "
                                 f"each (confidence unsure when you can't tell)."})
                continue
            break
        else:
            result.error = f"stopped after {max_turns} requests"
    except Exception as e:  # noqa: BLE001 — one failed batch is reported, not fatal to a run
        result.error = f"{type(e).__name__}: {e}"
    result.seconds = time.time() - started
    result.answers = dict(ctx.answers)
    result.proposals = list(ctx.proposals)
    return result


def _is_error(out: str) -> bool:
    try:
        data = json.loads(out)
    except ValueError:
        return True
    return isinstance(data, dict) and ("error" in data or data.get("accepted") is False)
