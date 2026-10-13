#!/usr/bin/env python3
"""
audit_judge.py — The admin audits' LLM judge: is this listing matched to the right
catalog entry? One Claude call per audit item (routes/admin/audits.py, scripts/audits.py).

The judge sees the evidence an admin would (scripts/audits.py evidence): the store's
listing (name, description, price, size field, store page, photo), the catalog entry it
is matched to (and that product's other sizes), the other listings matched to the same
entry (titles, prices), a few of the brand's entries it might be instead, and the flags
that brought it in. It answers right / wrong / unsure, a cause, a short explanation, and
a proposed fix in the proposal vocabulary (scripts/audits.py PROPOSAL_KINDS). Nothing it
says is applied: a person turns a proposed fix into a listing fix or a proposal.

The model is picked per audit run (MODELS); the key is ANTHROPIC_API_KEY. Every call's
tokens are counted and priced (PRICES) so the run records what it cost.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

# Per audit run: the admin picks one. Prices are $ per million tokens (input, output),
# Anthropic first-party rates (claude-api skill, 2026-10-06).
MODELS = {
    "claude-haiku-5-5":  {"label": "Haiku 5.5",  "price": (0.10, 0.50)},
    "claude-sonnet-5-5": {"label": "Sonnet 5.5", "price": (2.00, 10.00)},
    "claude-opus-5-5":   {"label": "Opus 5.5",   "price": (4.00, 20.00)},
}
DEFAULT_MODEL = "claude-sonnet-5-5"
# Opus 5.5 and Sonnet 5.5 decline some requests (stop_reason "refusal"); the server-side
# fallback re-runs a declined one on a model the API picks (beta, Claude API only).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")
MAX_TOKENS = 4000
EFFORT = "low"          # a classification over a page of evidence; raise if it misjudges

VERDICTS = ("right", "wrong", "unsure")
CAUSES = ("none", "wrong_product", "wrong_strain", "wrong_size", "wrong_line", "wrong_subtype",
          "catalog_missing_product", "catalog_missing_size", "catalog_duplicate",
          "store_price_error", "store_photo_error", "store_title_error", "other")
FIX_KINDS = ("none", "manual-match", "store-error", "add-product", "add-size", "rekey",
             "set-subtype", "deactivate", "add-example")

SYSTEM = """You audit how a cannabis marketplace matches dispensary listings to brand catalogs.

Each listing a dispensary sells has been matched to one entry of its brand's catalog: one product (category, subtype, product line, strain or flavour) in one size. You are shown the listing as the store wrote it, the catalog entry it is matched to, that product's other sizes, the other listings matched to the same entry, some other entries of the brand it could be instead, and the automatic flags (if any) that brought it to your attention.

Decide whether the match is right:
- "right": the listing is that product in that size.
- "wrong": it is a different product, strain, flavour, line, format or size, or the store's own data is wrong (a price far off what the same product costs elsewhere, a photo of another product, a title naming something else).
- "unsure": the evidence does not settle it. Prefer unsure to a guess.

Stores abbreviate, reorder words, add shelf codes and leave out the line or the size; a size field can disagree with the title (trust what the title, price and siblings agree on). Prices vary by store and sales happen: a price somewhat off is not by itself wrong, but a price that matches a different size of the product is strong evidence. An edible's mg is its total THC only.

Give a cause (none when right), a short explanation naming the evidence, and the fix you would propose:
- manual-match: the listing is another existing entry; give its entry_id from the candidates.
- store-error: the store's price, photo or title is wrong and the match is fine; say which in details.
- add-product / add-size: the catalog lacks the product or this size of it; give category, subtype, line, strain, size as the catalog would write them.
- rekey / set-subtype / deactivate: the catalog entry itself is filed wrong or duplicated; give entry_id and the corrected fields.
- add-example: the catalog is right but listings like this are read wrong; a brand example would teach the reader.
- none: nothing to fix.
Leave fields that do not apply empty."""

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "cause": {"type": "string", "enum": list(CAUSES)},
        "explanation": {"type": "string"},
        "fix": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(FIX_KINDS)},
                "entry_id": {"type": "string"},
                "category": {"type": "string"},
                "subtype": {"type": "string"},
                "line": {"type": "string"},
                "strain": {"type": "string"},
                "size": {"type": "string"},
                "details": {"type": "string"},
            },
            "required": ["kind", "entry_id", "category", "subtype", "line", "strain", "size", "details"],
            "additionalProperties": False,
        },
    },
    "required": ["verdict", "cause", "explanation", "fix"],
    "additionalProperties": False,
}


class JudgeUnavailable(RuntimeError):
    """No ANTHROPIC_API_KEY, or the anthropic package is missing."""


@dataclass
class Verdict:
    verdict: str
    cause: str
    explanation: str
    fix: dict
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw: dict = field(default_factory=dict)


def cost(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float:
    """$ for one call: cache reads at a tenth of the input price, writes at 1.25x."""
    p_in, p_out = MODELS.get(model, MODELS[DEFAULT_MODEL])["price"]
    return (input_tokens * p_in + cache_read * p_in * 0.1 + cache_write * p_in * 1.25
            + output_tokens * p_out) / 1_000_000


def make_client():
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        raise JudgeUnavailable("ANTHROPIC_API_KEY is not set: the LLM judge cannot run")
    try:
        import anthropic
    except ImportError as exc:                      # pragma: no cover - in requirements.txt
        raise JudgeUnavailable("the anthropic package is not installed") from exc
    return anthropic.Anthropic(max_retries=4)


def _photo_blocks(evidence: dict) -> list[dict]:
    out = []
    for label, url in (("The listing's photo:", (evidence.get("listing") or {}).get("image_url")),
                       ("The matched entry's photo:", (evidence.get("entry") or {}).get("image_url"))):
        if url and str(url).startswith("https://"):
            out += [{"type": "text", "text": label}, {"type": "image", "source": {"type": "url", "url": url}}]
    return out


def prompt(evidence: dict, with_photos: bool = True) -> list[dict]:
    """The user turn: the evidence as JSON, then the photos (by URL)."""
    text = ("Audit this match. Evidence (JSON):\n"
            + json.dumps(evidence, ensure_ascii=False, indent=1, default=str))
    return [{"type": "text", "text": text}] + (_photo_blocks(evidence) if with_photos else [])


def judge(evidence: dict, model: str = DEFAULT_MODEL, client=None) -> Verdict:
    """One item's verdict. A refusal or an unreadable answer is "unsure", with the
    reason in the explanation; an image the API cannot fetch is retried without photos."""
    if model not in MODELS:
        raise ValueError(f"unknown judge model {model!r} (one of {', '.join(MODELS)})")
    client = client or make_client()
    import anthropic

    def call(with_photos: bool):
        kwargs = dict(
            model=model, max_tokens=MAX_TOKENS,
            # The instructions are the same for every item: cached across a run.
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt(evidence, with_photos)}],
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if model in FALLBACK_MODELS:
            kwargs["extra_headers"] = {"anthropic-beta": FALLBACK_BETA}
            kwargs["extra_body"] = {"fallbacks": "default"}
        return client.messages.create(**kwargs)

    try:
        response = call(with_photos=True)
    except anthropic.BadRequestError:
        # Most often a photo URL the API could not fetch; the text is evidence enough.
        response = call(with_photos=False)
    usage = response.usage
    tin, tout = usage.input_tokens or 0, usage.output_tokens or 0
    cread = getattr(usage, "cache_read_input_tokens", 0) or 0
    cwrite = getattr(usage, "cache_creation_input_tokens", 0) or 0
    spent = cost(model, tin, tout, cread, cwrite)
    base = dict(model=getattr(response, "model", None) or model, input_tokens=tin + cread + cwrite,
                output_tokens=tout, cost_usd=spent)
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        return Verdict("unsure", "other", f"The judge declined ({getattr(details, 'category', None)}).",
                       {"kind": "none"}, **base)
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        verdict, cause = data["verdict"], data["cause"]
        if verdict not in VERDICTS or cause not in CAUSES:
            raise ValueError(f"verdict {verdict!r}, cause {cause!r}")
    except (ValueError, KeyError, TypeError) as exc:
        return Verdict("unsure", "other", f"Unreadable answer ({exc}; stop {response.stop_reason}).",
                       {"kind": "none"}, **base, raw={"text": text[:2000]})
    fix = {k: v for k, v in (data.get("fix") or {}).items() if v not in ("", None)}
    fix.setdefault("kind", "none")
    return Verdict(verdict, cause, data.get("explanation") or "", fix, **base, raw=data)
