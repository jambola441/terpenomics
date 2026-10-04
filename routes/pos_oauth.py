"""The OAuth callback a POS redirects the partner's browser to.

Unauthenticated by necessity -- it is a redirect from Square, not a call from
the admin UI -- so the signed `state` is what proves the request started from an
admin's /start call, and which partner it is for.

Configure the POS app's redirect URL as <API base>/pos/oauth/<provider>/callback.
After connecting, the browser is sent to POS_OAUTH_RETURN_URL (the admin UI)
with ?pos=connected&connection_id=... or ?pos=error&reason=...; with that unset,
the result is returned as JSON.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session

from connectors.base import ConnectorError, PosConnector
from connectors.oauth_state import InvalidState, read_state
from connectors.registry import PROVIDERS
from connectors.sync import ConnectError, complete_oauth
from database import get_session
from routes.pos_common import connector_factory

log = logging.getLogger("pos-oauth")

router = APIRouter(prefix="/pos", tags=["pos"])


def _return_url(origin: str) -> Optional[str]:
    """Where to send the browser: the admin Partner Stores page, or the partner's
    own /partner dashboard when they started the connect themselves."""
    admin = os.getenv("POS_OAUTH_RETURN_URL")
    if origin != "partner":
        return admin
    explicit = os.getenv("POS_PARTNER_RETURN_URL")
    if explicit:
        return explicit
    if admin:
        parts = urlsplit(admin)
        return f"{parts.scheme}://{parts.netloc}/partner"
    return None


def _finish(params: dict, status: int = 200, origin: str = "admin"):
    return_url = _return_url(origin)
    if return_url:
        sep = "&" if "?" in return_url else "?"
        return RedirectResponse(f"{return_url}{sep}{urlencode(params)}", status_code=302)
    return JSONResponse(params, status_code=status)


@router.get("/oauth/{provider}/callback")
def oauth_callback(
    provider: str,
    state: Optional[str] = Query(default=None),
    code: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
    factory: Callable[[str], PosConnector] = Depends(connector_factory),
):
    if provider not in PROVIDERS:
        return _finish({"pos": "error", "reason": "unknown provider"}, 404)

    # Read the state first, even on the error path: Square sends it back on a
    # "deny" too, and it says which page to return the browser to.
    partner_id, origin, state_error = None, "admin", None
    if state:
        try:
            partner_id, origin = read_state(state, provider)
        except InvalidState as e:
            state_error = str(e)

    if error:
        # The partner clicked "deny", or the POS refused the request.
        return _finish({"pos": "error", "reason": error_description or error}, 400, origin)
    if not state or not code:
        return _finish({"pos": "error", "reason": "missing code or state"}, 400, origin)
    if state_error:
        return _finish({"pos": "error", "reason": f"invalid state: {state_error}"}, 400, origin)

    try:
        connection = complete_oauth(session, factory(provider), partner_id, code)
    except ConnectError as e:
        return _finish({"pos": "error", "reason": str(e)}, 409, origin)
    except ConnectorError as e:
        log.error("%s OAuth for partner %s failed: %s", provider, partner_id, e)
        return _finish({"pos": "error", "reason": f"{provider} rejected the connection"}, 502, origin)

    return _finish(
        {"pos": "connected", "connection_id": str(connection.id), "partner_id": str(partner_id)},
        origin=origin,
    )
