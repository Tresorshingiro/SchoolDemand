"""Read the analysis inputs from the database, in the same shape as the source files."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import models as M
from ..domain import analysis as A
from ..domain import projection as P

ROSTER_SQL = text(f"""
SELECT s.mineduc_code::bigint AS school_code, s.name AS school_name, d.name AS district, se.name AS sector,
       s.latitude::float8 AS latitude, s.longitude::float8 AS longitude, g.code AS grade, cg.combination,
       cg.name AS class_group, c.source_classroom_id AS classroom_id, c.name AS classroom_name,
       cg.students_total AS "{A.STUDENTS}", c.mineduc_classroom_id AS {A.ROOM_ID}
FROM class_groups cg
JOIN academic_years y ON y.id = cg.academic_year_id AND y.year = :year
JOIN schools s ON s.id = cg.school_id
JOIN grades g ON g.id = cg.grade_id
LEFT JOIN classrooms c ON c.id = cg.classroom_id
LEFT JOIN sectors se ON se.id = s.sector_id
LEFT JOIN districts d ON d.id = se.district_id
ORDER BY cg.id
""")


def read_roster(session: Session, year: int = P.BASE_YEAR) -> pd.DataFrame:
    """The class-group roster of a year, prepared for the analysis (A.prepare_roster) — as A.load_roster does from
    the file."""
    df = pd.read_sql(ROSTER_SQL, session.connection(), params={"year": year})
    return A.prepare_roster(df)


def read_catchment_population(session: Session) -> pd.DataFrame:
    """Children aged 3 per pre-primary school catchment as published: school_code x year (NaN when missing)."""
    rows = session.execute(
        select(M.School.mineduc_code, M.CatchmentPopulation.year, M.CatchmentPopulation.population)
        .join(M.School, M.School.id == M.CatchmentPopulation.school_id)
        .where(M.CatchmentPopulation.age == 3)
    ).all()
    pop = pd.DataFrame(rows, columns=["school_code", "year", "population"]).astype({"school_code": "int64"})
    return pop.pivot_table(index="school_code", columns="year", values="population", aggfunc="sum").astype(float)


def read_catchment(session: Session, roster: pd.DataFrame, horizon: P.Horizon,
                   pop: pd.DataFrame | None = None) -> pd.DataFrame:
    """Children aged 3 per pre-primary school of `roster` for the horizon's projection years (P.fill_catchment)."""
    pop = read_catchment_population(session) if pop is None else pop
    # every pre-primary school is a catchment school, with or without figures (as in the catchment file)
    pre = roster[roster["level"] == A.LEVEL_ORDER[0]]
    n1 = pre[pre["grade"] == "N1"].groupby("school_code")[A.STUDENTS].sum()
    schools = pd.Index(sorted(pre["school_code"].unique()), name="school_code")
    return P.fill_catchment(pop.reindex(index=schools), n1.reindex(schools), horizon)


def read_nisr(session: Session) -> pd.DataFrame:
    """NISR children aged 3 per district: district name x year (empty when no NISR file is published)."""
    rows = session.execute(
        select(M.District.name, M.DistrictPopulation.year, M.DistrictPopulation.population)
        .join(M.District, M.District.id == M.DistrictPopulation.district_id)
        .where(M.DistrictPopulation.age == 3)
    ).all()
    if not rows:
        return pd.DataFrame()
    t = pd.DataFrame(rows, columns=["district", "year", "population"])
    return t.pivot_table(index="district", columns="year", values="population", aggfunc="sum").astype(float)


def live_imports(session: Session) -> list[tuple[M.ImportRun, str | None]]:
    """The live data (one import per kind, per school year for school data) with the name of who published it."""
    return [(run, name) for run, name in session.execute(
        select(M.ImportRun, func.coalesce(M.User.full_name, M.User.email))
        .outerjoin(M.User, M.User.id == M.ImportRun.published_by_id)
        .where(M.ImportRun.is_live).order_by(M.ImportRun.kind, M.ImportRun.academic_year)
    ).all()]


def school_years(session: Session) -> list[int]:
    """The published school years, oldest first."""
    return sorted(session.scalars(select(M.ImportRun.academic_year).where(
        M.ImportRun.is_live, M.ImportRun.kind == "school_data")).all())


def boundaries(session: Session) -> dict[str, dict]:
    """GeoJSON FeatureCollections: country (outline), districts (d), sectors (d, s)."""
    def collection(sql: str) -> dict:
        features = [{"type": "Feature", "properties": props, "geometry": geom}
                    for props, geom in session.execute(text(sql)).all()]
        return {"type": "FeatureCollection", "features": features}

    return {
        "country": collection("SELECT json_build_object('name', name), ST_AsGeoJSON(geom, 5)::json FROM countries "
                              "WHERE geom IS NOT NULL"),
        "districts": collection("SELECT json_build_object('d', name), ST_AsGeoJSON(geom, 5)::json FROM districts "
                                "WHERE geom IS NOT NULL ORDER BY name"),
        "sectors": collection("SELECT json_build_object('d', d.name, 's', s.name), ST_AsGeoJSON(s.geom, 5)::json "
                              "FROM sectors s JOIN districts d ON d.id = s.district_id WHERE s.geom IS NOT NULL "
                              "ORDER BY d.name, s.name"),
    }
