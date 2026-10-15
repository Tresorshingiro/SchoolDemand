"""The published school years (the newest by default, ?year= for another) and the map boundaries."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..services.auth import current_user
from ..services.store import store
from .common import json_payload, require_data

router = APIRouter(tags=["data"], dependencies=[Depends(current_user), Depends(require_data)])
YEAR = "a published school year (default: the newest)"


def _payload(request: Request, name: str, year: int | None) -> Response:
    try:
        return json_payload(request, store.year_payload(name, year))
    except KeyError as e:
        raise HTTPException(404, str(e.args[0])) from None


@router.get("/meta", summary="Levels, grades, capacity, source, data-quality counts, the school and projection years")
def meta(request: Request, year: int | None = None) -> Response:
    return _payload(request, "meta", year)


@router.get("/school-levels", summary=f"One record per school x level, {YEAR}")
def school_levels(request: Request, year: int | None = None) -> Response:
    return _payload(request, "school-levels", year)


@router.get("/grades", summary=f"One row per school x grade, {YEAR}")
def grades(request: Request, year: int | None = None) -> Response:
    return _payload(request, "grades", year)


@router.get("/combos", summary=f"Students and class groups per school x grade x combination, {YEAR}")
def combos(request: Request, year: int | None = None) -> Response:
    return _payload(request, "combos", year)


@router.get("/boundaries/{layer}", summary="GeoJSON outline of the country, districts or sectors")
def boundaries(layer: Literal["country", "districts", "sectors"], request: Request) -> Response:
    return json_payload(request, store.payload(f"boundaries/{layer}"), max_age=3600)
