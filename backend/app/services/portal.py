"""
Sign-in through the MINEDUC GIS portal (ArcGIS Enterprise, settings.portal_url).

The API sends the username and password to the portal's generateToken, then asks the portal who that token belongs
to (community/self). The portal token is used for these two requests only and never kept; the browser gets our own
session (services/auth.py). Neither the password nor the portal token is stored.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from fastapi import HTTPException

from ..config import settings

UNREACHABLE = "The MINEDUC GIS portal could not be reached. Try again in a moment."


@dataclass(frozen=True)
class PortalUser:
    username: str  # as the portal writes it
    full_name: str | None
    email: str | None


class WrongCredentials(Exception):
    """The portal refused the username and password."""


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
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise HTTPException(503, UNREACHABLE) from e


def sign_in(username: str, password: str) -> PortalUser:
    """The portal user with this username and password. WrongCredentials when the portal refuses them, 503 when it
    cannot be reached."""
    got = _post("generateToken", {"username": username, "password": password, "client": "referer",
                                  "referer": settings.portal_referer, "expiration": 5})
    token = got.get("token")
    if not token:
        raise WrongCredentials(" ".join((got.get("error") or {}).get("details") or []))
    me = _post("community/self", {"token": token})
    if not me.get("username"):
        raise HTTPException(503, UNREACHABLE)
    return PortalUser(me["username"], (me.get("fullName") or "").strip() or None, (me.get("email") or "").strip() or None)
