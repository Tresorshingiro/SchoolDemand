"""
Sign-in through the MINEDUC GIS portal (ArcGIS Enterprise, settings.portal_url).

The API sends the username and password to the portal's generateToken, then asks the portal who that token belongs
to (community/self). The portal token is used for these two requests only and never kept; the browser gets our own
session (services/auth.py). Neither the password nor the portal token is stored.

Single sign-on: on the portal's own site (gh.space.gov.rw/school) the dashboard gets the signed-in portal user's token
from the portal (oauth2/platformSelf with the dashboard's registered client ID) and hands it to the API, which asks
community/self who it belongs to (user_of_token) — the same check, without a password.
"""
from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from fastapi import HTTPException

from ..config import settings

UNREACHABLE = "The MINEDUC GIS portal could not be reached. Try again in a moment."
log = logging.getLogger("school_planning.portal")


@dataclass(frozen=True)
class PortalUser:
    username: str  # as the portal writes it
    full_name: str | None
    email: str | None


class WrongCredentials(Exception):
    """The portal refused the username and password (or the token)."""


INVALID_TOKEN = {401, 403, 498, 499}  # the portal's error codes for an expired, invalid or missing token


def _post(path: str, data: dict) -> dict:
    """POST to the portal's sharing API; the parsed JSON answer (the portal reports errors inside it, with HTTP 200)."""
    request = urllib.request.Request(
        f"{settings.portal_url.rstrip('/')}/sharing/rest/{path}",
        data=urllib.parse.urlencode({**data, "f": "json"}).encode(),
        headers={"Referer": settings.portal_referer, "Accept": "application/json"},
    )
    context = None if settings.portal_verify_ssl else ssl._create_unverified_context()  # noqa: S323 — opt-in setting
    try:
        with urllib.request.urlopen(request, timeout=settings.portal_timeout, context=context) as response:  # noqa: S310
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:  # the cause (firewall, DNS, certificate) in the log
        log.warning("portal %s/%s unreachable: %r", settings.portal_url, path, e)
        raise HTTPException(503, UNREACHABLE) from e


def sign_in(username: str, password: str) -> PortalUser:
    """The portal user with this username and password. WrongCredentials when the portal refuses them, 503 when it
    cannot be reached."""
    got = _post("generateToken", {"username": username, "password": password, "client": "referer",
                                  "referer": settings.portal_referer, "expiration": 5})
    token = got.get("token")
    if not token:
        raise WrongCredentials(" ".join((got.get("error") or {}).get("details") or []))
    try:
        return _self(token)
    except WrongCredentials:  # a token the portal has just made: its referer setting is wrong
        raise HTTPException(503, "The portal accepted the password but did not say who you are. Ask the developers to "
                                 "check PORTAL_REFERER.") from None


def user_of_token(token: str) -> PortalUser:
    """The portal user a portal token belongs to. WrongCredentials when the portal refuses the token (expired,
    invalid), 503 when it cannot be reached or does not answer who it is."""
    return _self(token)


def _self(token: str) -> PortalUser:
    """community/self: who the token belongs to (see user_of_token)."""
    me = _post("community/self", {"token": token})
    if me.get("username"):
        return PortalUser(me["username"], (me.get("fullName") or "").strip() or None,
                          (me.get("email") or "").strip() or None)
    error = me.get("error") or {}
    if error.get("code") in INVALID_TOKEN:
        raise WrongCredentials(error.get("message") or "Invalid token.")
    log.warning("portal %s/community/self did not name the user: %s", settings.portal_url, str(me)[:300])
    raise HTTPException(503, "The portal did not say who you are. Try again, or sign in with your username and password.")
