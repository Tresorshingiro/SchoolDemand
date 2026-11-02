"""The import lifecycle: upload -> check -> ready -> publish (or discard); withdraw; history.

Jobs (run_check, run_publish, run_withdraw) run on the worker thread with their own database session.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import models as M
from ..config import settings
from ..db import SessionLocal
from ..domain import analysis as A
from ..domain import projection as P
from ..domain import walking as WK
from ..domain.walking import WalkingNetwork
from ..services import repository as R
from ..services.audit import audit
from . import publish as PUB
from .checks import CHECKS, CheckContext
from .tables import read_table

KINDS = {  # kind -> (data_sources.code, label)
    "school_data": ("SCHOOL_DATA", "School data (MINEDUC)"),
    "catchment": ("CATCHMENT", "Catchment (GIS)"),
    "nisr_population": ("NISR_POPULATION", "NISR population (age 3, district)"),
    "flow_rates": ("FLOW_RATES", "Repetition and dropout (MINEDUC)"),
    "teachers": ("TEACHERS", "Teachers (MINEDUC)"),
    "walking_network": ("WALKING_NETWORK", "Walking network (OpenStreetMap)"),
}
YEAR_KINDS = {"school_data", "teachers"}  # one live import per school year
WORKBOOKS = {"flow_rates"}  # read with every sheet
NETWORK = "walking_network"  # an .osm.pbf: checked from its path, kept as a file (no rows in the database)
MAX_BYTES = 50 * 1024 * 1024
MAX_NETWORK_BYTES = 200 * 1024 * 1024
EXTENSIONS = {".xlsx", ".csv"}
PUBLISHABLE = {"ready", "superseded", "withdrawn"}
BUSY = {"uploaded", "checking", "publishing", "withdrawing"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upload_dir() -> Path:
    p = settings.upload_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def file_path(run: M.ImportRun) -> Path:
    return upload_dir() / f"{run.file_sha256}{Path(run.file_name or '').suffix.lower()}"


def parsed_path(run: M.ImportRun) -> Path:
    return upload_dir() / f"import-{run.id}.parsed.pkl"


def issues_path(run: M.ImportRun) -> Path:
    return upload_dir() / f"import-{run.id}.issues.csv"


def network_path(run: M.ImportRun) -> Path:
    return R.network_file(run)


def max_bytes(kind: str) -> int:
    return MAX_NETWORK_BYTES if kind == NETWORK else MAX_BYTES


def already_live(current: M.ImportRun | None, sha: str) -> bool:
    """Is this file the live one? A live network whose routing file was lost or damaged is not: it can be uploaded again."""
    if current is None or current.file_sha256 != sha:
        return False
    return current.kind != NETWORK or network_usable(current)


def network_usable(run: M.ImportRun) -> bool:
    return WK.usable(network_path(run))


def _rows(parsed) -> int:
    return parsed.nodes if isinstance(parsed, WalkingNetwork) else len(parsed)


def _keep_parsed(run: M.ImportRun, parsed) -> None:
    if isinstance(parsed, WalkingNetwork):
        parsed.save(network_path(run))
    else:
        pd.to_pickle(parsed, parsed_path(run))


def label(run: M.ImportRun) -> str:
    year = f" {run.academic_year}" if run.academic_year else ""
    return f"{KINDS[run.kind][1]}{year} · {run.file_name}"


def live(session: Session, kind: str, year: int | None = None) -> M.ImportRun | None:
    q = select(M.ImportRun).where(M.ImportRun.is_live, M.ImportRun.kind == kind)
    if kind in YEAR_KINDS:
        q = q.where(M.ImportRun.academic_year == year)
    return session.scalar(q)


def can_publish(run: M.ImportRun) -> bool:
    return run.status in PUBLISHABLE and bool(run.report) and not run.report.get("errors")


# ---------------------------------------------------------------- upload
def create_upload(session: Session, *, kind: str, file_name: str, content: bytes, academic_year: int | None,
                  user: M.User | None) -> M.ImportRun:
    if kind not in KINDS:
        raise HTTPException(422, f"Unknown kind of data {kind!r}.")
    ext = Path(file_name).suffix.lower()
    if kind == NETWORK:
        if not file_name.lower().endswith(".osm.pbf"):
            raise HTTPException(422, "Upload the OpenStreetMap extract, an .osm.pbf file.")
    elif ext not in EXTENSIONS:
        raise HTTPException(422, "Upload an .xlsx or .csv file.")
    if not content:
        raise HTTPException(422, "The file is empty.")
    if len(content) > max_bytes(kind):
        raise HTTPException(413, f"The file is larger than {max_bytes(kind) // (1024 * 1024)} MB.")
    if kind in WORKBOOKS and ext != ".xlsx":
        raise HTTPException(422, "Upload the .xlsx file with its two sheets (Repetition Rate, Dropout Rate).")
    if kind in YEAR_KINDS:
        if academic_year is None:
            raise HTTPException(422, "Choose the school year of this file.")
        if not 2000 <= academic_year <= 2100:
            raise HTTPException(422, "The school year must be between 2000 and 2100.")
    else:
        academic_year = None
    sha = hashlib.sha256(content).hexdigest()
    current = live(session, kind, academic_year)
    if already_live(current, sha):
        when = f"{current.published_at:%d %b %Y}".lstrip("0") if current.published_at else "earlier"
        raise HTTPException(409, f"This file is already live (published {when}).")
    path = upload_dir() / f"{sha}{ext}"
    if not path.exists():
        path.write_bytes(content)
    run = M.ImportRun(source_id=session.scalar(select(M.DataSource.id).where(M.DataSource.code == KINDS[kind][0])),
                      kind=kind, academic_year=academic_year, endpoint=file_name[:200], file_name=file_name[:255],
                      file_sha256=sha, file_size=len(content), status="uploaded", progress=0,
                      uploaded_by_id=user.id if user else None)
    session.add(run)
    session.flush()
    audit(session, user, "data.upload", label(run))
    session.commit()
    return run


# ---------------------------------------------------------------- check
def build_context(session: Session) -> CheckContext:
    years = R.school_years(session)
    horizon = P.Horizon(years[-1]) if years else P.DEFAULT_HORIZON
    sectors = {(d, s) for d, s in session.execute(
        select(M.District.name, M.Sector.name).join(M.Sector, M.Sector.district_id == M.District.id)).all()}
    districts = sorted(session.scalars(select(M.District.name)).all())
    cache: dict[int, pd.DataFrame] = {}

    def roster_of(year: int) -> pd.DataFrame:
        if year not in cache:
            cache[year] = R.read_roster(session, year)
        return cache[year]

    preprimary, totals = set(), None
    if years:
        roster = roster_of(years[-1])
        preprimary = set(roster.loc[roster["level"] == A.LEVEL_ORDER[0], "school_code"].astype(int))
        catchment = R.read_catchment(session, roster, horizon)
        totals = P.default_intake(catchment, A._school_info(roster))["N1"]
    network = live(session, NETWORK)
    network_km = ((network.report or {}).get("summary") or {}).get("km") if network else None
    return CheckContext(horizon, sectors, districts, years, preprimary, totals, roster_of, network_km)


def _check(session: Session, run: M.ImportRun) -> tuple[pd.DataFrame | WalkingNetwork | None, dict, pd.DataFrame, int]:
    raw = file_path(run) if run.kind == NETWORK else read_table(file_path(run), all_sheets=run.kind in WORKBOOKS)
    parsed, rep = CHECKS[run.kind](raw, run.academic_year, build_context(session))
    data = rep.to_json()
    current = live(session, run.kind, run.academic_year)
    data["checked_against"] = current.id if current else None
    if run.kind == NETWORK:
        rows = parsed.nodes if parsed is not None else 0
    else:
        rows = sum(len(t) for t in raw.values()) if isinstance(raw, dict) else len(raw)
    return parsed, data, rep.issues(), rows


def run_check(run_id: int) -> None:
    with SessionLocal() as s:
        run = s.get(M.ImportRun, run_id)
        run.status, run.progress, run.error, run.report = "checking", 10, None, None
        s.commit()
        try:
            parsed, report, issues, n = _check(s, run)
            if parsed is not None:
                _keep_parsed(run, parsed)
            if len(issues):
                issues.to_csv(issues_path(run), index=False, encoding="utf-8-sig")
            run.report, run.rows_received = report, n
            run.status, run.progress, run.finished_at = "ready", 100, _now()
        except Exception as e:  # noqa: BLE001 — an unreadable file is reported on the import, not raised
            s.rollback()
            run = s.get(M.ImportRun, run_id)
            run.status, run.progress, run.error = "failed", 0, f"The file could not be read: {e}"
        s.commit()


# ---------------------------------------------------------------- publish, withdraw
def _parsed(session: Session, run: M.ImportRun) -> pd.DataFrame | WalkingNetwork:
    """The checked rows or network (read again from the file when they are no longer kept)."""
    if run.kind == NETWORK:
        if network_usable(run):
            return WalkingNetwork.load(network_path(run))
    elif parsed_path(run).exists():
        return pd.read_pickle(parsed_path(run))
    parsed, report, _, _ = _check(session, run)
    if parsed is None:
        raise ValueError("the file no longer passes the checks: " + report["errors"][0]["message"])
    _keep_parsed(run, parsed)
    return parsed


def _reload(run_id: int) -> None:
    from ..services.store import store  # noqa: PLC0415 — the store reads the database this module just changed
    try:
        store.load()
    except Exception as e:  # noqa: BLE001 — the data is published; the portal offers "Reload data"
        with SessionLocal() as s:
            s.get(M.ImportRun, run_id).error = f"Published, but the site could not reload the data ({e}). Use Reload data."
            s.commit()


def run_publish(run_id: int, user_id: int | None, again: bool = False, reload: bool = True) -> None:
    with SessionLocal() as s:
        run = s.get(M.ImportRun, run_id)
        user = s.get(M.User, user_id) if user_id else None
        try:
            parsed = _parsed(s, run)
            previous = live(s, run.kind, run.academic_year)
            if previous is not None and previous.id != run.id:
                previous.is_live, previous.status = False, "superseded"
                s.flush()  # one live import per kind (and school year)
            PUB.PUBLISH[run.kind](s, run, parsed)
            run.is_live, run.status, run.progress, run.error = True, "published", 100, None
            run.published_at, run.published_by_id, run.rows_loaded = _now(), user_id, _rows(parsed)
            audit(s, user, "data.republish" if again else "data.publish", label(run))
            s.commit()
        except Exception as e:  # noqa: BLE001
            s.rollback()
            run = s.get(M.ImportRun, run_id)
            run.status, run.error = "failed", f"Publishing failed; the live data is unchanged: {e}"
            s.commit()
            return
    if reload:
        _reload(run_id)


def check_withdraw(session: Session, run: M.ImportRun) -> None:
    if not run.is_live:
        raise HTTPException(409, "Only live data can be withdrawn.")
    if run.kind == "catchment":
        raise HTTPException(409, "Publish another catchment file instead: the projection needs one.")
    if run.kind == "flow_rates":
        raise HTTPException(409, "Publish another rates file instead: the projection needs one.")
    if run.kind == NETWORK:
        raise HTTPException(409, "Publish another walking network instead: planned schools need one.")
    if run.kind == "school_data" and R.school_years(session) == [run.academic_year]:
        raise HTTPException(409, "This is the only school year: publish another one before withdrawing it.")


def run_withdraw(run_id: int, user_id: int | None, reload: bool = True) -> None:
    with SessionLocal() as s:
        run = s.get(M.ImportRun, run_id)
        try:
            PUB.withdraw_rows(s, run)
            run.is_live, run.status, run.error = False, "withdrawn", None
            audit(s, s.get(M.User, user_id) if user_id else None, "data.withdraw", label(run))
            s.commit()
        except Exception as e:  # noqa: BLE001
            s.rollback()
            run = s.get(M.ImportRun, run_id)
            run.status, run.error = "published", f"Withdrawing failed; the live data is unchanged: {e}"
            s.commit()
            return
    if reload:
        _reload(run_id)


# ---------------------------------------------------------------- what publishing would do
def consequence(session: Session, run: M.ImportRun) -> str:
    if run.kind == "school_data":
        years, y = R.school_years(session), run.academic_year
        if y in years:
            return f"Replaces the live {y} data."
        if years and y < max(years):
            return f"Adds {y} as a past school year; the projection stays on {max(years)}."
        n = 0
        if years:
            base_id = session.scalar(select(M.AcademicYear.id).where(M.AcademicYear.year == max(years)))
            n = session.scalar(select(func.count()).select_from(M.ProjectionScenario)
                               .where(M.ProjectionScenario.base_year_id == base_id))
        plans = f" and {n} saved plan{'s' if n != 1 else ''} will be archived" if n else ""
        return f"{y} becomes the base year. The projection moves to {y + 1}-{y + P.HORIZON_YEARS}{plans}."
    if run.kind == "catchment":
        return "Replaces the live catchment figures: the default N1 plan and how N1 is shared between schools follow them."
    if run.kind == "flow_rates":
        return "Replaces the repetition and dropout rates: every projected year follows them."
    if run.kind == NETWORK:
        return "Replaces the walking network: the schools each planned school can take students from follow it."
    if run.kind == "teachers":
        current = live(session, "teachers", run.academic_year)
        return (f"Replaces the {run.academic_year} teachers." if current is not None
                else f"Adds teachers for {run.academic_year}.")
    return ("The default N1 plan follows these NISR district totals "
            "(districts not in the file keep their catchment totals).")


def mark_interrupted() -> int:
    """At startup: jobs that were running when the API stopped are marked failed."""
    with SessionLocal() as s:
        n = s.execute(update(M.ImportRun).where(M.ImportRun.status.in_(["uploaded", "checking"]))
                      .values(status="failed", progress=0,
                              error="Interrupted (the API restarted) - run the check again.")).rowcount
        n += s.execute(update(M.ImportRun).where(M.ImportRun.status == "publishing")
                       .values(status="failed", error="Interrupted while publishing; the live data is unchanged.")).rowcount
        n += s.execute(update(M.ImportRun).where(M.ImportRun.status == "withdrawing")
                       .values(status="published", error="Interrupted while withdrawing; the data is still live.")).rowcount
        s.commit()
    return n
