"""
Sign-in with email and password.

Passwords are stored as argon2id hashes. A successful sign-in creates a session: a random token sent to the browser
in an HttpOnly cookie, stored in the database only as its SHA-256, so a copy of the database does not let anyone sign
in. Signing out deletes the session. Repeated wrong passwords for one email are refused for a while.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..config import settings
from ..db import get_session

COOKIE = "sp_session"
MIN_PASSWORD = 8
MAX_FAILURES, FAILURE_WINDOW = 10, 15 * 60  # wrong passwords per email, seconds

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not a real password")  # verified for unknown emails so both answers take as long


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"The password must have at least {MIN_PASSWORD} characters.")
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- wrong-password throttle (per API process)
_failures: dict[str, deque[float]] = defaultdict(deque)
_failures_lock = threading.Lock()


def _recent_failures(email: str, now: float) -> deque[float]:
    q = _failures[email]
    while q and q[0] < now - FAILURE_WINDOW:
        q.popleft()
    return q


def authenticate(session: Session, email: str, password: str) -> M.User:
    """The active user with this email and password; 401 otherwise, 429 after too many wrong passwords."""
    email = normalize_email(email)
    now = time.time()
    with _failures_lock:
        if len(_recent_failures(email, now)) >= MAX_FAILURES:
            raise HTTPException(429, "Too many wrong passwords. Wait 15 minutes, then try again.")
    user = session.scalar(select(M.User).where(M.User.email == email))
    ok = verify_password(user.password_hash if user else _DUMMY_HASH, password)
    if not (ok and user and user.is_active):
        with _failures_lock:
            _recent_failures(email, now).append(now)
        raise HTTPException(401, "Wrong email or password.")
    with _failures_lock:
        _failures.pop(email, None)
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


def set_cookie(request: Request, response, token: str, max_age: int | None) -> None:
    secure = settings.session_cookie_secure
    if secure is None:
        secure = request.url.scheme == "https"
    response.set_cookie(COOKIE, token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/")


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE, path="/")


def end_user_sessions(session: Session, user_id: int, keep_token: str | None = None) -> None:
    """Sign a user out everywhere (except the browser holding `keep_token`)."""
    q = delete(M.UserSession).where(M.UserSession.user_id == user_id)
    if keep_token:
        q = q.where(M.UserSession.token_hash != _token_hash(keep_token))
    session.execute(q)


def session_user(request: Request, session: Session) -> M.User | None:
    """The active user of the request's session cookie, or None."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    return session.scalar(
        select(M.User).join(M.UserSession, M.UserSession.user_id == M.User.id)
        .where(M.UserSession.token_hash == _token_hash(token), M.UserSession.expires_at > func.now(), M.User.is_active)
    )


def signed_in_user(request: Request, session: Session = Depends(get_session)) -> M.User:
    """FastAPI dependency: the signed-in user, or 401 — even one who must still change their password."""
    user = session_user(request, session)
    if user is None:
        raise HTTPException(401, "Please sign in.")
    return user


PASSWORD_CHANGE_REQUIRED = "password_change_required"  # the dashboard recognises this detail


def current_user(user: M.User = Depends(signed_in_user)) -> M.User:
    """FastAPI dependency: the signed-in user; 403 until a temporary password has been changed."""
    if user.must_change_password:
        raise HTTPException(403, PASSWORD_CHANGE_REQUIRED)
    return user


def require_admin(user: M.User = Depends(current_user)) -> M.User:
    """FastAPI dependency: the signed-in administrator; 403 for viewers."""
    if user.role != "admin":
        raise HTTPException(403, "Only an administrator can do this.")
    return user
