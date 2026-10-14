"""The admin audits' worker side (scripts/audits.py, audit_worker.py, audit_judge.py) and
the reading examples' move to the database (catalog_reading, import_reading_examples).

Supabase's REST API is stood in for by an in-memory table store (FakeRest) and the
Claude client by a fake: nothing here reaches the network.
"""
import json
import random
import urllib.parse
from types import SimpleNamespace

import pytest

import audit_judge
import audit_worker
import audits
import catalog_fix
import catalog_reading
import db_http
import import_reading_examples


class FakeRest:
    """The PostgREST calls the audits make, over dicts: eq, lt, is, in, a simple or=(),
    select (columns ignored), order, limit."""

    def __init__(self, tables=None):
        self.tables = {k: [dict(r) for r in v] for k, v in (tables or {}).items()}

    def _match(self, row, query):
        for part in filter(None, query.split("&")):
            key, _, val = part.partition("=")
            val = urllib.parse.unquote(val)
            if key in ("select", "order", "limit", "offset"):
                continue
            if key == "or":
                terms = val.strip("()").split(",")
                if not any(self._match(row, t.replace(".", "=", 1)) for t in terms):
                    return False
                continue
            have = row.get(key)
            if val.startswith("eq."):
                if str(have) != val[3:]:
                    return False
            elif val.startswith("ilike."):
                if str(have or "").lower() != val[6:].lower():
                    return False
            elif val.startswith("lt."):
                if have is None or str(have) >= val[3:]:
                    return False
            elif val == "is.true":
                if have is not True:
                    return False
            elif val == "is.false":
                if have is not False:
                    return False
            elif val == "is.null":
                if have is not None:
                    return False
            elif val == "not.is.null":
                if have is None:
                    return False
            elif val.startswith("in.("):
                if str(have) not in [v.strip('"') for v in val[4:-1].split(",")]:
                    return False
            else:
                raise AssertionError(f"filter not modelled: {part}")
        return True

    def select(self, table, query=""):
        rows = [dict(r) for r in self.tables.get(table, []) if self._match(r, query)]
        for part in query.split("&"):
            if part.startswith("limit="):
                rows = rows[:int(part[6:])]
        return rows

    def select_all(self, table, query="", page=1000):
        return self.select(table, query)

    def insert(self, table, rows):
        rows = rows if isinstance(rows, list) else [rows]
        self.tables.setdefault(table, []).extend(dict(r) for r in rows)
        return [dict(r) for r in rows]

    def update(self, table, query, changes):
        out = []
        for r in self.tables.get(table, []):
            if self._match(r, query):
                r.update(changes)
                out.append(dict(r))
        return out


@pytest.fixture
def rest(monkeypatch):
    def install(tables=None):
        fake = FakeRest(tables)
        for name in ("select", "select_all", "insert", "update"):
            monkeypatch.setattr(db_http, name, getattr(fake, name))
        return fake
    return install


def catalog():
    def e(id, variant, **kw):
        return {"id": id, "catalog_id": "c1", "name": "Yuzu Lemon", "strain": "Yuzu Lemon", "category": "edible",
                "subtype": "gummy", "product_line": None, "variant": variant, "product_key": "lb:edible:gummy::yuzulemon",
                "is_active": True, **kw}
    return {"id": "c1", "brand_name": "Camino", "brand_slug": "camino", "source_method": "listings_bootstrap",
            "entries": [e("e20", "20pk 100mg"), e("e10", "10pk 50mg"),
                        {**e("pom", "20pk 100mg"), "name": "Pomegranate", "strain": "Pomegranate",
                         "product_key": "lb:edible:gummy::pomegranate"}]}


def listing(id, name, entry, method="attributes", price=2000, store="s1"):
    return {"id": id, "dispensary_id": store, "scraped_name": name, "scraped_brand": "Camino",
            "scraped_category": "edible", "variant": None, "size": None, "description": "Tasty",
            "reading": {"strain": "Yuzu Lemon"}, "catalog_entry_id": entry, "catalog_match_method": method,
            "catalog_match_confidence": 1.0, "last_seen_at": None, "price_cents": price, "url": f"https://s/{id}",
            "image_url": None}


# ---------------------------------------------------------------------------
# Building a run
# ---------------------------------------------------------------------------

def test_items_flag_the_odd_price_and_sample_the_rest(monkeypatch):
    rows = [listing(f"l{i}", f"Camino Yuzu Lemon 20pk {i}", "e20", store=f"s{i}") for i in range(5)]
    rows.append(listing("cheap", "Camino Yuzu Lemon 20pk", "e20", price=900, store="s9"))
    rows.append(listing("review", "Camino ???", None, method="review_unsure"))
    stores = {f"s{i}": {"id": f"s{i}", "name": f"Store {i}"} for i in range(10)}
    cats = {"camino": catalog()}
    monkeypatch.setattr(audits, "load_brand", lambda brand, catalogs: (cats["camino"], rows, stores))
    items = audits.items_for_brand("Camino", cats, 3, {}, set(), random.Random(1))
    flagged = [i for i in items if i["source"] == "flag"]
    assert [i["listing_id"] for i in flagged] == ["cheap"]
    assert {f["kind"] for f in flagged[0]["flags"]} >= {"price-outlier"}
    sampled = [i for i in items if i["source"] == "sample"]
    assert len(sampled) == 3 and all(i["listing_id"].startswith("l") for i in sampled)
    ev = flagged[0]["evidence"]
    assert ev["entry"]["id"] == "e20" and [e["id"] for e in ev["product_other_sizes"]] == ["e10"]
    assert ev["siblings_total"] == 5 and ev["listing"]["store"] == "Store 9"
    # Settled listings (judged right, or a store error, before) are not flagged again.
    again = audits.items_for_brand("Camino", cats, 0, {}, {"cheap"}, random.Random(1))
    assert again == []


def test_build_run_stores_items_and_judges_when_a_model_is_set(rest, monkeypatch):
    fake = rest({"audit_runs": [{"id": "r1", "brands": ["Camino"], "sample_size": 2, "judge_model": "claude-haiku-5-5",
                                 "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}],
                 "audit_items": []})
    monkeypatch.setattr(audits.catalog_store, "load_all", lambda source="auto": {"camino": catalog()})
    monkeypatch.setattr(audits.data_health, "load_dismissals", lambda: {})
    monkeypatch.setattr(audits, "items_for_brand", lambda *a, **k: [
        {"id": "i1", "listing_id": "l1", "brand": "Camino", "source": "sample", "flags": [], "evidence": {"x": 1},
         "created_at": "t"}])
    judged = []
    monkeypatch.setattr(audits, "judge_run", lambda run_id: judged.append(run_id))
    audits.build_run("r1")
    assert fake.tables["audit_items"][0]["run_id"] == "r1"
    assert fake.tables["audit_runs"][0]["total_items"] == 1 and fake.tables["audit_runs"][0]["status"] == "judging"
    assert judged == ["r1"]


def test_judge_run_records_verdicts_and_spend(rest, monkeypatch):
    fake = rest({"audit_runs": [{"id": "r1", "judge_model": "claude-sonnet-5-5", "input_tokens": 0,
                                 "output_tokens": 0, "cost_usd": 0}],
                 "audit_items": [{"id": "i1", "run_id": "r1", "evidence": {}, "verdict": None, "created_at": "1"},
                                 {"id": "i2", "run_id": "r1", "evidence": {}, "verdict": "right", "created_at": "2"}]})
    monkeypatch.setattr(audit_judge, "judge", lambda ev, model, client: audit_judge.Verdict(
        "wrong", "wrong_size", "the price is the 10pk's", {"kind": "manual-match", "entry_id": "e10"}, model,
        1000, 100, 0.003))
    out = audits.judge_run("r1", client=object())
    run = fake.tables["audit_runs"][0]
    assert out["judged"] == 2 and run["status"] == "ready" and run["judged_items"] == 2
    assert (run["input_tokens"], run["output_tokens"], run["cost_usd"]) == (1000, 100, 0.003)
    item = fake.tables["audit_items"][0]
    assert item["verdict"] == "wrong" and item["judged_by"] == "llm:claude-sonnet-5-5"
    assert item["proposed_fix"]["entry_id"] == "e10"


def test_judge_run_without_a_key_leaves_the_run_for_manual_judging(rest, monkeypatch):
    fake = rest({"audit_runs": [{"id": "r1", "judge_model": "claude-opus-5-5"}], "audit_items": []})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = audits.judge_run("r1")
    assert "ANTHROPIC_API_KEY" in out["error"] and fake.tables["audit_runs"][0]["status"] == "ready"


def test_judge_run_whose_calls_all_fail_is_failed(rest, monkeypatch):
    fake = rest({"audit_runs": [{"id": "r1", "judge_model": "claude-haiku-5-5"}],
                 "audit_items": [{"id": "i1", "run_id": "r1", "evidence": {}, "verdict": None}]})

    def boom(*a, **k):
        raise RuntimeError("401 invalid x-api-key")
    import audit_judge
    monkeypatch.setattr(audit_judge, "judge", boom)
    out = audits.judge_run("r1", client=object())
    assert out["errors"] and fake.tables["audit_runs"][0]["status"] == "failed"


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------

def test_catalog_edit_maps_params_to_a_plan_edit():
    assert audits.catalog_edit("add-size", {"entry": "e20", "size": "5pk", "why": "x"}) == \
        {"op": "add-size", "entry": "e20", "size": "5pk"}
    assert audits.catalog_edit("rekey", {"entries": ["a"], "line": ""}) == {"op": "rekey", "entries": ["a"], "line": ""}
    with pytest.raises(audits.Refused):
        audits.catalog_edit("manual-match", {})


def test_measure_a_catalog_proposal_runs_the_plan_through_measure_data(monkeypatch):
    seen = {}

    def fake_measure(plan, **kw):
        seen["writes"] = plan.writes
        return {"trusted_before": 3, "trusted_after": 4}
    monkeypatch.setattr(catalog_fix, "measure_data", fake_measure)
    m = audits.measure({"kind": "add-size", "brand": "Camino", "params": {"entry": "e20", "size": "5pk 25mg"}},
                       catalogs={"camino": catalog()})
    assert m == {"trusted_before": 3, "trusted_after": 4}
    assert seen["writes"][0][0] == "insert" and seen["writes"][0][3]["variant"] == "5pk 25mg"
    with pytest.raises(audits.Refused, match="already comes in"):
        audits.measure({"kind": "add-size", "brand": "Camino", "params": {"entry": "e20", "size": "10pk 50mg"}},
                       catalogs={"camino": catalog()})


def test_measure_proposal_records_a_refusal(rest):
    fake = rest({"audit_proposals": [{"id": "p1", "kind": "manual-match", "brand": "Camino",
                                      "params": {"listing_id": "nope", "entry": "e20"}}], "listings": []})
    audits.measure_proposal("p1")
    p = fake.tables["audit_proposals"][0]
    assert p["status"] == "failed" and "no listing" in p["error"]


def test_apply_manual_match_writes_rematches_and_logs(rest, monkeypatch):
    fake = rest({"listings": [listing("l1", "Camino Yuzu", "e20")], "audit_log": [],
                 "audit_proposals": [{"id": "p1", "kind": "manual-match", "brand": "Camino", "status": "approved",
                                      "decided_by": "me", "params": {"listing_id": "l1", "entry": "e10"}}]})
    monkeypatch.setattr(audits.catalog_store, "load_all", lambda source="auto": {"camino": catalog()})
    import rematch_brand
    monkeypatch.setattr(rematch_brand, "rematch", lambda brand, write_changes: {
        "listings": 1, "trusted_before": 1, "trusted_after": 1, "written": 0, "stored_readings": True, "changes": {}})
    out = audits.apply_proposal("p1")
    assert fake.tables["listings"][0]["catalog_entry_id"] == "e10"
    assert fake.tables["listings"][0]["catalog_match_method"] == "manual"
    assert fake.tables["audit_proposals"][0]["status"] == "applied"
    assert out["writes"][0]["before"]["catalog_entry_id"] == "e20"
    (log,) = fake.tables["audit_log"]
    assert log["action"] == "apply:manual-match" and log["actor"] == "me"


def test_apply_refuses_an_unapproved_proposal():
    with pytest.raises(audits.Refused, match="not approved"):
        audits.apply({"id": "p", "kind": "add-size", "brand": "Camino", "status": "measured", "params": {}})


def test_apply_catalog_proposal_writes_the_plan_and_syncs(rest, monkeypatch):
    fake = rest({"listings": [], "audit_log": [],
                 "audit_proposals": [{"id": "p1", "kind": "add-size", "brand": "Camino", "status": "approved",
                                      "params": {"entry": "e20", "size": "5pk 25mg"}}]})
    monkeypatch.setattr(audits.catalog_store, "load_all", lambda source="auto": {"camino": catalog()})
    monkeypatch.setattr(catalog_fix, "for_edit", lambda c: c)
    written = []
    monkeypatch.setattr(catalog_fix, "write", lambda plan: written.append(plan))
    import rematch_brand
    monkeypatch.setattr(rematch_brand, "rematch", lambda brand, write_changes: {
        "listings": 0, "trusted_before": 0, "trusted_after": 0, "written": 0, "stored_readings": True, "changes": {}})
    audits.apply_proposal("p1")
    assert len(written) == 1 and fake.tables["audit_proposals"][0]["status"] == "applied"
    assert fake.tables["audit_proposals"][0]["result"]["writes"][0]["op"] == "insert"


def test_example_proposals_need_the_table_filled_first(rest):
    rest({"reading_examples": []})
    with pytest.raises(audits.Refused, match="import_reading_examples"):
        audits._examples_after("add-example", {"listing": "x", "entry": {"strain": "Yuzu Lemon"}}, catalog())


def test_add_example_measures_with_the_new_example(rest, monkeypatch):
    rest({"reading_examples": [{"id": "x1", "brand_slug": "other", "position": 0, "listing": "o",
                                "entry": {"strain": "O"}, "is_active": True}]})
    seen = {}

    def fake_measure(plan, examples_after=None, **kw):
        seen["after"] = examples_after
        return {"ok": True}
    monkeypatch.setattr(catalog_fix, "measure_data", fake_measure)
    params = {"listing": "Camino Pom 20ct", "entry": {"strain": "Pomegranate", "size": "20pk 100mg"}}
    assert audits.measure({"kind": "add-example", "brand": "Camino", "params": params},
                          catalogs={"camino": catalog()}) == {"ok": True}
    assert seen["after"]["camino"] == [{"listing": "Camino Pom 20ct", "entry": params["entry"]}]
    assert seen["after"]["other"][0]["listing"] == "o"
    with pytest.raises(audits.Refused, match="names 2 active entries"):
        audits.measure({"kind": "add-example", "brand": "Camino",
                        "params": {"listing": "x", "entry": {"strain": "Yuzu Lemon"}}}, catalogs={"camino": catalog()})


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------

def test_worker_claims_runs_and_records_failures(rest, monkeypatch):
    fake = rest({"audit_jobs": [
        {"id": "j1", "kind": "measure_proposal", "payload": {"proposal_id": "p1"}, "status": "queued",
         "attempts": 0, "created_at": "1"},
        {"id": "j2", "kind": "build_run", "payload": {"run_id": "r1"}, "status": "queued", "attempts": 0,
         "created_at": "2"}],
        "audit_runs": [{"id": "r1"}], "audit_proposals": [{"id": "p1"}]})
    ran = []
    monkeypatch.setattr(audits, "measure_proposal", lambda pid: ran.append(pid))

    def boom(run_id):
        raise RuntimeError("no catalog")
    monkeypatch.setattr(audits, "build_run", boom)
    assert audit_worker.main(["--drain"]) == 0
    jobs = {j["id"]: j for j in fake.tables["audit_jobs"]}
    assert ran == ["p1"] and jobs["j1"]["status"] == "done" and jobs["j1"]["attempts"] == 1
    assert jobs["j2"]["status"] == "failed" and "no catalog" in jobs["j2"]["error"]
    assert fake.tables["audit_runs"][0]["status"] == "failed"
    assert audit_worker.claim() is None


# ---------------------------------------------------------------------------
# The judge (Claude client mocked)
# ---------------------------------------------------------------------------

class FakeMessages:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def create(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _response(payload=None, stop="end_turn", text=None):
    body = text if text is not None else json.dumps(payload)
    return SimpleNamespace(stop_reason=stop, stop_details=SimpleNamespace(category="cyber"), model="m",
                           content=[SimpleNamespace(type="text", text=body)],
                           usage=SimpleNamespace(input_tokens=3000, output_tokens=400,
                                                 cache_read_input_tokens=1000, cache_creation_input_tokens=0))


ANSWER = {"verdict": "wrong", "cause": "wrong_size", "explanation": "priced like the 10pk",
          "fix": {"kind": "manual-match", "entry_id": "e10", "category": "", "subtype": "", "line": "",
                  "strain": "", "size": "", "details": ""}}


def test_judge_parses_the_structured_answer_and_prices_it():
    msgs = FakeMessages([_response(ANSWER)])
    ev = {"listing": {"image_url": "https://img/x.jpg"}, "entry": {"image_url": None}}
    v = audit_judge.judge(ev, "claude-haiku-5-5", SimpleNamespace(messages=msgs))
    assert (v.verdict, v.cause, v.fix) == ("wrong", "wrong_size", {"kind": "manual-match", "entry_id": "e10"})
    assert v.input_tokens == 4000 and v.output_tokens == 400
    assert v.cost_usd == pytest.approx((3000 * 0.10 + 1000 * 0.01 + 400 * 0.50) / 1e6)
    call = msgs.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["output_config"]["format"]["type"] == "json_schema"
    assert any(b["type"] == "image" for b in call["messages"][0]["content"])
    assert "extra_body" not in call                     # no server-side fallback for Haiku


def test_judge_opts_opus_and_sonnet_into_fallbacks_and_retries_without_photos():
    import anthropic
    import httpx
    bad = anthropic.BadRequestError("image fetch failed", response=httpx.Response(
        400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")), body=None)
    msgs = FakeMessages([bad, _response(ANSWER)])
    ev = {"listing": {"image_url": "https://img/x.jpg"}}
    v = audit_judge.judge(ev, "claude-opus-5-5", SimpleNamespace(messages=msgs))
    assert v.verdict == "wrong"
    assert msgs.calls[1]["extra_body"] == {"fallbacks": "default"}
    assert not any(b["type"] == "image" for b in msgs.calls[1]["messages"][0]["content"])


def test_judge_turns_a_refusal_or_bad_answer_into_unsure():
    v = audit_judge.judge({}, "claude-sonnet-5-5", SimpleNamespace(messages=FakeMessages([_response(stop="refusal", text="")])))
    assert v.verdict == "unsure" and "declined" in v.explanation
    v = audit_judge.judge({}, "claude-sonnet-5-5", SimpleNamespace(messages=FakeMessages([_response(text="nope")])))
    assert v.verdict == "unsure" and "Unreadable" in v.explanation
    with pytest.raises(ValueError):
        audit_judge.judge({}, "gpt-4", SimpleNamespace(messages=FakeMessages([])))


def test_cost_per_model_order():
    costs = [audit_judge.cost(m, 4500, 600) for m in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")]
    assert costs == sorted(costs) and costs[2] == pytest.approx((4500 * 4 + 600 * 20) / 1e6)


# ---------------------------------------------------------------------------
# Reading examples in the database
# ---------------------------------------------------------------------------

def test_examples_read_from_the_table_with_file_fallback(rest, monkeypatch):
    monkeypatch.setenv("READING_EXAMPLES", "db")
    rest({"reading_examples": [
        {"brand_slug": "camino", "position": 1, "listing": "second", "entry": {"strain": "B"}, "is_active": True},
        {"brand_slug": "camino", "position": 0, "listing": "first", "size_field": "10mg", "entry": {"strain": "A"},
         "is_active": True},
        {"brand_slug": "camino", "position": 2, "listing": "gone", "entry": {"strain": "C"}, "is_active": False}]})
    catalog_reading.reload_examples()
    try:
        assert catalog_reading._examples() == {"camino": [
            {"listing": "first", "entry": {"strain": "A"}, "size_field": "10mg"},
            {"listing": "second", "entry": {"strain": "B"}}]}
        with catalog_reading.examples_override({"x": []}):
            assert catalog_reading._examples() == {"x": []}
        rest({"reading_examples": []})                  # empty table: the file
        catalog_reading.reload_examples()
        assert catalog_reading._examples() == catalog_reading.examples_from_file()
    finally:
        monkeypatch.setenv("READING_EXAMPLES", "file")
        catalog_reading.reload_examples()


def test_import_round_trips_the_file(rest):
    fake = rest({"reading_examples": []})
    assert import_reading_examples.main(["--write"]) == 0
    assert catalog_reading.examples_from_rows(fake.tables["reading_examples"]) == catalog_reading.examples_from_file()
    assert import_reading_examples.main(["--write"]) == 2         # refused: already filled
