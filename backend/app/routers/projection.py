"""The projection 2026-2030: its configuration and runs for an intake plan (calculated on the server)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import ProjectionRequest
from ..services.auth import current_user
from ..services.store import store
from .common import complete_intake, complete_schools, json_payload, require_data

router = APIRouter(prefix="/projection", tags=["projection"], dependencies=[Depends(current_user), Depends(require_data)])


@router.get("/config", summary="Years, levels, grades, how new students enter, the default intake plan")
def config(request: Request) -> Response:
    return json_payload(request, store.payload("projection-config"))


@router.get("/default", summary="The projection with the default (catchment) intake plan")
def default(request: Request) -> Response:
    return json_payload(request, store.projection(None))


@router.post("/run", summary="The projection for an intake plan and planned new schools (cached per plan)")
async def run(body: ProjectionRequest, request: Request, session: Session = Depends(get_session)) -> Response:
    intake = complete_intake(body.intake)
    planned = complete_schools(body.schools, session)
    is_default = intake == store.snapshot.default_intake  # same cache entry as GET /projection/default
    payload = await run_in_threadpool(store.projection, None if is_default else intake, planned)
    return json_payload(request, payload, max_age=0)
