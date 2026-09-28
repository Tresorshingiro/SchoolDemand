"""The 2026 dataset and the map boundaries."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..services.auth import current_user
from ..services.store import store
from .common import json_payload, require_data

router = APIRouter(tags=["data"], dependencies=[Depends(current_user), Depends(require_data)])


@router.get("/meta", summary="Levels, grades, capacity, source, data-quality counts")
def meta(request: Request) -> Response:
    return json_payload(request, store.payload("meta"))


@router.get("/school-levels", summary="One record per school x level (2026)")
def school_levels(request: Request) -> Response:
    return json_payload(request, store.payload("school-levels"))


@router.get("/grades", summary="One row per school x grade (2026)")
def grades(request: Request) -> Response:
    return json_payload(request, store.payload("grades"))


@router.get("/combos", summary="Students and class groups per school x grade x combination (2026)")
def combos(request: Request) -> Response:
    return json_payload(request, store.payload("combos"))


@router.get("/boundaries/{layer}", summary="GeoJSON outline of the country, districts or sectors")
def boundaries(layer: Literal["country", "districts", "sectors"], request: Request) -> Response:
    return json_payload(request, store.payload(f"boundaries/{layer}"), max_age=3600)
