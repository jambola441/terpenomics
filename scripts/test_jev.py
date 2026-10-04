"""Offline tests for jev.py — the transport is faked, nothing touches the network."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jev  # noqa: E402


def _ok(answers, tokens=100, cost=None):
    usage = {"input_tokens": tokens, "output_tokens": 10}
    if cost is not None:
        usage["cost"] = cost
    return 200, {"model": "typesafe/jev-1.13-20260917", "answers": answers, "usage": usage}, "", {}


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(jev, "_pause", lambda seconds: None)
    monkeypatch.setattr(jev, "_wait_for_pause", lambda: None)
    monkeypatch.setattr(jev, "_consecutive_failures", 0)
    monkeypatch.setattr(jev, "_breaker_open_until", 0.0)


class TestQuestions:
    def test_choice_needs_two_to_255_options(self):
        with pytest.raises(ValueError):
            jev.Choice("pick", {"only": None}).to_json()
        with pytest.raises(ValueError):
            jev.Choice("pick", {str(i): None for i in range(256)}).to_json()
        assert jev.Choice("pick", {"a": None, "b": "desc"}).to_json()["type"] == "choice"

    def test_score_needs_two_to_ten_levels(self):
        with pytest.raises(ValueError):
            jev.Score("rate", ["one"]).to_json()
        assert jev.Score("rate", ["low", "high"]).to_json()["criteria"] == ["low", "high"]

    def test_noul_criteria_optional(self):
        assert "criteria" not in jev.Noul("true?").to_json()
        assert jev.Noul("true?", {"true": "y", "false": "n"}).to_json()["criteria"]["true"] == "y"


class TestAsk:
    def test_parses_choice_and_cost(self, monkeypatch):
        monkeypatch.setattr(jev, "_post", lambda body, timeout: _ok(
            {"p": {"type": "choice", "choice": "a", "confidence": 0.6,
                   "probabilities": {"none": 0.2, "a": 0.8}}}, cost=0.00002))
        res = jev.ask({"name": "x"}, {"p": jev.Choice("pick", {"none": None, "a": None})})
        assert res.choice("p") == ("a", 0.8, {"none": 0.2, "a": 0.8})
        assert res.cost_usd == pytest.approx(0.00002)
        assert res.model.startswith("typesafe/jev-1.13")

    def test_cost_falls_back_to_list_price(self, monkeypatch):
        monkeypatch.setattr(jev, "_post", lambda body, timeout: _ok(
            {"t": {"type": "noul", "noul": 0.9}}, tokens=1_000_000))
        res = jev.ask("s", {"t": jev.Noul("q")})
        assert res.noul("t") == pytest.approx(0.9)
        assert res.cost_usd == pytest.approx(0.042)

    def test_sends_pinned_model_and_serialised_questions(self, monkeypatch):
        seen = {}

        def fake(body, timeout):
            seen.update(body)
            return _ok({"t": {"type": "noul", "noul": 0.5}})

        monkeypatch.setattr(jev, "_post", fake)
        jev.ask({"a": 1}, {"t": jev.Noul("q")})
        assert seen["model"] == jev.MODEL
        assert seen["questions"]["t"] == {"type": "noul", "instructions": "q"}
        assert seen["state"] == {"a": 1}

    def test_retries_rate_limit_then_succeeds(self, monkeypatch):
        calls = iter([
            (429, {"error": {"code": 429}}, "slow down", {"Retry-After": "1"}),
            (529, None, "overloaded", {}),
            _ok({"t": {"type": "noul", "noul": 0.1}}),
        ])
        monkeypatch.setattr(jev, "_post", lambda body, timeout: next(calls))
        assert jev.ask("s", {"t": jev.Noul("q")}).noul("t") == pytest.approx(0.1)

    def test_auth_failure_is_not_retried(self, monkeypatch):
        n = {"calls": 0}

        def fake(body, timeout):
            n["calls"] += 1
            return 401, {"error": {"code": 401}}, "bad key", {}

        monkeypatch.setattr(jev, "_post", fake)
        with pytest.raises(jev.JevError):
            jev.ask("s", {"t": jev.Noul("q")})
        assert n["calls"] == 1

    def test_only_in_flight_budget_402_is_transient(self):
        budget = {"error": {"metadata": {"limit_source": "openrouter_in_flight_budget"}}}
        assert jev._transient(402, budget)
        assert not jev._transient(402, {"error": {"message": "insufficient credits"}})
        assert jev._transient(429, None)
        assert not jev._transient(422, None)

    def test_gives_up_after_max_attempts(self, monkeypatch):
        monkeypatch.setattr(jev, "_post", lambda body, timeout: (503, None, "down", {}))
        with pytest.raises(jev.JevError, match="gave up"):
            jev.ask("s", {"t": jev.Noul("q")})


class TestAskMany:
    def test_order_preserved_and_failures_are_none(self, monkeypatch):
        def fake(body, timeout):
            if body["state"] == "bad":
                return 401, None, "no", {}
            return _ok({"t": {"type": "noul", "noul": float(body["state"])}}, cost=0.001)

        monkeypatch.setattr(jev, "_post", fake)
        usage = jev.Usage()
        out = jev.ask_many([("0.1", {"t": jev.Noul("q")}), ("bad", {"t": jev.Noul("q")}),
                            ("0.3", {"t": jev.Noul("q")})], workers=3, usage=usage)
        assert out[0].noul("t") == pytest.approx(0.1)
        assert out[1] is None
        assert out[2].noul("t") == pytest.approx(0.3)
        assert (usage.requests, usage.failures) == (2, 1)
        assert usage.cost_usd == pytest.approx(0.002)


class TestBreaker:
    def test_opens_after_consecutive_failures_and_fails_fast(self, monkeypatch):
        calls = {"n": 0}

        def fake(body, timeout):
            calls["n"] += 1
            return 401, None, "no", {}

        monkeypatch.setattr(jev, "_post", fake)
        for _ in range(jev.BREAKER_FAILURES):
            with pytest.raises(jev.JevError):
                jev.ask("s", {"t": jev.Noul("q")})
        assert jev.breaker_open()
        before = calls["n"]
        with pytest.raises(jev.JevError, match="circuit open"):
            jev.ask("s", {"t": jev.Noul("q")})
        assert calls["n"] == before   # no network call while open

    def test_success_resets_the_count(self, monkeypatch):
        seq = iter([(401, None, "no", {})] * (jev.BREAKER_FAILURES - 1)
                   + [_ok({"t": {"type": "noul", "noul": 0.5}})]
                   + [(401, None, "no", {})])
        monkeypatch.setattr(jev, "_post", lambda body, timeout: next(seq))
        for _ in range(jev.BREAKER_FAILURES - 1):
            with pytest.raises(jev.JevError):
                jev.ask("s", {"t": jev.Noul("q")})
        jev.ask("s", {"t": jev.Noul("q")})
        with pytest.raises(jev.JevError):
            jev.ask("s", {"t": jev.Noul("q")})
        assert not jev.breaker_open()
