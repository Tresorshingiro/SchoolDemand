"""Write checked data into the live tables (inside the caller's transaction)."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .. import models as M
from ..domain import analysis as A
from ..services import repository as R
from .sql import none, reset_sequence


def _year_id(session: Session, year: int) -> int:
    session.execute(pg_insert(M.AcademicYear.__table__).values(year=year).on_conflict_do_nothing(index_elements=["year"]))
    year_id = session.scalar(select(M.AcademicYear.id).where(M.AcademicYear.year == year))
    levels = dict(session.execute(select(M.SchoolLevel.code, M.SchoolLevel.id)).all())
    session.execute(pg_insert(M.LevelNorm.__table__).values([
        {"level_id": levels[key], "academic_year_id": year_id, "classroom_capacity": cap}
        for key, _, _, cap in A.LEVELS if key in levels
    ]).on_conflict_do_nothing(index_elements=["level_id", "academic_year_id"]))
    return year_id


def _clear_year(session: Session, year_id: int) -> None:
    session.execute(delete(M.DataQualityIssue).where(M.DataQualityIssue.academic_year_id == year_id))
    session.execute(delete(M.ClassGroup).where(M.ClassGroup.academic_year_id == year_id))
    session.execute(delete(M.Classroom).where(M.Classroom.academic_year_id == year_id))


def refresh_schools(session: Session, newest_year: int) -> None:
    """Active = in the newest school year; map point from the coordinates."""
    session.execute(text(
        "UPDATE schools s SET is_active = EXISTS (SELECT 1 FROM class_groups cg JOIN academic_years y "
        "ON y.id = cg.academic_year_id WHERE cg.school_id = s.id AND y.year = :y), "
        "geom = CASE WHEN latitude IS NULL OR longitude IS NULL THEN NULL "
        "ELSE ST_SetSRID(ST_MakePoint(longitude::float8, latitude::float8), 4326) END"), {"y": newest_year})


def _schools(session: Session, roster: pd.DataFrame, run: M.ImportRun, details: bool) -> dict[int, int]:
    """Schools by code (new ones added). Name, sector and coordinates are updated only from the newest year."""
    sectors = {(d, s): i for d, s, i in session.execute(
        select(M.District.name, M.Sector.name, M.Sector.id).join(M.District, M.District.id == M.Sector.district_id))}
    rows = [{"mineduc_code": str(int(r.school_code)), "name": r.school_name, "sector_id": sectors.get((r.district, r.sector)),
             "latitude": none(r.latitude), "longitude": none(r.longitude), "is_active": True, "import_run_id": run.id}
            for r in A._school_info(roster).itertuples(index=False)]
    stmt = pg_insert(M.School.__table__).values(rows)
    if details:
        stmt = stmt.on_conflict_do_update(index_elements=["mineduc_code"], set_={
            c: stmt.excluded[c] for c in ("name", "sector_id", "latitude", "longitude", "import_run_id")})
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=["mineduc_code"])
    session.execute(stmt)
    codes = [r["mineduc_code"] for r in rows]
    return {int(k): v for k, v in session.execute(
        select(M.School.mineduc_code, M.School.id).where(M.School.mineduc_code.in_(codes))).all()}


def publish_school_data(session: Session, run: M.ImportRun, roster: pd.DataFrame) -> None:
    """Replace one school year's rooms, class groups and data-quality issues."""
    year = run.academic_year
    newest = max([year, *R.school_years(session)])
    year_id = _year_id(session, year)
    run.academic_year_id = year_id
    _clear_year(session, year_id)
    school_id = _schools(session, roster, run, details=year >= newest)
    grades = dict(session.execute(select(M.Grade.code, M.Grade.id)).all())
    rooms = (roster.groupby(["school_code", A.ROOM_ID], sort=False)
             .agg(source=("classroom_id", "first"), name=("classroom_name", "first")).reset_index())
    start = session.scalar(select(func.coalesce(func.max(M.Classroom.id), 0))) + 1
    room_id = {(int(c), str(t)): start + i for i, (c, t) in enumerate(zip(rooms["school_code"], rooms[A.ROOM_ID]))}
    session.execute(insert(M.Classroom.__table__), [
        {"id": room_id[(int(r.school_code), str(getattr(r, A.ROOM_ID)))], "academic_year_id": year_id,
         "school_id": school_id[int(r.school_code)], "mineduc_classroom_id": str(getattr(r, A.ROOM_ID)),
         "source_classroom_id": none(r.source), "name": none(r.name), "import_run_id": run.id}
        for r in rooms.itertuples(index=False)
    ])
    start = session.scalar(select(func.coalesce(func.max(M.ClassGroup.id), 0))) + 1
    session.execute(insert(M.ClassGroup.__table__), [
        {"id": start + i, "academic_year_id": year_id, "school_id": school_id[int(r.school_code)],
         "grade_id": grades[r.grade], "name": none(r.class_group), "combination": none(r.combination),
         "classroom_id": room_id[(int(r.school_code), str(getattr(r, A.ROOM_ID)))],
         "students_total": int(r.students), "import_run_id": run.id}
        for i, r in enumerate(roster.rename(columns={A.STUDENTS: "students"}).itertuples(index=False))
    ])
    dq = A.data_quality(roster)
    if len(dq):
        session.execute(insert(M.DataQualityIssue.__table__), [
            {"import_run_id": run.id, "academic_year_id": year_id, "school_id": school_id.get(int(r.school_code)),
             "entity": "class_groups", "issue_code": r.issue, "detail": none(r.detail)}
            for r in dq.itertuples(index=False)
        ])
    for table in ("classrooms", "class_groups", "data_quality_issues"):
        reset_sequence(session, table)
    refresh_schools(session, newest)


def publish_catchment(session: Session, run: M.ImportRun, pop: pd.DataFrame) -> None:
    """Replace every school's catchment figures (children aged 3)."""
    session.execute(delete(M.CatchmentPopulation))
    ids = {int(k): v for k, v in session.execute(select(M.School.mineduc_code, M.School.id)).all()}
    rows = [{"school_id": ids[int(code)], "year": int(y), "age": 3, "population": int(round(v)), "import_run_id": run.id}
            for code, row in pop.iterrows() if int(code) in ids for y, v in row.items() if not pd.isna(v)]
    if rows:
        session.execute(insert(M.CatchmentPopulation.__table__), rows)
    reset_sequence(session, "catchment_population")


def publish_nisr(session: Session, run: M.ImportRun, nisr: pd.DataFrame) -> None:
    """Replace the NISR district totals (children aged 3)."""
    session.execute(delete(M.DistrictPopulation))
    ids = dict(session.execute(select(M.District.name, M.District.id)).all())
    rows = [{"district_id": ids[d], "year": int(y), "age": 3, "population": int(round(v)), "import_run_id": run.id}
            for d, row in nisr.iterrows() for y, v in row.items() if not pd.isna(v)]
    if rows:
        session.execute(insert(M.DistrictPopulation.__table__), rows)
    reset_sequence(session, "district_population")


PUBLISH = {"school_data": publish_school_data, "catchment": publish_catchment, "nisr_population": publish_nisr}


def withdraw_rows(session: Session, run: M.ImportRun) -> None:
    """Remove a live school year (another year stays) or the NISR figures."""
    if run.kind == "nisr_population":
        session.execute(delete(M.DistrictPopulation))
        return
    year_id = session.scalar(select(M.AcademicYear.id).where(M.AcademicYear.year == run.academic_year))
    _clear_year(session, year_id)
    refresh_schools(session, max(y for y in R.school_years(session) if y != run.academic_year))
