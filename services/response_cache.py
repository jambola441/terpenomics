"""Shared answers to public catalogue reads, kept in memory for a few minutes.

A category or brand page is the same for every shopper and changes only when
the scrapers run, yet building one reads every listing in it: 2-2.7 s for a
category in production, then the encoding of a megabyte of JSON on top. So the
encoded answer is kept:

  - younger than FRESH_SECONDS: served as is;
  - younger than STALE_SECONDS: served as is, while a background thread
    rebuilds it, so nobody waits on the rebuild;
  - older, or missing: rebuilt before answering.

A page can therefore show stock up to FRESH_SECONDS old (a little more while
a rebuild runs). The listing page and placing an order still read live rows.

The API runs as one process (see the Dockerfile), so a dict is enough; a
second worker would simply keep its own copy.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Hashable

from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlmodel import Session

log = logging.getLogger(__name__)

FRESH_SECONDS = 300
STALE_SECONDS = 3600
# Every category plus the brands people actually open; each entry is the
# encoded body, about 1 MB for the biggest category.
MAX_ENTRIES = 300

# Browsers may reuse an answer briefly (Back, a second tab). Short, because the
# server copy is what keeps it fresh.
CACHE_CONTROL = "public, max-age=60"

_entries: "OrderedDict[Hashable, tuple[float, bytes]]" = OrderedDict()
_refreshing: set[Hashable] = set()
_lock = threading.Lock()


def _encode(value: Any) -> bytes:
    return json.dumps(jsonable_encoder(value), separators=(",", ":")).encode()


def _store(key: Hashable, body: bytes) -> None:
    with _lock:
        _entries[key] = (time.monotonic(), body)
        _entries.move_to_end(key)
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)


def _refresh_in_background(key: Hashable, build: Callable[[Session], Any]) -> None:
    with _lock:
        if key in _refreshing:
            return
        _refreshing.add(key)

    def run() -> None:
        # Imported here so tests can point the engine elsewhere first.
        from database import engine

        try:
            with Session(engine) as session:
                _store(key, _encode(build(session)))
        except Exception:
            # Gone (a 404 now) or the database hiccupped: drop the copy, and the
            # next request rebuilds it in the foreground and reports properly.
            log.warning("background rebuild of %r failed", key, exc_info=True)
            with _lock:
                _entries.pop(key, None)
        finally:
            with _lock:
                _refreshing.discard(key)

    threading.Thread(target=run, name=f"cache-refresh-{key!r}", daemon=True).start()


def cached_json(key: Hashable, build: Callable[[Session], Any], session: Session) -> Response:
    """The JSON answer for `key`, built with `build(session)` when there is no
    usable copy. Exceptions from `build` (an HTTPException 404, say) pass
    through and are not cached."""
    now = time.monotonic()
    with _lock:
        entry = _entries.get(key)
    if entry is not None:
        built_at, body = entry
        age = now - built_at
        if age < STALE_SECONDS:
            if age >= FRESH_SECONDS:
                _refresh_in_background(key, build)
            return Response(body, media_type="application/json", headers={"Cache-Control": CACHE_CONTROL})

    body = _encode(build(session))
    _store(key, body)
    return Response(body, media_type="application/json", headers={"Cache-Control": CACHE_CONTROL})


def clear() -> None:
    """Forget everything. For tests: the server's copies only age out."""
    with _lock:
        _entries.clear()
