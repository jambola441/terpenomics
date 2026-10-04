"""
jev.py — Typed decisions from Jev, TypeSafe's System One model, over OpenRouter.

Jev does not generate text. It takes a state plus typed questions and returns, for
each question, an answer drawn from the options we supplied together with calibrated
probabilities:

  choice   pick one option from a set we define (up to 255)    -> choice, probabilities, confidence
  noul     is this statement true?                              -> probability 0..1
  score    rate against 2-10 ordered levels                     -> score, probabilities, confidence

That shape is why it fits the catalog work and not the extraction work. Matching a
listing to "which of these catalog products is it, or none" is a closed-set decision
with an explicit abstain option, and the probability is exactly the gate CATALOG.md
asked for ("No match must be a first-class outcome with a confidence threshold").
Extracting a strain is open-ended string generation, which Jev cannot do — that stays
with the LLM or, better, with a catalog that already names the product.

Measured from this repo (2026-10-04, three identical calls): the same answer every
time with probabilities moving +/-0.02, 350-720 ms, $0.00002 per call. Haiku's
run-to-run variance is the reason README.md calls consistency the binding constraint;
a decision model that returns near-identical probabilities for identical input is the
property that matters most here.

Documented weak spots (docs.typesafe.ai/model-jaggedness/jev-1.13), and what this
module's callers do about them:
  - arithmetic / counting      sizes and pack math stay in code (sizes.py)
  - leans toward first option  put the abstain option first, so the bias is caution
  - large irrelevant state     send the listing name, brand, category, size — not
                               a 2,000-character sales description
  - literal reading            spell the criterion out in each option's description

Transport: OpenRouter's System One endpoint, which implements TypeSafe's request and
response shape and authenticates with the OPENROUTER_API_KEY this repo already uses.
Stdlib only, like db_http.py, so it runs anywhere the pipeline runs.

    from jev import Choice, ask
    res = ask({"name": "..."}, {"product": Choice("Which product?", {"none": "...", "a": "..."})})
    res.answers["product"]["choice"], res.answers["product"]["probabilities"]
"""

from __future__ import annotations

import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Pinned, never an alias. Confidence thresholds are calibrated against one model
# version; `~typesafe/jev-latest` would move them without notice, the same trap
# README.md records for floating DeepSeek aliases.
MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
BASE_URL = os.environ.get("JEV_BASE_URL", "https://openrouter.ai/api").rstrip("/")
ENDPOINT = f"{BASE_URL}/v1/systemone"
# OpenRouter list price for typesafe/jev-1.13. Output tokens are free. Used only when
# a response omits usage.cost.
PRICE_PER_INPUT_TOKEN = 0.042 / 1e6

TIMEOUT_SECONDS = float(os.environ.get("JEV_TIMEOUT", "30"))
MAX_ATTEMPTS = 5
# 402 is only transient when OpenRouter's in-flight budget is full (checked below);
# 529 is TypeSafe's "overloaded".
_RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}
USER_AGENT = "terpenomics-jev/1.0"


class JevError(RuntimeError):
    """A Jev request failed for a reason retrying will not fix."""


def _load_key() -> str | None:
    import db_http  # noqa: F401  (loads the repo-root .env on import — one parser)
    for name in ("JEV_API_KEY", "OPENROUTER_API_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    return None


def available() -> bool:
    """True when a key is configured. Callers degrade to deterministic-only without one."""
    return bool(_load_key())


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

@dataclass
class Choice:
    """One option from a fixed set. `criteria` maps option -> description (or None).

    Dict order is the order Jev sees, and Jev leans toward the first option — put the
    option you would rather it default to (usually the abstain one) first.
    """
    instructions: str
    criteria: dict[str, Any]

    def to_json(self) -> dict:
        if not 2 <= len(self.criteria) <= 255:
            raise ValueError(f"a Choice needs 2-255 options, got {len(self.criteria)}")
        return {"type": "choice", "instructions": self.instructions, "criteria": self.criteria}


@dataclass
class Noul:
    """A yes/no question, answered as P(yes)."""
    instructions: str
    criteria: dict[str, str] | None = None   # optional {"true": ..., "false": ...}

    def to_json(self) -> dict:
        q: dict[str, Any] = {"type": "noul", "instructions": self.instructions}
        if self.criteria:
            q["criteria"] = self.criteria
        return q


@dataclass
class Score:
    """A position on 2-10 ordered levels, described in words."""
    instructions: str
    criteria: list[str]

    def to_json(self) -> dict:
        if not 2 <= len(self.criteria) <= 10:
            raise ValueError(f"a Score needs 2-10 levels, got {len(self.criteria)}")
        return {"type": "score", "instructions": self.instructions, "criteria": self.criteria}


Question = Choice | Noul | Score


@dataclass
class Result:
    answers: dict[str, dict]
    model: str
    input_tokens: int
    cost_usd: float
    latency_s: float

    def choice(self, key: str) -> tuple[str | None, float, dict[str, float]]:
        """(choice, probability of that choice, full distribution)."""
        a = self.answers.get(key) or {}
        probs = {k: float(v) for k, v in (a.get("probabilities") or {}).items()}
        pick = a.get("choice")
        return pick, probs.get(pick, 0.0), probs

    def noul(self, key: str) -> float | None:
        a = self.answers.get(key) or {}
        return None if a.get("noul") is None else float(a["noul"])


@dataclass
class Usage:
    """Thread-safe running total for a batch, so a run can print what it cost."""
    requests: int = 0
    failures: int = 0
    input_tokens: int = 0
    cost_usd: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, r: Result | None) -> None:
        with self._lock:
            if r is None:
                self.failures += 1
                return
            self.requests += 1
            self.input_tokens += r.input_tokens
            self.cost_usd += r.cost_usd

    def summary(self) -> str:
        return (f"jev: {self.requests} call(s), {self.failures} failed, "
                f"{self.input_tokens:,} input tokens, ${self.cost_usd:.4f}")


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

# One shared pause for every worker: when the gateway says slow down, all threads
# wait together instead of each hammering it with its own retry.
_pause_until = 0.0
_pause_lock = threading.Lock()


def _wait_for_pause() -> None:
    while True:
        with _pause_lock:
            delay = _pause_until - time.monotonic()
        if delay <= 0:
            return
        time.sleep(min(delay, 5.0))


def _pause(seconds: float) -> None:
    global _pause_until
    with _pause_lock:
        _pause_until = max(_pause_until, time.monotonic() + seconds)


# Circuit breaker. During an outage every call would otherwise spend its full retry
# budget (five attempts with backoff) before giving up, and a fleet import would stall
# for the length of the outage. After BREAKER_FAILURES consecutive failures, calls fail
# immediately for BREAKER_SECONDS; callers already treat a failed call as "no
# decision", which for matching is "no match" — the safe outcome.
BREAKER_FAILURES = 5
BREAKER_SECONDS = 600.0
_consecutive_failures = 0
_breaker_open_until = 0.0
_breaker_lock = threading.Lock()


def _record(ok: bool) -> None:
    global _consecutive_failures, _breaker_open_until
    with _breaker_lock:
        if ok:
            _consecutive_failures = 0
            return
        _consecutive_failures += 1
        if _consecutive_failures >= BREAKER_FAILURES:
            _breaker_open_until = time.monotonic() + BREAKER_SECONDS


def breaker_open() -> bool:
    with _breaker_lock:
        return time.monotonic() < _breaker_open_until


def _post(body: dict, timeout: float) -> tuple[int, dict | None, str, dict]:
    key = _load_key()
    if not key:
        raise JevError("no OPENROUTER_API_KEY (or JEV_API_KEY) configured")
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8")
            return r.status, json.loads(text), text, dict(r.headers)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        return e.code, parsed, text, dict(e.headers or {})


def _transient(status: int, parsed: dict | None) -> bool:
    if status in _RETRY_STATUS:
        return True
    if status == 402:
        # Only the in-flight budget is worth waiting out; any other 402 means the
        # credits or the key limit ran out, and retrying would just repeat it.
        meta = ((parsed or {}).get("error") or {}).get("metadata") or {}
        return meta.get("limit_source") == "openrouter_in_flight_budget"
    return False


def ask(state: Any, questions: dict[str, Question | dict], *, model: str = MODEL,
        timeout: float = TIMEOUT_SECONDS) -> Result:
    """One System One request: one state, any number of questions, one round trip.

    Questions are evaluated in parallel and in isolation against the same state, so
    asking several at once costs input tokens, not latency.
    """
    if breaker_open():
        raise JevError("circuit open after repeated failures — skipping Jev for now")
    body = {
        "model": model,
        "state": state,
        "questions": {k: (q.to_json() if hasattr(q, "to_json") else q) for k, q in questions.items()},
    }
    last = ""
    for attempt in range(MAX_ATTEMPTS):
        _wait_for_pause()
        t0 = time.monotonic()
        try:
            status, parsed, text, headers = _post(body, timeout)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            status, parsed, text, headers = 0, None, str(e), {}
        if status == 200 and parsed and "answers" in parsed:
            _record(True)
            usage = parsed.get("usage") or {}
            tokens = int(usage.get("input_tokens") or 0)
            cost = usage.get("cost")
            return Result(
                answers=parsed["answers"], model=parsed.get("model", model),
                input_tokens=tokens,
                cost_usd=float(cost) if cost is not None else tokens * PRICE_PER_INPUT_TOKEN,
                latency_s=time.monotonic() - t0,
            )
        last = f"{status}: {text[:300]}"
        if status and not _transient(status, parsed):
            _record(False)
            raise JevError(last)
        if attempt + 1 < MAX_ATTEMPTS:
            try:
                retry_after = float(headers.get("Retry-After") or headers.get("retry-after") or 0)
            except ValueError:
                retry_after = 0.0
            _pause(retry_after or min(30.0, 2 ** attempt) + random.random())
    _record(False)
    raise JevError(f"gave up after {MAX_ATTEMPTS} attempts — last {last}")


def ask_many(jobs: Iterable[tuple[Any, dict[str, Question | dict]]], *, workers: int = 8,
             usage: Usage | None = None, model: str = MODEL,
             on_error: Callable[[int, Exception], None] | None = None) -> list[Result | None]:
    """Run many requests concurrently. Results come back in input order; a request that
    fails for good yields None rather than sinking the batch — the caller treats it as
    "no decision", which for matching means "no match", the safe outcome.

    OpenRouter lists 80 requests/s for this model; 8 workers at ~0.4 s each is ~20/s,
    comfortably under it without any client-side rate limiter.
    """
    jobs = list(jobs)
    out: list[Result | None] = [None] * len(jobs)
    usage = usage or Usage()

    def run(i: int) -> None:
        state, questions = jobs[i]
        try:
            out[i] = ask(state, questions, model=model)
        except Exception as e:  # noqa: BLE001 — one bad item must not stop the batch
            if on_error:
                on_error(i, e)
        usage.add(out[i])

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(run, range(len(jobs))))
    return out
