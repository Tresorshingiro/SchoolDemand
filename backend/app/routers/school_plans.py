"""Saved plans of new schools, shared by everyone who uses the dashboard; separate from the intake plans
(scenarios.py) and switched on or off on the dashboard.

A plan belongs to the base year it was made for; when a newer school year is published it is archived (readable,
not changed) and an admin can copy it into the current years.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..domain import new_schools as NS
from ..domain import projection as P
from ..schemas import PlannedSchoolIn, ScenarioCopyIn, SchoolPlanIn, SchoolPlanOut, SchoolPlanSummary
from ..services.audit import audit
from ..services.auth import current_user, require_admin
from ..services.store import store
from .common import complete_intake, complete_schools, require_data

router = APIRouter(prefix="/school-plans", tags=["school plans"], dependencies=[Depends(current_user)])


def _current() -> P.Horizon:
    return store.snapshot.horizon if store.ready else P.DEFAULT_HORIZON


def _base_year(session: Session, p: M.SchoolPlan) -> int:
    return session.scalar(select(M.AcademicYear.year).where(M.AcademicYear.id == p.base_year_id))


def _schools(session: Session, p: M.SchoolPlan) -> list[PlannedSchoolIn]:
    rows = session.execute(
        select(M.PlannedSchoolRow, func.ST_Y(M.PlannedSchoolRow.geom), func.ST_X(M.PlannedSchoolRow.geom))
        .where(M.PlannedSchoolRow.school_plan_id == p.id).order_by(M.PlannedSchoolRow.id)).all()
    levels: dict[int, dict[str, int]] = {}
    for sid, code, n in session.execute(
            select(M.PlannedSchoolLevel.planned_school_id, M.SchoolLevel.code, M.PlannedSchoolLevel.classrooms)
            .join(M.SchoolLevel, M.SchoolLevel.id == M.PlannedSchoolLevel.level_id)
            .join(M.PlannedSchoolRow, M.PlannedSchoolRow.id == M.PlannedSchoolLevel.planned_school_id)
            .where(M.PlannedSchoolRow.school_plan_id == p.id)).all():
        levels.setdefault(sid, {})[code] = n
    return [PlannedSchoolIn(name=r.name, latitude=lat, longitude=lon, levels=levels.get(r.id, {}),
                            opening_year=r.opening_year, walking_km=float(r.walking_km)) for r, lat, lon in rows]


def _summary(session: Session, p: M.SchoolPlan) -> SchoolPlanSummary:
    base = _base_year(session, p)
    n = session.scalar(select(func.count()).select_from(M.PlannedSchoolRow)
                       .where(M.PlannedSchoolRow.school_plan_id == p.id))
    return SchoolPlanSummary(id=p.id, name=p.name, description=p.description, created_by=p.created_by,
                             created_at=p.created_at, updated_at=p.updated_at, base_year=base,
                             archived=base != _current().base, schools=n, summary=p.summary)


def _out(session: Session, p: M.SchoolPlan) -> SchoolPlanOut:
    return SchoolPlanOut(**_summary(session, p).model_dump(), plan_schools=_schools(session, p))


def _get(session: Session, plan_id: int) -> M.SchoolPlan:
    p = session.get(M.SchoolPlan, plan_id)
    if p is None:
        raise HTTPException(404, f"No plan of new schools {plan_id}.")
    return p


async def _results(session: Session, schools: list[PlannedSchoolIn], intake) -> dict:
    """The plan's summary with today's data (the intake plan on screen, else the default)."""
    planned = complete_schools(schools, session)
    full = complete_intake(intake)
    run_intake = None if full == store.snapshot.default_intake else full
    _, before, _, _ = await run_in_threadpool(store.frames, run_intake)
    info, after, _, _ = await run_in_threadpool(store.frames, run_intake, planned)
    return {**NS.summary(before, after, info, planned, _current()),
            "calculated_at": datetime.now(timezone.utc).isoformat()}


def _save_schools(session: Session, p: M.SchoolPlan, schools: list[PlannedSchoolIn]) -> None:
    level_ids = dict(session.execute(select(M.SchoolLevel.code, M.SchoolLevel.id)).all())
    session.execute(delete(M.PlannedSchoolRow).where(M.PlannedSchoolRow.school_plan_id == p.id))
    for s in schools:
        row = M.PlannedSchoolRow(school_plan_id=p.id, name=s.name.strip(), opening_year=s.opening_year,
                                 walking_km=s.walking_km, geom=WKTElement(f"POINT({s.longitude} {s.latitude})", 4326))
        session.add(row)
        session.flush()
        session.add_all([M.PlannedSchoolLevel(planned_school_id=row.id, level_id=level_ids[code], classrooms=n)
                         for code, n in s.levels.items()])


def _flush_name(session: Session, name: str) -> None:
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(409, f"A plan named {name!r} already exists.") from None


async def _new(session: Session, name: str, description: str | None, schools: list[PlannedSchoolIn], intake,
               user: M.User) -> M.SchoolPlan:
    summary = await _results(session, schools, intake)
    base_year = session.scalar(select(M.AcademicYear.id).where(M.AcademicYear.year == _current().base))
    p = M.SchoolPlan(name=name.strip(), description=description, base_year_id=base_year, summary=summary,
                     created_by=(user.full_name or user.username)[:100])
    session.add(p)
    _flush_name(session, name)
    _save_schools(session, p, schools)
    return p


@router.get("", response_model=list[SchoolPlanSummary], summary="Saved plans of new schools, most recently changed first")
def list_plans(session: Session = Depends(get_session)):
    return [_summary(session, p) for p in
            session.scalars(select(M.SchoolPlan).order_by(M.SchoolPlan.updated_at.desc())).all()]


@router.get("/{plan_id}", response_model=SchoolPlanOut)
def get_plan(plan_id: int, session: Session = Depends(get_session)):
    return _out(session, _get(session, plan_id))


@router.post("", response_model=SchoolPlanOut, status_code=201, dependencies=[Depends(require_data)])
async def create_plan(body: SchoolPlanIn, session: Session = Depends(get_session),
                      user: M.User = Depends(require_admin)):
    p = await _new(session, body.name, body.description, body.schools, body.intake, user)
    audit(session, user, "school_plan.create", p.name)
    session.commit()
    return _out(session, p)


@router.put("/{plan_id}", response_model=SchoolPlanOut, dependencies=[Depends(require_data)])
async def update_plan(plan_id: int, body: SchoolPlanIn, session: Session = Depends(get_session),
                      user: M.User = Depends(require_admin)):
    p = _get(session, plan_id)
    s = _summary(session, p)
    if s.archived:
        raise HTTPException(409, f"This plan was made for {s.base_year + 1}-{s.base_year + P.HORIZON_YEARS}; "
                                 "copy it to the current years first.")
    p.summary = await _results(session, body.schools, body.intake)
    p.name, p.description = body.name.strip(), body.description
    _flush_name(session, body.name)
    _save_schools(session, p, body.schools)
    p.updated_at = func.now()
    audit(session, user, "school_plan.update", p.name)
    session.commit()
    session.refresh(p)
    return _out(session, p)


@router.post("/{plan_id}/copy", response_model=SchoolPlanOut, status_code=201, dependencies=[Depends(require_data)],
             summary="Copy a plan into the current years (opening years already past move to the first projected year)")
async def copy_plan(plan_id: int, body: ScenarioCopyIn, session: Session = Depends(get_session),
                    user: M.User = Depends(require_admin)):
    old = _get(session, plan_id)
    first = _current().future[0]
    schools = [s.model_copy(update={"opening_year": max(s.opening_year, first)}) for s in _schools(session, old)]
    p = await _new(session, body.name, old.description, schools, None, user)
    audit(session, user, "school_plan.create", p.name, {"copied_from": old.name})
    session.commit()
    return _out(session, p)


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int, session: Session = Depends(get_session), user: M.User = Depends(require_admin)) -> Response:
    p = _get(session, plan_id)
    audit(session, user, "school_plan.delete", p.name)
    session.delete(p)
    session.commit()
    return Response(status_code=204)
