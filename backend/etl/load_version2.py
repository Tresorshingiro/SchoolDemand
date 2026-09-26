"""
Load the development data into the database (until the MINEDUC API / real data is connected):

  Version 2.xlsx          2026 roster: schools, physical rooms (test_code), class groups
  Chachement area.xlsx    children aged 3 per pre-primary school catchment, 2027-2030
  boundaries/*.geojson    country, district and sector outlines (scripts/build_boundaries.py)

from SCHOOL_DATA_DIR (data-sources/ in the repository, /data in the API container).

Re-runnable. Reference tables, provinces, districts, sectors and schools are upserted by their code, so their ids —
and the saved scenarios that point at districts — stay. The 2026 roster, classrooms, catchments and data-quality
issues are replaced. The API picks the new data up on restart or POST /api/admin/reload.

Run (from backend/):  python -m etl.load_version2
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import Table, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import models as M
from app.db import SessionLocal
from app.domain import analysis as A
from app.domain import projection as P

BOUNDARIES = A.DATA_DIR / "boundaries"
ENTRY_AGE = {"NUR": 3, "PRI": 6, "LSE": 12, "USE": 15, "TVE": 15, "TTC": 15}  # official entry age of each level
NEXT_LEVEL = {"N3": "P1", "P6": "S1", "S3": "S4"}  # progression between levels (S3 also feeds L3 / Y1)


def slug(*parts: str) -> str:
    return "/".join(str(p).strip().upper() for p in parts)


def none(v):
    """NaN / NaT -> None for the database."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT else v


def upsert(session: Session, table: Table, rows: list[dict], key: str) -> dict:
    """Insert or update rows by their unique `key`; returns {key value: id}."""
    if not rows:
        return {}
    stmt = pg_insert(table).values(rows)
    # a key-only table still "updates" the key to itself, so existing rows are returned too
    cols = [c for c in rows[0] if c not in (key, "id")] or [key]
    stmt = stmt.on_conflict_do_update(
        index_elements=[key], set_={c: stmt.excluded[c] for c in cols},
    ).returning(table.c[key], table.c.id)
    return {k: i for k, i in session.execute(stmt).all()}


def reset_sequence(session: Session, table: str) -> None:
    session.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 0) + 1, false) FROM {table}"))


def geojson(name: str) -> list[dict]:
    return json.loads((BOUNDARIES / f"{name}.geojson").read_text(encoding="utf-8"))["features"]


def load(session: Session) -> dict:
    t0 = time.time()
    roster = A.load_roster(refresh=True)
    pop, _ = P.read_catchment()
    print(f"read {len(roster):,} class groups, {len(pop):,} catchments in {time.time() - t0:.0f}s")

    # ---- sources and the import run
    sources = upsert(session, M.DataSource.__table__, [
        {"code": "VERSION2_XLSX", "name": "Version 2.xlsx — 2026 roster (development data)", "base_url": None},
        {"code": "CATCHMENT_XLSX", "name": "Chachement area.xlsx — children aged 3 per pre-primary catchment", "base_url": None},
        {"code": "GEOBOUNDARIES", "name": "geoBoundaries RWA (Open Data Rwanda 2012), CC BY 4.0", "base_url": "https://www.geoboundaries.org"},
    ], "code")

    # ---- reference data
    years = upsert(session, M.AcademicYear.__table__, [{"year": y} for y in P.YEARS], "year")
    base_year = years[P.BASE_YEAR]
    run = M.ImportRun(source_id=sources["VERSION2_XLSX"], endpoint=A.SOURCE_XLSX.name, academic_year_id=base_year,
                      status="running", rows_received=len(roster), params={"catchment": P.CATCHMENT_XLSX.name})
    session.add(run)
    session.flush()

    levels = upsert(session, M.SchoolLevel.__table__, [
        {"code": key, "name": label, "entry_age": ENTRY_AGE.get(key), "duration_years": len(grades), "sort_order": i,
         "full_day": label in A.FULL_DAY}
        for i, (key, label, grades, _) in enumerate(A.LEVELS)
    ], "code")
    grade_rows = [{"code": g, "level_id": levels[key], "sequence": k + 1}
                  for key, _, grades, _ in A.LEVELS for k, g in enumerate(grades)]
    grades = upsert(session, M.Grade.__table__, grade_rows, "code")
    for key, _, gs, _ in A.LEVELS:  # progression: next grade in the level, then into the next level
        for k, g in enumerate(gs):
            nxt = gs[k + 1] if k + 1 < len(gs) else NEXT_LEVEL.get(g)
            session.execute(update(M.Grade).where(M.Grade.id == grades[g]).values(next_grade_id=grades.get(nxt)))
    session.execute(pg_insert(M.LevelNorm.__table__).values([
        {"level_id": levels[key], "academic_year_id": base_year, "classroom_capacity": cap} for key, _, _, cap in A.LEVELS
    ]).on_conflict_do_update(index_elements=["level_id", "academic_year_id"],
                             set_={"classroom_capacity": pg_insert(M.LevelNorm.__table__).excluded.classroom_capacity}))

    # ---- administrative units (names as spelled in the roster; codes until NISR codes are loaded)
    province_of = {d: p for p, ds in A.PROVINCES.items() for d in ds}
    provinces = upsert(session, M.Province.__table__, [{"code": slug(p), "name": p} for p in A.PROVINCES], "code")
    info = A._school_info(roster)
    district_names = sorted(d for d in info["district"].unique() if d != A.UNKNOWN)
    districts = upsert(session, M.District.__table__, [
        {"code": slug(d), "province_id": provinces[slug(province_of[d])], "name": d} for d in district_names
    ], "code")
    pairs = sorted({(d, s) for d, s in info[["district", "sector"]].itertuples(index=False) if A.UNKNOWN not in (d, s)})
    sectors = upsert(session, M.Sector.__table__, [
        {"code": slug(d, s), "district_id": districts[slug(d)], "name": s} for d, s in pairs
    ], "code")
    upsert(session, M.Country.__table__, [{"code": "RWA", "name": "Rwanda"}], "code")

    geom = "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326))"
    session.execute(text(f"UPDATE countries SET geom = {geom} WHERE code = 'RWA'"),
                    [{"g": json.dumps(geojson("rwanda")[0]["geometry"])}])
    session.execute(text(f"UPDATE districts SET geom = {geom} WHERE code = :code"),
                    [{"g": json.dumps(f["geometry"]), "code": slug(f["properties"]["d"])} for f in geojson("districts")])
    session.execute(text(f"UPDATE sectors SET geom = {geom} WHERE code = :code"),
                    [{"g": json.dumps(f["geometry"]), "code": slug(f["properties"]["d"], f["properties"]["s"])}
                     for f in geojson("sectors")])

    # ---- schools (kept by code; schools missing from this load become inactive)
    schools = upsert(session, M.School.__table__, [
        {"mineduc_code": str(int(r.school_code)), "name": r.school_name,
         "sector_id": sectors.get(slug(r.district, r.sector)), "latitude": none(r.latitude), "longitude": none(r.longitude),
         "is_active": True, "import_run_id": run.id}
        for r in info.itertuples(index=False)
    ], "mineduc_code")
    session.execute(update(M.School).where(M.School.mineduc_code.not_in(list(schools))).values(is_active=False))
    session.execute(text("UPDATE schools SET geom = CASE WHEN latitude IS NULL OR longitude IS NULL THEN NULL "
                         "ELSE ST_SetSRID(ST_MakePoint(longitude::float8, latitude::float8), 4326) END"))

    # ---- replace the roster, rooms, catchments and quality issues
    session.execute(text("TRUNCATE class_groups, classrooms, catchment_population, data_quality_issues RESTART IDENTITY"))
    school_id = {int(k): v for k, v in schools.items()}
    rooms = (roster.groupby(["school_code", A.ROOM_ID], sort=False)
             .agg(source=("classroom_id", "first"), name=("classroom_name", "first")).reset_index())
    room_id = {(int(c), str(t)): i + 1 for i, (c, t) in enumerate(zip(rooms["school_code"], rooms[A.ROOM_ID]))}
    session.execute(insert(M.Classroom.__table__), [
        {"id": room_id[(int(r.school_code), str(getattr(r, A.ROOM_ID)))], "school_id": school_id[int(r.school_code)],
         "mineduc_classroom_id": str(getattr(r, A.ROOM_ID)), "source_classroom_id": none(r.source),
         "name": none(r.name), "import_run_id": run.id}
        for r in rooms.itertuples(index=False)
    ])
    session.execute(insert(M.ClassGroup.__table__), [
        {"id": i + 1, "academic_year_id": base_year, "school_id": school_id[int(r.school_code)], "grade_id": grades[r.grade],
         "name": none(r.class_group), "combination": none(r.combination),
         "classroom_id": room_id[(int(r.school_code), str(getattr(r, A.ROOM_ID)))],
         "students_total": int(r.students), "import_run_id": run.id}
        for i, r in enumerate(roster.rename(columns={A.STUDENTS: "students"}).itertuples(index=False))
    ])
    catch_rows = [
        {"school_id": school_id[int(code)], "year": int(y), "age": 3, "population": int(round(v)), "import_run_id": run.id}
        for code, row in pop.iterrows() if int(code) in school_id for y, v in row.items() if not pd.isna(v)
    ]
    session.execute(insert(M.CatchmentPopulation.__table__), catch_rows)
    dq = A.data_quality(roster)
    if len(dq):
        session.execute(insert(M.DataQualityIssue.__table__), [
            {"import_run_id": run.id, "academic_year_id": base_year, "school_id": school_id.get(int(r.school_code)),
             "entity": "class_groups", "issue_code": r.issue, "detail": none(r.detail)}
            for r in dq.itertuples(index=False)
        ])
    for table in ("classrooms", "class_groups", "catchment_population", "data_quality_issues"):
        reset_sequence(session, table)

    run.status, run.rows_loaded, run.finished_at = "success", len(roster), datetime.now(timezone.utc)
    counts = {
        "schools": len(schools), "sectors": len(sectors), "districts": len(districts), "classrooms": len(room_id),
        "class_groups": len(roster), "catchment_values": len(catch_rows), "quality_issues": len(dq),
    }
    run.params = {**(run.params or {}), "counts": counts}
    return {"import_run": run.id, **counts, "seconds": round(time.time() - t0)}


def main() -> None:
    with SessionLocal() as session, session.begin():
        result = load(session)
    print("loaded:", result)
    missing = select(M.School.id).where(M.School.geom.is_(None), M.School.is_active)
    with SessionLocal() as session:
        print("active schools without coordinates:", len(session.execute(missing).all()))


if __name__ == "__main__":
    main()
