"""A recording Metrc API client.

Every call is captured as a CallRecord carrying exactly the fields the Metrc
proficiency evaluation workbook asks for: result code, license, object id,
last-modified, tag, the full request URL, and the minified JSON.

Auth follows the Getting Started docs: HTTP basic, where the username is the
integrator (vendor) key and the password is the industry user key. The one
exception is POST /sandbox/v2/integrator/setup, which authenticates with the
vendor key alone via an x-metrc-key header.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable
from urllib.parse import urlencode

import requests

from .config import MetrcConfig

# Metrc rejects request bodies carrying more than this many objects with a 413.
MAX_OBJECTS_PER_REQUEST = 10


def minify(value: Any) -> str:
    """Render JSON the way the workbook demands: one line, no padding."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return value.strip()
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


@dataclass
class CallRecord:
    """One API call, in the shape the evaluation workbook wants it."""

    step: str = ""
    sheet: str = ""
    method: str = ""
    path: str = ""
    url: str = ""
    status: int | None = None
    license_number: str = ""
    request_body: Any = None
    response_body: Any = None
    error: str = ""
    duration_ms: int = 0
    attempts: int = 1
    # Verification columns, filled in by the step that made the call.
    object_ids: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    last_modified: str = ""
    names: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == 200

    @property
    def endpoint(self) -> str:
        return f"{self.method} {self.path}"

    def evidence(self) -> str:
        """What goes in the 'JSON Body Or Response' column.

        Writes carry their request body; reads carry their response.
        """
        if self.method in {"POST", "PUT", "DELETE"} and self.request_body is not None:
            return minify(self.request_body)
        return minify(self.response_body)

    def to_dict(self) -> dict:
        return asdict(self)


class MetrcError(RuntimeError):
    def __init__(self, record: "CallRecord"):
        self.record = record
        detail = record.error or minify(record.response_body)
        super().__init__(f"{record.endpoint} -> {record.status}: {detail[:400]}")


class MetrcClient:
    def __init__(self, config: MetrcConfig, recorder: "Recorder | None" = None):
        self.config = config
        self.recorder = recorder
        self.session = requests.Session()

    # -- auth ---------------------------------------------------------------
    def _basic_auth_header(self) -> str:
        self.config.require("vendor_key", "user_key")
        raw = f"{self.config.vendor_key}:{self.config.user_key}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _vendor_only_header(self) -> dict:
        self.config.require("vendor_key")
        return {"x-metrc-key": self.config.vendor_key}

    # -- core ---------------------------------------------------------------
    def call(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: Any = None,
        license_number: str | None = None,
        step: str = "",
        sheet: str = "",
        vendor_only: bool = False,
        raise_on_error: bool = True,
    ) -> CallRecord:
        if isinstance(body, list) and len(body) > MAX_OBJECTS_PER_REQUEST:
            raise ValueError(
                f"{method} {path}: {len(body)} objects exceeds Metrc's limit of "
                f"{MAX_OBJECTS_PER_REQUEST} per request (would return HTTP 413)"
            )

        params = dict(params or {})
        # Most endpoints are facility-scoped and refuse to work without this.
        lic = license_number if license_number is not None else self.config.license_number
        if lic and "licenseNumber" not in params and not path.startswith("/sandbox/v2/integrator"):
            params["licenseNumber"] = lic

        url = self.config.base_url + path
        if params:
            # urlencode handles the +offset -> %2B escaping the docs warn about.
            url = f"{url}?{urlencode(params)}"

        headers = {"Content-Type": "application/json"}
        if vendor_only:
            headers.update(self._vendor_only_header())
        else:
            headers["Authorization"] = self._basic_auth_header()

        record = CallRecord(
            step=step,
            sheet=sheet,
            method=method.upper(),
            path=path,
            url=url,
            license_number=lic or "",
            request_body=body,
        )

        started = time.time()
        for attempt in range(1, self.config.max_retries + 1):
            record.attempts = attempt
            try:
                resp = self.session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    data=minify(body) if body is not None else None,
                    timeout=self.config.timeout,
                )
            except requests.RequestException as exc:
                record.error = f"{type(exc).__name__}: {exc}"
                if attempt == self.config.max_retries:
                    break
                time.sleep(2 ** attempt)
                continue

            record.status = resp.status_code
            record.error = ""
            text = resp.text.strip()
            if text:
                try:
                    record.response_body = resp.json()
                except ValueError:
                    record.response_body = text
            else:
                record.response_body = None

            if resp.status_code == 429 and attempt < self.config.max_retries:
                wait = float(resp.headers.get("Retry-After") or self.config.default_backoff)
                time.sleep(wait)
                continue
            break

        record.duration_ms = int((time.time() - started) * 1000)
        record.object_ids = _extract_ids(record.response_body)

        if self.recorder is not None:
            self.recorder.add(record)

        if raise_on_error and not record.ok:
            raise MetrcError(record)
        return record

    # -- verbs --------------------------------------------------------------
    def get(self, path: str, **kw) -> CallRecord:
        return self.call("GET", path, **kw)

    def post(self, path: str, **kw) -> CallRecord:
        return self.call("POST", path, **kw)

    def put(self, path: str, **kw) -> CallRecord:
        return self.call("PUT", path, **kw)

    def delete(self, path: str, **kw) -> CallRecord:
        return self.call("DELETE", path, **kw)


def _extract_ids(payload: Any) -> list:
    """Pull created-object ids out of a v2 response.

    v2 POSTs return {"Ids": [...]} in request order; GETs return objects or a
    paginated {"Data": [...]} envelope.
    """
    if payload is None:
        return []
    if isinstance(payload, dict):
        if isinstance(payload.get("Ids"), list):
            return [i for i in payload["Ids"] if i is not None]
        if "Id" in payload:
            return [payload["Id"]]
        if isinstance(payload.get("Data"), list):
            return [row["Id"] for row in payload["Data"] if isinstance(row, dict) and "Id" in row]
    if isinstance(payload, list):
        return [row["Id"] for row in payload if isinstance(row, dict) and "Id" in row]
    return []


def rows(payload: Any) -> list:
    """Normalise a v2 read into a plain list, unwrapping the pagination envelope."""
    if isinstance(payload, dict) and isinstance(payload.get("Data"), list):
        return payload["Data"]
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    return []


def first(payload: Any, **match: Any) -> dict | None:
    """First row matching every key/value in `match` (None means 'any')."""
    for row in rows(payload):
        if not isinstance(row, dict):
            continue
        if all(row.get(k) == v for k, v in match.items() if v is not None):
            return row
    return None
