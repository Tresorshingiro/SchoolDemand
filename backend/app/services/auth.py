"""
Sign-in with a MINEDUC GIS portal account (username and password, checked by the portal: services/portal.py).

Every portal user can sign in. The first sign-in adds the person to `users` as an administrator; after that an
administrator can make them a viewer or disable them in the admin portal, and the portal keeps their password. A
successful sign-in creates a session: a random token sent to the browser in an HttpOnly cookie, stored in the database
only as its SHA-256, so a copy of the database does not let anyone sign in. Signing out deletes the session. Repeated
wrong passwords for one username are refused for a while (before they reach the portal).
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..config import settings
from ..db import get_session
from . import portal
from .audit import audit

COOKIE = "sp_session"
MAX_FAILURES, FAILURE_WINDOW = 10, 15 * 60  # wrong passwords per username, seconds
NEW_USER_ROLE = "admin"  # every portal user is an administrator at first sign-in


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- wrong-password throttle (per API process)
_failures: dict[str, deque[float]] = defaultdict(deque)
_failures_lock = threading.Lock()


def _recent_failures(key: str, now: float) -> deque[float]:
    q = _failures[key]
    while q and q[0] < now - FAILURE_WINDOW:
        q.popleft()
    return q


def find_user(session: Session, username: str) -> M.User | None:
    """The account of a portal username (the portal ignores case, so do we)."""
    return session.scalar(select(M.User).where(func.lower(M.User.username) == username.strip().lower()))


def authenticate(session: Session, username: str, password: str) -> M.User:
    """The user whose portal username and password these are, added on first sign-in. 401 for a wrong password, 403
    for an account disabled here, 429 after too many wrong passwords, 503 when the portal cannot be reached."""
    username = username.strip()
    key = username.lower()
    now = time.time()
    with _failures_lock:
        if len(_recent_failures(key, now)) >= MAX_FAILURES:
            raise HTTPException(429, "Too many wrong passwords. Wait 15 minutes, then try again.")
    try:
        p = portal.sign_in(username, password)
    except portal.WrongCredentials:
        with _failures_lock:
            _recent_failures(key, now).append(now)
        raise HTTPException(401, "Wrong username or password.") from None
    with _failures_lock:
        _failures.pop(key, None)

    user = find_user(session, p.username)
    if user is None:
        user = M.User(username=p.username, role=NEW_USER_ROLE, is_active=True)
        session.add(user)
        session.flush()
        audit(session, user, "user.first_sign_in", p.username, {"role": NEW_USER_ROLE})
    elif not user.is_active:
        raise HTTPException(403, "Your account is disabled in School Demand. Ask an administrator to enable it.")
    user.username, user.full_name, user.email = p.username, p.full_name or user.full_name, p.email
    return user


# ---------------------------------------------------------------- sessions
def start_session(session: Session, user: M.User, remember: bool) -> tuple[str, int | None]:
    """Create a session; returns (cookie token, cookie max-age in seconds or None for a browser-session cookie)."""
    lifetime = timedelta(days=settings.remember_days) if remember else timedelta(hours=settings.session_hours)
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session.execute(delete(M.UserSession).where(M.UserSession.expires_at < now))  # housekeeping
    session.add(M.UserSession(user_id=user.id, token_hash=_token_hash(token), expires_at=now + lifetime))
    user.last_login_at = now
    session.commit()
    return token, int(lifetime.total_seconds()) if remember else None


def end_session(session: Session, token: str | None) -> None:
    if token:
        session.execute(delete(M.UserSession).where(M.UserSession.token_hash == _token_hash(token)))
        session.commit()


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" if settings.session_cookie_secure is None else settings.session_cookie_secure


def _cross_site(request: Request) -> bool:
    """Cookie usable inside another site's frame (SameSite=None; Secure; Partitioned): needs HTTPS."""
    secure = _secure(request)
    return secure if settings.session_cookie_cross_site is None else settings.session_cookie_cross_site and secure


def _cross_site_cookie(value: str, max_age: int | None) -> str:
    """Written by hand: Starlette writes Partitioned only on Python 3.14+."""
    age = [] if max_age is None else [f"Max-Age={max_age}"]
    return "; ".join([f"{COOKIE}={value}", *age, "Path=/", "HttpOnly", "Secure", "SameSite=None", "Partitioned"])


def set_cookie(request: Request, response, token: str, max_age: int | None) -> None:
    if _cross_site(request):
        response.headers.append("set-cookie", _cross_site_cookie(token, max_age))
        return
    response.set_cookie(COOKIE, token, max_age=max_age, httponly=True, secure=_secure(request), samesite="lax", path="/")


def clear_cookie(request: Request, response) -> None:
    if _cross_site(request):  # removed with the same attributes it was set with
        response.headers.append("set-cookie", _cross_site_cookie('""', 0))
        return
    response.delete_cookie(COOKIE, path="/")


# Requests that change something must come from the dashboard's own code (api.ts sends this header). A form or a
# script on another site cannot add it to a request that carries the session cookie, so a cookie that is also sent
# from other sites (SameSite=None) cannot be used to act on someone's behalf.
CSRF_HEADER = "X-Requested-With"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def csrf_refused(request: Request) -> bool:
    return (request.method not in SAFE_METHODS and COOKIE in request.cookies
            and request.headers.get(CSRF_HEADER) != "fetch")


def end_user_sessions(session: Session, user_id: int) -> None:
    """Sign a user out everywhere."""
    session.execute(delete(M.UserSession).where(M.UserSession.user_id == user_id))


def session_user(request: Request, session: Session) -> M.User | None:
    """The active user of the request's session cookie, or None."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    return session.scalar(
        select(M.User).join(M.UserSession, M.UserSession.user_id == M.User.id)
        .where(M.UserSession.token_hash == _token_hash(token), M.UserSession.expires_at > func.now(), M.User.is_active)
    )


def current_user(request: Request, session: Session = Depends(get_session)) -> M.User:
    """FastAPI dependency: the signed-in user, or 401."""
    user = session_user(request, session)
    if user is None:
        raise HTTPException(401, "Please sign in.")
    return user


def require_admin(user: M.User = Depends(current_user)) -> M.User:
    """FastAPI dependency: the signed-in administrator; 403 for viewers."""
    if user.role != "admin":
        raise HTTPException(403, "Only an administrator can do this.")
    return user
