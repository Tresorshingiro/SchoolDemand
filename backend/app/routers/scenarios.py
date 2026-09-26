"""Saved intake plans (projection scenarios), shared by everyone who uses the dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..domain import projection as P
from ..schemas import Intake, ScenarioIn, ScenarioOut, ScenarioSummary
from .common import complete_intake, require_data

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _intake(session: Session, scenario_id: int) -> Intake:
    rows = session.execute(
        select(M.Grade.code, M.District.name, M.ScenarioIntake.year, M.ScenarioIntake.new_entrants)
        .join(M.Grade, M.Grade.id == M.ScenarioIntake.grade_id)
        .join(M.District, M.District.id == M.ScenarioIntake.district_id)
        .where(M.ScenarioIntake.scenario_id == scenario_id)
    ).all()
    years = P.YEARS[1:]
    out: Intake = {}
    for grade, district, year, value in rows:
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
        for year, value in zip(P.YEARS[1:], values)
    ])


def _out(session: Session, s: M.ProjectionScenario) -> ScenarioOut:
    return ScenarioOut(**ScenarioSummary.model_validate(s).model_dump(), intake=_intake(session, s.id))


def _get(session: Session, scenario_id: int) -> M.ProjectionScenario:
    s = session.get(M.ProjectionScenario, scenario_id)
    if s is None:
        raise HTTPException(404, f"No scenario {scenario_id}.")
    return s


@router.get("", response_model=list[ScenarioSummary], summary="Saved scenarios, most recently changed first")
def list_scenarios(session: Session = Depends(get_session)):
    return session.scalars(select(M.ProjectionScenario).order_by(M.ProjectionScenario.updated_at.desc())).all()


@router.get("/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: int, session: Session = Depends(get_session)):
    return _out(session, _get(session, scenario_id))


@router.post("", response_model=ScenarioOut, status_code=201, dependencies=[Depends(require_data)])
def create_scenario(body: ScenarioIn, session: Session = Depends(get_session)):
    intake = complete_intake(body.intake)
    base_year = session.scalar(select(M.AcademicYear.id).where(M.AcademicYear.year == P.BASE_YEAR))
    s = M.ProjectionScenario(name=body.name.strip(), description=body.description, created_by=body.created_by,
                             base_year_id=base_year, end_year=P.YEARS[-1])
    session.add(s)
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(409, f"A scenario named {body.name!r} already exists.") from None
    _save_intake(session, s, intake)
    session.commit()
    return _out(session, s)


@router.put("/{scenario_id}", response_model=ScenarioOut, dependencies=[Depends(require_data)])
def update_scenario(scenario_id: int, body: ScenarioIn, session: Session = Depends(get_session)):
    s = _get(session, scenario_id)
    intake = complete_intake(body.intake)
    s.name, s.description = body.name.strip(), body.description
    if body.created_by:
        s.created_by = body.created_by
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(409, f"A scenario named {body.name!r} already exists.") from None
    _save_intake(session, s, intake)
    s.updated_at = func.now()
    session.commit()
    session.refresh(s)
    return _out(session, s)


@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, session: Session = Depends(get_session)) -> Response:
    session.delete(_get(session, scenario_id))
    session.commit()
    return Response(status_code=204)
