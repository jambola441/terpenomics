"""The model registry, the request a gateway-routed model gets, and what a call costs — offline.

A reasoning model changes three things the registry used to take for granted: it needs
request parameters of its own (MODELS "params"), part of what it is billed for is
reasoning it never shows, and the gateway reports cache reads and writes at their own
rates. The usage block these tests fake has the shape OpenRouter returned for a live
call to openai/gpt-6-luna on 2026-10-06.
"""

import os
import sys
import threading
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import enrich  # noqa: E402


def gateway(content='[{"id": "0", "strain": "Blue Razz", "product_line": null}]',
            finish="stop", **usage):
    """A stand-in for the OpenAI SDK client: records every create() call it gets."""
    calls = []

    def create(**kw):
        calls.append(kw)
        u = {"prompt_tokens": 1496, "completion_tokens": 514,
             "prompt_tokens_details": NS(cached_tokens=0, cache_write_tokens=1493),
             "completion_tokens_details": NS(reasoning_tokens=386)}
        u.update(usage)
        return NS(choices=[NS(message=NS(content=content), finish_reason=finish)], usage=NS(**u))

    return NS(chat=NS(completions=NS(create=create))), calls


def ask(client, params=None, max_tokens=4096):
    return enrich._call_llm_once(client, "openrouter", "vendor/model", "system", [{"id": "0"}],
                                 90, max_tokens, "extract 1", threading.Lock(), params)


# --- the request ---------------------------------------------------------------

def test_a_request_carries_only_what_the_model_entry_asks_for():
    client, calls = gateway()
    ask(client)
    # No temperature, response_format, seed or reasoning knob unless an entry names it:
    # the models already in the registry are called exactly as they always were.
    assert sorted(calls[0]) == ["max_tokens", "messages", "model", "timeout"]


def test_a_models_params_ride_on_every_request():
    client, calls = gateway()
    ask(client, params={"reasoning_effort": "low"})
    assert calls[0]["reasoning_effort"] == "low" and calls[0]["max_tokens"] == 4096


def test_a_reply_cut_off_at_max_tokens_says_so(capsys):
    # A reasoning model can spend the whole budget thinking and answer nothing.
    client, _ = gateway(content="", finish="length")
    items, usage, retry = ask(client, max_tokens=512)
    assert items is None and retry is None and usage == dict(enrich._ZERO_USAGE)
    assert "cut off at max_tokens=512" in capsys.readouterr().err


# --- the usage ---------------------------------------------------------------

def test_cache_and_reasoning_tokens_are_split_out_of_the_plain_counts():
    client, _ = gateway()
    _, usage, _ = ask(client)
    assert usage == {"input_tokens": 3,                 # 1496 prompt - 1493 written to cache
                     "cache_write_tokens": 1493, "cache_read_tokens": 0,
                     "output_tokens": 514,              # reasoning is inside this already
                     "reasoning_tokens": 386}


def test_a_gateway_that_reports_no_details_is_read_as_plain_input_and_output():
    client, _ = gateway(prompt_tokens_details=None, completion_tokens_details=None)
    _, usage, _ = ask(client)
    assert usage == {"input_tokens": 1496, "output_tokens": 514, "cache_write_tokens": 0,
                     "cache_read_tokens": 0, "reasoning_tokens": 0}


# --- the cost ----------------------------------------------------------------

PER_CALL = {"input_tokens": 100_000, "output_tokens": 500_000, "cache_write_tokens": 1_000_000,
            "cache_read_tokens": 2_000_000, "reasoning_tokens": 300_000}


def priced(model, monkeypatch, tmp_path):
    """The cost enrich() reports for one edible row, whose two model calls (classify,
    then extract) each report PER_CALL."""
    def fake_llm(client, provider, api_model, system_prompt, payload, *rest):
        if isinstance(payload, dict):
            payload = payload["items"]
        if system_prompt in (enrich._CLASSIFY_PROMPT_HINTED, enrich._CLASSIFY_PROMPT_FRESH):
            out = {p["id"]: {"category": "edible", "subtype": "gummy", "variant": "100mg"} for p in payload}
        else:
            out = {p["id"]: {"strain": "Plain", "product_line": None} for p in payload}
        return out, dict(PER_CALL)

    monkeypatch.setenv("ENRICH_CLASSIFIER", "llm")
    monkeypatch.setattr(enrich, "_call_llm", fake_llm)
    monkeypatch.setattr(enrich, "_make_client", lambda cfg: object())
    monkeypatch.setattr(enrich, "_CACHE_DIR", tmp_path)
    row = {"name": "Gummies 10pk", "brand": "Testbrand", "category": "edible", "variant": "10mg",
           "sku": "a", "dispensary_slug": "test-store", "description": ""}
    usage = enrich.enrich([row], model=model, brand_examples={})
    assert usage["reasoning_tokens"] == 2 * PER_CALL["reasoning_tokens"]
    return usage["cost_usd"]


@pytest.mark.parametrize("model", ["luna", "haiku-5.5-or"])
def test_cache_tokens_are_billed_at_the_entrys_own_rates_and_reasoning_only_once(
        model, monkeypatch, tmp_path):
    # Both: 0.1M x $0.10 + 0.5M x $0.50 + 1M x $0.125 + 2M x $0.01 = $0.405 a call.
    # Billing the 0.3M reasoning tokens again would add $0.15 a call.
    assert priced(model, monkeypatch, tmp_path) == pytest.approx(2 * 0.405)


def test_an_entry_with_no_cache_rates_bills_cache_tokens_as_plain_input(monkeypatch, tmp_path):
    # haiku-or: (0.1M + 1M + 2M) x $1 + 0.5M x $5 = $5.60 a call — what it was billed
    # before cache tokens were split out of input_tokens.
    assert priced("haiku-or", monkeypatch, tmp_path) == pytest.approx(2 * 5.60)


# --- the registry ------------------------------------------------------------

def test_the_default_model_is_still_haiku():
    assert enrich.DEFAULT_MODEL == "haiku"


@pytest.mark.parametrize("model", sorted(enrich.MODELS))
def test_every_entry_pins_a_model_version(model):
    # A floating alias changes weights without notice, and every prompt and confidence
    # threshold here is calibrated against one version (evals/enrich/README.md).
    api_model = enrich.MODELS[model]["api_model"]
    assert not api_model.startswith("~") and not api_model.endswith("-latest"), api_model
