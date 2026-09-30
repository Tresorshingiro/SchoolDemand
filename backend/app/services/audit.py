"""The audit log: one row per change an administrator (or a user to their own account) makes."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models as M


def audit(session: Session, user: M.User | None, action: str, target: str, detail: dict | None = None) -> None:
    """Add an entry in the caller's transaction (committed with the change it describes)."""
    session.add(M.AuditLog(user_id=user.id if user else None, action=action, target=target[:200], detail=detail))
