"""
Load the development data through the same pipeline as the admin portal (upload -> check -> publish):

  Version 2.xlsx                   2026 school data (schools, rooms, class groups)
  Chachement area.xlsx             children aged 3 per pre-primary school catchment
  NISR population.xlsx / .csv      children aged 3 per district (optional; pop3_YYYY columns)
  Repetition and dropout rates.xlsx  MINEDUC repetition and dropout per district (the projection needs them)
  Teachers.xlsx                    MINEDUC teachers per school and level (loaded as the newest school year)
  rwanda-latest.osm.pbf            OpenStreetMap roads and paths, for planned schools' walking distance (optional)
  boundaries/*.geojson             country, district and sector outlines (scripts/build_boundaries.py)

from SCHOOL_DATA_DIR (data-sources/ in the repository, /data in the API container). Reference tables, provinces,
districts and sectors are upserted by their code first. A file already live is skipped, so the job can be re-run, and
so is a kind whose live data came from another file (an upload in the admin portal): --replace publishes over it.
The API picks the new data up on restart or POST /api/admin/reload.

Run (from backend/):  python -m etl.load_version2 [--replace]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app import models as M
from app.db import SessionLocal
from app.domain import analysis as A
from app.domain import projection as P
from app.domain import rates as RT
from app.domain import teachers as T
from app.imports import service as S
from app.imports.sql import upsert
from app.services import repository as R

BOUNDARIES = A.DATA_DIR / "boundaries"
NISR_FILES = [A.DATA_DIR / "NISR population.xlsx", A.DATA_DIR / "NISR population.csv"]
WALKING_NETWORK = A.DATA_DIR / "rwanda-latest.osm.pbf"  # optional: Geofabrik's Rwanda extract
ENTRY_AGE = {"NUR": 3, "PRI": 6, "LSE": 12, "USE": 15, "TVE": 15, "TTC": 15}  # official entry age of each level
NEXT_LEVEL = {"N3": "P1", "P6": "S1", "S3": "S4"}  # progression between levels (S3 also feeds L3 / Y1)


def slug(*parts: str) -> str:
    return "/".join(str(p).strip().upper() for p in parts)


def geojson(name: str) -> list[dict]:
    return json.loads((BOUNDARIES / f"{name}.geojson").read_text(encoding="utf-8"))["features"]


def ensure_reference(session: Session) -> None:
    """Data sources, levels, grades, provinces / districts / sectors (from the boundaries) and their outlines."""
    upsert(session, M.DataSource.__table__, [
        {"code": code, "name": label, "base_url": None} for code, label in S.KINDS.values()
    ] + [{"code": "GEOBOUNDARIES", "name": "geoBoundaries RWA (Open Data Rwanda 2012), CC BY 4.0",
          "base_url": "https://www.geoboundaries.org"}], "code")
    levels = upsert(session, M.SchoolLevel.__table__, [
        {"code": key, "name": label, "entry_age": ENTRY_AGE.get(key), "duration_years": len(grades), "sort_order": i,
         "full_day": label in A.FULL_DAY}
        for i, (key, label, grades, _) in enumerate(A.LEVELS)
    ], "code")
    grades = upsert(session, M.Grade.__table__, [
        {"code": g, "level_id": levels[key], "sequence": k + 1} for key, _, gs, _ in A.LEVELS for k, g in enumerate(gs)
    ], "code")
    for _, _, gs, _ in A.LEVELS:  # progression: next grade in the level, then into the next level
        for k, g in enumerate(gs):
            nxt = gs[k + 1] if k + 1 < len(gs) else NEXT_LEVEL.get(g)
            session.execute(update(M.Grade).where(M.Grade.id == grades[g]).values(next_grade_id=grades.get(nxt)))

    province_of = {d: p for p, ds in A.PROVINCES.items() for d in ds}
    provinces = upsert(session, M.Province.__table__, [{"code": slug(p), "name": p} for p in A.PROVINCES], "code")
    district_names = sorted({f["properties"]["d"] for f in geojson("districts")})
    districts = upsert(session, M.District.__table__, [
        {"code": slug(d), "province_id": provinces[slug(province_of[d])], "name": d} for d in district_names
    ], "code")
    pairs = sorted({(f["properties"]["d"], f["properties"]["s"]) for f in geojson("sectors")})
    upsert(session, M.Sector.__table__, [
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


def load_file(kind: str, path: Path, year: int | None = None, replace: bool = False) -> str:
    """Upload, check and publish one file (the API is not reloaded: restart it or POST /api/admin/reload). Live data
    published from another file (an upload in the admin portal) is kept unless `replace`."""
    with SessionLocal() as s:
        current = S.live(s, kind, year)
        if current is not None and current.file_name != path.name and not replace:
            return (f"{path.name}: skipped - the live data is {current.file_name} (import {current.id}); upload this "
                    "file in the admin portal to replace it, or run with --replace")
        try:
            run = S.create_upload(s, kind=kind, file_name=path.name, content=path.read_bytes(), academic_year=year,
                                  user=None)
        except HTTPException as e:
            return f"{path.name}: {e.detail}"
        run_id = run.id
    S.run_check(run_id)
    with SessionLocal() as s:
        run = s.get(M.ImportRun, run_id)
        if run.status != "ready" or not S.can_publish(run):
            problems = run.error or "; ".join(e["message"] for e in run.report["errors"])
            return f"{path.name}: not published - {problems}"
        warnings = len(run.report["warnings"])
    S.run_publish(run_id, None, reload=False)
    with SessionLocal() as s:
        run = s.get(M.ImportRun, run_id)
        return f"{path.name}: {run.status} ({run.rows_loaded or 0} rows, {warnings} warning type(s))" + (
            f" - {run.error}" if run.error else "")


def teachers_year() -> int:
    """The school year Teachers.xlsx is loaded as: the newest published school year (2026 before any is)."""
    with SessionLocal() as s:
        return max(R.school_years(s), default=P.BASE_YEAR)


def main(replace: bool = False) -> None:
    with SessionLocal() as session, session.begin():
        ensure_reference(session)
    print("reference data and boundaries: ok")
    print(load_file("school_data", A.SOURCE_XLSX, P.BASE_YEAR, replace))
    print(load_file("catchment", P.CATCHMENT_XLSX, replace=replace))
    print(load_file("flow_rates", RT.RATES_XLSX, replace=replace))
    if T.TEACHERS_XLSX.exists():
        print(load_file("teachers", T.TEACHERS_XLSX, teachers_year(), replace))
    for path in NISR_FILES:
        if path.exists():
            print(load_file("nisr_population", path, replace=replace))
    if WALKING_NETWORK.exists():
        print(load_file("walking_network", WALKING_NETWORK, replace=replace))


if __name__ == "__main__":
    main(replace="--replace" in sys.argv[1:])
