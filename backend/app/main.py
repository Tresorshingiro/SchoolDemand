"""
School planning API — classroom sufficiency 2026 and projection 2026-2030.

  uvicorn app.main:app --reload          (from backend/, development)
  http://localhost:8000/api/docs         interactive documentation
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import data, projection, scenarios, system
from .services.store import store

log = logging.getLogger("school_planning")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        result = await run_in_threadpool(store.load)
        log.warning("data loaded: %s", result)
    except Exception as e:  # noqa: BLE001 — start anyway; /api/health reports it and data routes answer 503
        log.warning("no data loaded at startup: %s", e)
    yield


app = FastAPI(
    title="School planning API",
    version="1.0.0",
    summary="Classroom sufficiency 2026 and projection 2026-2030 for every school level in Rwanda.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"])

for router in (system.router, data.router, projection.router, scenarios.router):
    app.include_router(router, prefix="/api")
