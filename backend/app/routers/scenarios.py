"""Saved intake plans (projection scenarios), shared by everyone who uses the dashboard.

A plan belongs to the base year it was made for; when a newer school year is published it is archived (readable,
not changed) and an admin can copy it into the current years.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..domain import projection as P
from ..schemas import Intake, ScenarioCopyIn, ScenarioIn, ScenarioOut, ScenarioSummary
from ..services.audit import audit
from ..services.auth import current_user, require_admin
from ..services.store import store
from .common import complete_intake, require_data

router = APIRouter(prefix="/scenarios", tags=["scenarios"], dependencies=[Depends(current_user)])


def _base_year(session: Session, s: M.ProjectionScenario) -> int:
    return session.scalar(select(M.AcademicYear.year).where(M.AcademicYear.id == s.base_year_id))


def _current() -> P.Horizon:
    return store.snapshot.horizon if store.ready else P.DEFAULT_HORIZON


def _summary(session: Session, s: M.ProjectionScenario) -> ScenarioSummary:
    base = _base_year(session, s)
    return ScenarioSummary(id=s.id, name=s.name, description=s.description, created_by=s.created_by,
                           created_at=s.created_at, updated_at=s.updated_at, base_year=base,
                           archived=base != _current().base)


def _intake(session: Session, s: M.ProjectionScenario) -> Intake:
    rows = session.execute(
        select(M.Grade.code, M.District.name, M.ScenarioIntake.year, M.ScenarioIntake.new_entrants)
        .join(M.Grade, M.Grade.id == M.ScenarioIntake.grade_id)
        .join(M.District, M.District.id == M.ScenarioIntake.district_id)
        .where(M.ScenarioIntake.scenario_id == s.id)
    ).all()
    years = P.Horizon(_base_year(session, s)).future  # the plan's own years
    out: Intake = {}
    for grade, district, year, value in rows:
        if year in years:
            out.setdefault(grade, {}).setdefault(district, [0] * len(years))[years.index(year)] = value
    return out


def _save_intake(session: Session, scenario: M.ProjectionScenario, intake: Intake) -> None:
    grade_ids = dict(session.execute(select(M.Grade.code, M.Grade.id)).all())
    district_ids = dict(session.execute(select(M.District.name, M.District.id)).all())
    session.execute(delete(M.ScenarioIntake).where(M.ScenarioIntake.scenario_id == scenario.id))
    session.add_all([
        M.ScenarioIntake(scenario_id=scenario.id, year=year, grade_id=grade_ids[grade], district_id=district_ids[district],
                         new_entrants=value, source="manual")
        for grade, table in intake.items() for district, values in table.items()
        for year, value in zip(_current().future, values)
    ])


def _out(session: Session, s: M.ProjectionScenario) -> ScenarioOut:
    return ScenarioOut(**_summary(session, s).model_dump(), intake=_intake(session, s))


def _get(session: Session, scenario_id: int) -> M.ProjectionScenario:
    s = session.get(M.ProjectionScenario, scenario_id)
    if s is None:
        raise HTTPException(404, f"No scenario {scenario_id}.")
    return s


def _new(session: Session, name: str, description: str | None, user: M.User, intake: Intake) -> M.ProjectionScenario:
    h = _current()
    base_year = session.scalar(select(M.AcademicYear.id).where(M.AcademicYear.year == h.base))
    s = M.ProjectionScenario(name=name.strip(), description=description, created_by=(user.full_name or user.email)[:100],
                             base_year_id=base_year, end_year=h.years[-1])
    session.add(s)
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(409, f"A scenario named {name!r} already exists.") from None
    _save_intake(session, s, intake)
    return s


@router.get("", response_model=list[ScenarioSummary], summary="Saved scenarios, most recently changed first")
def list_scenarios(session: Session = Depends(get_session)):
    return [_summary(session, s) for s in
            session.scalars(select(M.ProjectionScenario).order_by(M.ProjectionScenario.updated_at.desc())).all()]


@router.get("/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: int, session: Session = Depends(get_session)):
    return _out(session, _get(session, scenario_id))


@router.post("", response_model=ScenarioOut, status_code=201, dependencies=[Depends(require_data)])
def create_scenario(body: ScenarioIn, session: Session = Depends(get_session), user: M.User = Depends(require_admin)):
    s = _new(session, body.name, body.description, user, complete_intake(body.intake))
    audit(session, user, "scenario.create", s.name)
    session.commit()
    return _out(session, s)


@router.put("/{scenario_id}", response_model=ScenarioOut, dependencies=[Depends(require_data)])
def update_scenario(scenario_id: int, body: ScenarioIn, session: Session = Depends(get_session),
                    user: M.User = Depends(require_admin)):
    s = _get(session, scenario_id)
    summary = _summary(session, s)
    if summary.archived:
        y = summary.base_year
        raise HTTPException(409, f"This plan was made for {y + 1}-{y + P.HORIZON_YEARS}; "
                                 "copy it to the current years first.")
    intake = complete_intake(body.intake)
    s.name, s.description = body.name.strip(), body.description
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(409, f"A scenario named {body.name!r} already exists.") from None
    _save_intake(session, s, intake)
    s.updated_at = func.now()
    audit(session, user, "scenario.update", s.name)
    session.commit()
    session.refresh(s)
    return _out(session, s)


@router.post("/{scenario_id}/copy", response_model=ScenarioOut, status_code=201, dependencies=[Depends(require_data)],
             summary="Copy a plan into the current years (years in both keep their values)")
def copy_scenario(scenario_id: int, body: ScenarioCopyIn, session: Session = Depends(get_session),
                  user: M.User = Depends(require_admin)):
    old = _get(session, scenario_id)
    old_years = P.Horizon(_base_year(session, old)).future
    old_plan = _intake(session, old)
    defaults = complete_intake(None)

    def value(g: str, d: str, k: int, y: int) -> int:
        """The old plan's value for year y when it had that year, else the default plan's."""
        old_values = old_plan.get(g, {}).get(d)
        return old_values[old_years.index(y)] if old_values and y in old_years else defaults[g][d][k]

    intake = {g: {d: [value(g, d, k, y) for k, y in enumerate(_current().future)] for d in table}
              for g, table in defaults.items()}
    s = _new(session, body.name, old.description, user, intake)
    audit(session, user, "scenario.create", s.name, {"copied_from": old.name})
    session.commit()
    return _out(session, s)


@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, session: Session = Depends(get_session),
                    user: M.User = Depends(require_admin)) -> Response:
    s = _get(session, scenario_id)
    audit(session, user, "scenario.delete", s.name)
    session.delete(s)
    session.commit()
    return Response(status_code=204)
