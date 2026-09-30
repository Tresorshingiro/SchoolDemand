"""The admin portal's API: user accounts and the audit log. Administrators only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..schemas import AdminUserOut, AuditOut, PasswordSetIn, UserCreateIn, UserPatchIn
from ..services.accounts import check_admin_removal, hash_or_422, valid_email
from ..services.audit import audit
from ..services.auth import end_user_sessions, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


def _user(session: Session, user_id: int) -> M.User:
    user = session.get(M.User, user_id)
    if user is None:
        raise HTTPException(404, f"No user {user_id}.")
    return user


def _name(value: str | None) -> str | None:
    return (value or "").strip() or None


@router.get("/users", response_model=list[AdminUserOut], summary="Every account")
def list_users(session: Session = Depends(get_session), _: M.User = Depends(require_admin)):
    return session.scalars(select(M.User).order_by(M.User.email)).all()


@router.post("/users", response_model=AdminUserOut, status_code=201,
             summary="Add an account with a temporary password (changed at first sign-in)")
def create_user(body: UserCreateIn, session: Session = Depends(get_session), admin: M.User = Depends(require_admin)):
    email = valid_email(body.email)
    if session.scalar(select(M.User.id).where(M.User.email == email)):
        raise HTTPException(409, f"{email} already has an account.")
    user = M.User(email=email, full_name=_name(body.full_name), role=body.role, password_hash=hash_or_422(body.password),
                  is_active=True, must_change_password=True, created_by_id=admin.id)
    session.add(user)
    audit(session, admin, "user.create", email, {"role": body.role})
    session.commit()
    session.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=AdminUserOut, summary="Change name, role, or disable / enable")
def update_user(user_id: int, body: UserPatchIn, session: Session = Depends(get_session),
                admin: M.User = Depends(require_admin)):
    user = _user(session, user_id)
    fields = body.model_fields_set
    loses_admin = user.role == "admin" and user.is_active and (
        ("role" in fields and body.role != "admin") or ("is_active" in fields and body.is_active is False))
    if loses_admin:
        check_admin_removal(session, admin.id, user)
    if "full_name" in fields and _name(body.full_name) != user.full_name:
        user.full_name = _name(body.full_name)
        audit(session, admin, "user.update", user.email, {"full_name": user.full_name})
    if body.role is not None and body.role != user.role:
        audit(session, admin, "user.role", user.email, {"from": user.role, "to": body.role})
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        audit(session, admin, "user.enable" if body.is_active else "user.disable", user.email)
        if not body.is_active:
            end_user_sessions(session, user.id)
    session.commit()
    session.refresh(user)
    return user


@router.post("/users/{user_id}/password", status_code=204,
             summary="Set a temporary password (signs the user out; they choose their own at next sign-in)")
def reset_password(user_id: int, body: PasswordSetIn, session: Session = Depends(get_session),
                   admin: M.User = Depends(require_admin)) -> Response:
    user = _user(session, user_id)
    user.password_hash = hash_or_422(body.password)
    user.must_change_password = True
    end_user_sessions(session, user.id)
    audit(session, admin, "user.password_reset", user.email)
    session.commit()
    return Response(status_code=204)


@router.get("/audit", response_model=list[AuditOut], summary="Who changed what, newest first")
def audit_log(limit: int = Query(50, ge=1, le=200), before: int | None = None, user_id: int | None = None,
              action: str | None = Query(None, max_length=40, description="prefix, e.g. user. or scenario.delete"),
              session: Session = Depends(get_session), _: M.User = Depends(require_admin)):
    q = (select(M.AuditLog, M.User.email, M.User.full_name)
         .outerjoin(M.User, M.User.id == M.AuditLog.user_id)
         .order_by(M.AuditLog.id.desc()).limit(limit))
    if before is not None:
        q = q.where(M.AuditLog.id < before)
    if user_id is not None:
        q = q.where(M.AuditLog.user_id == user_id)
    if action:
        q = q.where(M.AuditLog.action.startswith(action, autoescape=True))
    return [AuditOut(id=a.id, at=a.at, user_id=a.user_id, user_email=email, user_name=name, action=a.action,
                     target=a.target, detail=a.detail) for a, email, name in session.execute(q).all()]
