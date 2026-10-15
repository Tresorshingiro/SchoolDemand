"""The admin portal's API: user accounts and the audit log. Administrators only.

Accounts come from the MINEDUC GIS portal (added at first sign-in, name and email refreshed at each one); here an
administrator changes their role or disables them. Passwords are the portal's.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..schemas import AdminUserOut, AuditOut, UserPatchIn
from ..services.accounts import check_admin_removal
from ..services.audit import audit
from ..services.auth import end_user_sessions, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


def _user(session: Session, user_id: int) -> M.User:
    user = session.get(M.User, user_id)
    if user is None:
        raise HTTPException(404, f"No user {user_id}.")
    return user


@router.get("/users", response_model=list[AdminUserOut], summary="Everyone who has signed in")
def list_users(session: Session = Depends(get_session), _: M.User = Depends(require_admin)):
    return session.scalars(select(M.User).order_by(M.User.username)).all()


@router.patch("/users/{user_id}", response_model=AdminUserOut, summary="Change the role, or disable / enable")
def update_user(user_id: int, body: UserPatchIn, session: Session = Depends(get_session),
                admin: M.User = Depends(require_admin)):
    user = _user(session, user_id)
    fields = body.model_fields_set
    loses_admin = user.role == "admin" and user.is_active and (
        ("role" in fields and body.role != "admin") or ("is_active" in fields and body.is_active is False))
    if loses_admin:
        check_admin_removal(session, admin.id, user)
    if body.role is not None and body.role != user.role:
        audit(session, admin, "user.role", user.username, {"from": user.role, "to": body.role})
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        audit(session, admin, "user.enable" if body.is_active else "user.disable", user.username)
        if not body.is_active:
            end_user_sessions(session, user.id)
    session.commit()
    session.refresh(user)
    return user


@router.get("/audit", response_model=list[AuditOut], summary="Who changed what, newest first")
def audit_log(limit: int = Query(50, ge=1, le=200), before: int | None = None, user_id: int | None = None,
              action: str | None = Query(None, max_length=40, description="prefix, e.g. user. or scenario.delete"),
              session: Session = Depends(get_session), _: M.User = Depends(require_admin)):
    q = (select(M.AuditLog, M.User.username, M.User.full_name)
         .outerjoin(M.User, M.User.id == M.AuditLog.user_id)
         .order_by(M.AuditLog.id.desc()).limit(limit))
    if before is not None:
        q = q.where(M.AuditLog.id < before)
    if user_id is not None:
        q = q.where(M.AuditLog.user_id == user_id)
    if action:
        q = q.where(M.AuditLog.action.startswith(action, autoescape=True))
    return [AuditOut(id=a.id, at=a.at, user_id=a.user_id, user_username=username, user_name=name, action=a.action,
                     target=a.target, detail=a.detail) for a, username, name in session.execute(q).all()]
