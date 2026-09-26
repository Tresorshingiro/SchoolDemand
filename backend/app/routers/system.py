"""Health check and data reload."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from ..config import settings
from ..db import engine
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
        "data": {"import_run": snap.import_run, "class_groups": len(snap.roster)} if snap else None,
    }


@router.post("/admin/reload", summary="Re-read the database after an import (X-Admin-Token header)")
async def reload(x_admin_token: str = Header("")) -> dict:
    if not settings.admin_token:
        raise HTTPException(403, "Reload is disabled: set ADMIN_TOKEN, or restart the API after an import.")
    if x_admin_token != settings.admin_token:
        raise HTTPException(401, "Wrong admin token.")
    return await run_in_threadpool(store.load)
