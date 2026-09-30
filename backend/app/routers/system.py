"""Health check and data reload."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..db import engine, get_session
from ..services import auth
from ..services.store import store

router = APIRouter(tags=["system"])


@router.get("/health", summary="API, database and loaded data")
def health() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception as e:  # noqa: BLE001 — report, don't fail the health check
        db = f"error: {e.__class__.__name__}"
    snap = store.snapshot if store.ready else None
    return {
        "status": "ok" if db == "ok" and snap else "degraded",
        "database": db,
        "data": {"import_run": snap.import_run, "class_groups": len(snap.roster), "years": list(snap.rosters)}
        if snap else None,
    }


@router.post("/admin/reload", summary="Re-read the database after an import (signed-in admin, or X-Admin-Token header)")
async def reload(request: Request, x_admin_token: str = Header(""), session: Session = Depends(get_session)) -> dict:
    token_ok = bool(settings.admin_token) and secrets.compare_digest(x_admin_token, settings.admin_token)
    if not token_ok:
        user = auth.session_user(request, session)
        if user is None:
            raise HTTPException(401, "Sign in as an administrator, or send the X-Admin-Token header.")
        if user.role != "admin" or user.must_change_password:
            raise HTTPException(403, "Only an administrator can do this.")
    return await run_in_threadpool(store.load)
