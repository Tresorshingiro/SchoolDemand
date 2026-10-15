"""The portal client (services/portal.py) with the portal's answers stubbed: no network, no database."""
import urllib.error

import pytest
from fastapi import HTTPException

from app.services import portal

SIGN_IN = portal.sign_in  # the real one: conftest swaps the module's for a fake portal once the tests start


def answers(token_answer: dict, self_answer: dict | None = None):
    calls = []

    def post(path: str, data: dict) -> dict:
        calls.append((path, data))
        return token_answer if path == "generateToken" else self_answer

    return post, calls


def test_signed_in_user_comes_from_community_self(monkeypatch):
    post, calls = answers({"token": "abc", "expires": 1}, {"username": "JDoe", "fullName": " Jane Doe ", "email": ""})
    monkeypatch.setattr(portal, "_post", post)
    assert SIGN_IN("jdoe", "secret") == portal.PortalUser("JDoe", "Jane Doe", None)
    (p1, d1), (p2, d2) = calls
    assert p1 == "generateToken" and d1["username"] == "jdoe" and d1["password"] == "secret" and d1["client"] == "referer"
    assert p2 == "community/self" and d2 == {"token": "abc"}  # the token goes in the body, not the address


def test_refused_password(monkeypatch):
    post, calls = answers({"error": {"code": 400, "message": "Unable to generate token.",
                                     "details": ["Invalid username or password."]}})
    monkeypatch.setattr(portal, "_post", post)
    with pytest.raises(portal.WrongCredentials, match="Invalid username or password"):
        SIGN_IN("jdoe", "wrong")
    assert len(calls) == 1


def test_unreachable_portal(monkeypatch):
    def fail(*args, **kwargs):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(portal.urllib.request, "urlopen", fail)
    with pytest.raises(HTTPException) as e:
        SIGN_IN("jdoe", "secret")
    assert e.value.status_code == 503
