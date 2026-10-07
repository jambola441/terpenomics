"""Tests for review_agent.py: the conversation loop against a scripted client, offline;
and the review eval's scoring (evals/review/run_review.py)."""

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import review_agent as ra  # noqa: E402
import review_tools as rt  # noqa: E402

CATALOGS = {"grön": {"brand_name": "Grön", "source_method": "storefront", "entries": [
    {"id": "e1", "catalog_id": "c1", "product_key": "k1", "name": "Baja Blaze Mega", "category": "edible",
     "subtype": "gummy", "strain": "Baja Blaze", "product_line": "Mega", "variant": "100mg"}]}}
QUEUED = {"id": "q1", "brand": "Grön", "name": "Grön - Baja Blaze Mega", "category": "edible", "size_field": "",
          "price_cents": 1800, "description": "100mg THC per gummy", "url": None, "store": "s1",
          "first_pass": {"category": "edible", "subtype": "gummy", "strain": "Baja Blaze", "product_line": None,
                         "variant": "100mg"},
          "p": {"category": 1.0, "subtype": 1.0, "strain": 0.45, "product_line": 0.6, "size": 1.0}}
LABELS = {"listing_id": "q1", "category": "edible", "subtype": "gummy", "strain": "Baja Blaze",
          "product_line": "Mega", "size": "100mg", "confidence": "sure", "evidence": "Catalog entry e1."}


def ctx():
    return rt.ReviewContext(catalogs=CATALOGS, listings=[QUEUED]).for_batch({"q1": QUEUED})


def response(stop, *blocks, searches=0):
    return NS(stop_reason=stop, content=list(blocks), model="claude-sonnet-5-5", stop_details=NS(category="cyber"),
              usage=NS(input_tokens=100, output_tokens=50, cache_read_input_tokens=1000, cache_creation_input_tokens=0,
                       server_tool_use=NS(web_search_requests=searches, web_fetch_requests=0)))


def call(name, args, id_="t1"):
    return NS(type="tool_use", id=id_, name=name, input=args)


def text(t):
    return NS(type="text", text=t)


class FakeClient:
    """Plays back responses; keeps a copy of each request's messages."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        return self.responses.pop(0)


def test_a_batch_records_the_labels_it_submits_and_what_it_cost():
    client = FakeClient(response("tool_use", call("search_catalog", {"brand": "Grön", "query": "baja blaze"})),
                        response("tool_use", call("submit_labels", LABELS, "t2"), searches=1),
                        response("end_turn", text("q1: nothing to check")))
    r = ra.review_batch(ctx(), [QUEUED], client=client)
    assert r.error is None and r.requests == 3
    assert r.answers["q1"]["product_line"] == "Mega"
    assert r.tool_calls == {"search_catalog": 1, "submit_labels": 1}
    assert round(r.cost_usd, 6) == round(3 * (100 * 2 + 50 * 10 + 1000 * 0.2) / 1e6 + 0.01, 6)
    second = client.requests[1]["messages"]
    assert second[1]["role"] == "assistant" and second[2]["content"][0]["tool_use_id"] == "t1"
    assert json.loads(second[2]["content"][0]["content"])["entries"][0]["entry_id"] == "e1"


def test_the_history_only_grows_and_a_paused_turn_is_sent_again_as_it_stands():
    paused = response("pause_turn", NS(type="server_tool_use", id="s1", name="web_search", input={"query": "gron"}))
    client = FakeClient(paused, response("tool_use", call("submit_labels", LABELS)), response("end_turn", text("ok")))
    ra.review_batch(ctx(), [QUEUED], client=client)
    msgs = [req["messages"] for req in client.requests]
    assert all(a == b[:len(a)] for a, b in zip(msgs, msgs[1:]))
    assert msgs[1][-1] == {"role": "assistant", "content": paused.content}      # no "continue" message


def test_requests_carry_strict_tools_web_tools_caching_and_the_fallback():
    client = FakeClient(response("tool_use", call("submit_labels", LABELS)), response("end_turn", text("ok")))
    ra.review_batch(ctx(), [QUEUED], "claude-opus-5-5", client=client)
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"] == {"effort": "medium"}
    assert all(t.get("strict") for t in req["tools"] if "input_schema" in t)
    assert {t["name"] for t in req["tools"]} >= {"web_search", "web_fetch", "submit_labels"}
    assert req["system"][0]["cache_control"] and req["cache_control"] == {"type": "ephemeral"}
    assert req["extra_body"] == {"fallbacks": "default"} and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert "effect rule" in req["system"][0]["text"] and "preroll: no subtype" in req["system"][0]["text"]


def test_an_unanswered_listing_gets_one_reminder():
    client = FakeClient(response("end_turn", text("done")), response("end_turn", text("still done")))
    r = ra.review_batch(ctx(), [QUEUED], client=client)
    assert r.requests == 2 and r.answers == {}
    assert "No answer was recorded for q1" in client.requests[1]["messages"][-1]["content"]


def test_a_rejected_answer_goes_back_as_an_error_and_a_refusal_stops_the_batch():
    bad = {**LABELS, "category": "gummies"}
    client = FakeClient(response("tool_use", call("submit_labels", bad)), response("refusal"))
    r = ra.review_batch(ctx(), [QUEUED], client=client)
    assert client.requests[1]["messages"][-1]["content"][0]["is_error"] is True
    assert r.error == "refusal (cyber)" and r.answers == {}


def test_the_prompt_shows_the_first_pass_and_how_sure_it_was():
    out = ra.listing_text(QUEUED, "hold-up-roll-up")
    assert "store: hold-up-roll-up" in out and "price: $18.00" in out
    assert "strain Baja Blaze (45% sure)" in out and "product line none (60% sure)" in out


def test_listings_are_batched_by_store_and_brand_five_at_most():
    ls = [{"id": f"a{i}", "brand": "Grön", "store": "s1"} for i in range(7)] + \
         [{"id": "b0", "brand": "GRÖN", "store": "s2"}, {"id": "c0", "brand": "Wyld", "store": "s1"}]
    assert [[l["id"] for l in b] for b in ra.batches(ls)] == [
        ["a0", "a1", "a2", "a3", "a4"], ["a5", "a6"], ["b0"], ["c0"]]


def _run_review():
    path = Path(__file__).resolve().parent.parent / "evals" / "review" / "run_review.py"
    spec = importlib.util.spec_from_file_location("run_review", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_review_scoring_counts_what_the_pipeline_would_write():
    rr = _run_review()
    case = {"id": "x", "listing": {"category": "preroll"}, "slice": "flagged",
            "expect": {"category": "preroll", "subtype": "single", "strain": "ATF", "variant": "3g"},
            "accept": {"strain": ["ATF", "Alaskan Thunder Fuck"]},
            "first_pass": {"category": "preroll", "subtype": "pack", "strain": "ATF", "variant": "2.5g"},
            "today": {"category": "preroll", "strain": "Alaskan Thunder Fuck", "variant": "2.5g"}}
    assert set(rr.wanted(case)) == {"category", "strain", "variant"}      # a pre-roll keeps no subtype
    sure = {"category": "preroll", "subtype": None, "strain": "alaskan thunder fuck ", "product_line": None,
            "size": "3g", "confidence": "sure", "evidence": "x"}
    s = rr.score_case(case, sure)
    assert s["all_applied"] and not s["all_first"] and s["fields"]["strain"]["ok_today"]
    unsure = rr.score_case(case, {**sure, "confidence": "unsure"})    # the first pass stands
    assert unsure["fields"]["variant"]["ok_agent"] and not unsure["fields"]["variant"]["ok_applied"]
    totals = rr.summarize([s, unsure])["totals"]
    assert (totals["fields"], totals["fixed"], totals["broke"], totals["unsure"]) == (6, 1, 0, 1)
