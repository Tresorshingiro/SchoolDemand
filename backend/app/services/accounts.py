"""Rules for managing accounts from the admin portal."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from .auth import hash_password, normalize_email


def valid_email(email: str) -> str:
    """Trimmed, lower-case email; 422 when it is not one."""
    email = normalize_email(email)
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email:
        raise HTTPException(422, "That is not an email address.")
    return email


def hash_or_422(password: str) -> str:
    try:
        return hash_password(password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


def check_admin_removal(session: Session, actor_id: int, target: M.User) -> None:
    """Before `target` stops being an active admin: never yourself, never the last one.

    The active admins are locked (SELECT ... FOR UPDATE) so two admins demoting each other at the same moment are
    counted one after the other."""
    if target.id == actor_id:
        raise HTTPException(409, "You cannot remove your own admin access.")
    admins = session.scalars(
        select(M.User.id).where(M.User.role == "admin", M.User.is_active).with_for_update()
    ).all()
    if not set(admins) - {target.id}:
        raise HTTPException(409, "At least one active administrator is needed.")
