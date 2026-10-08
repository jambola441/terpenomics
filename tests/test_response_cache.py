"""services/response_cache: fresh copies are served without a rebuild, stale
ones are served while a rebuild runs, and failures are never cached."""
import json
import threading

import pytest
from fastapi import HTTPException

from services import response_cache


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(response_cache.time, "monotonic", c)
    return c


def _body(response):
    return json.loads(response.body)


def test_a_fresh_copy_is_served_without_building_again(clock):
    calls = []

    def build(session):
        calls.append(session)
        return {"n": len(calls)}

    first = response_cache.cached_json("k", build, session="s1")
    clock.now += response_cache.FRESH_SECONDS - 1
    second = response_cache.cached_json("k", build, session="s2")

    assert _body(first) == _body(second) == {"n": 1}
    assert calls == ["s1"]
    assert second.headers["cache-control"] == response_cache.CACHE_CONTROL


def test_a_stale_copy_is_served_while_it_is_rebuilt(clock, monkeypatch):
    monkeypatch.setattr("database.engine", object())

    class FakeSession:
        def __init__(self, engine):
            pass

        def __enter__(self):
            return "background"

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(response_cache, "Session", FakeSession)
    rebuilt = threading.Event()
    version = {"v": 1}

    def build(session):
        if session == "background":
            rebuilt.set()
        return {"v": version["v"]}

    response_cache.cached_json("k", build, session="request")
    version["v"] = 2
    clock.now += response_cache.FRESH_SECONDS + 1

    # Served at once from the old copy...
    assert _body(response_cache.cached_json("k", build, session="request")) == {"v": 1}
    # ...while the background thread builds the new one.
    assert rebuilt.wait(5)
    for _ in range(50):
        if _body(response_cache.cached_json("k", build, session="request")) == {"v": 2}:
            break
        threading.Event().wait(0.02)
    assert _body(response_cache.cached_json("k", build, session="request")) == {"v": 2}


def test_a_copy_past_the_stale_limit_is_rebuilt_before_answering(clock):
    version = {"v": 1}
    response_cache.cached_json("k", lambda s: {"v": version["v"]}, session=None)
    version["v"] = 2
    clock.now += response_cache.STALE_SECONDS + 1
    assert _body(response_cache.cached_json("k", lambda s: {"v": version["v"]}, session=None)) == {"v": 2}


def test_errors_pass_through_and_are_not_cached(clock):
    def missing(session):
        raise HTTPException(status_code=404, detail="brand not found")

    with pytest.raises(HTTPException):
        response_cache.cached_json("k", missing, session=None)
    # Once the brand exists, the next request sees it.
    assert _body(response_cache.cached_json("k", lambda s: {"ok": True}, session=None)) == {"ok": True}


def test_keys_are_separate(clock):
    a = response_cache.cached_json(("category", "flower", True), lambda s: {"c": "flower"}, session=None)
    b = response_cache.cached_json(("category", "flower", False), lambda s: {"c": "all"}, session=None)
    assert _body(a) == {"c": "flower"} and _body(b) == {"c": "all"}
