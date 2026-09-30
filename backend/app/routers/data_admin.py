"""The admin portal's Data pages: upload, check, publish, withdraw, history. Administrators only."""
from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..domain import projection as P
from ..imports import service as S
from ..imports import worker
from ..imports.checks import TEMPLATES
from ..schemas import ImportDetailOut, ImportOut
from ..services import repository as R
from ..services.audit import audit
from ..services.auth import require_admin

router = APIRouter(prefix="/admin/data", tags=["admin data"], dependencies=[Depends(require_admin)])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _names(session: Session) -> dict[int, str]:
    return dict(session.execute(select(M.User.id, func.coalesce(M.User.full_name, M.User.email))).all())


def _out(run: M.ImportRun, names: dict[int, str]) -> ImportOut:
    return ImportOut(id=run.id, kind=run.kind, label=S.KINDS[run.kind][1], academic_year=run.academic_year,
                     file_name=run.file_name, file_size=run.file_size, status=run.status, progress=run.progress,
                     is_live=run.is_live, uploaded_by=names.get(run.uploaded_by_id), uploaded_at=run.started_at,
                     published_by=names.get(run.published_by_id), published_at=run.published_at, error=run.error)


def _detail(session: Session, run: M.ImportRun) -> ImportDetailOut:
    session.refresh(run)
    return ImportDetailOut(**_out(run, _names(session)).model_dump(), report=run.report, can_publish=S.can_publish(run),
                           consequence=S.consequence(session, run) if run.status not in S.BUSY else None)


def _get(session: Session, run_id: int) -> M.ImportRun:
    run = session.get(M.ImportRun, run_id)
    if run is None:
        raise HTTPException(404, f"No import {run_id}.")
    return run


@router.get("/sources", summary="The live data of each kind")
def sources(session: Session = Depends(get_session)) -> list[dict]:
    names = _names(session)
    live = session.scalars(select(M.ImportRun).where(M.ImportRun.is_live)
                           .order_by(M.ImportRun.academic_year.desc())).all()
    return [{"kind": kind, "label": lab, "live": [_out(r, names) for r in live if r.kind == kind],
             "connector": "not set up" if kind == "school_data" else None} for kind, (_, lab) in S.KINDS.items()]


@router.post("/uploads", status_code=202, response_model=ImportDetailOut, summary="Upload a file; it is checked next")
async def upload(kind: str = Form(...), academic_year: int | None = Form(None), file: UploadFile = File(...),
                 session: Session = Depends(get_session), admin: M.User = Depends(require_admin)):
    content = await file.read(S.MAX_BYTES + 1)
    run = S.create_upload(session, kind=kind, file_name=file.filename or "upload", content=content,
                          academic_year=academic_year, user=admin)
    worker.submit(S.run_check, run.id)
    return _detail(session, run)


@router.get("/imports", response_model=list[ImportOut], summary="Every import, newest first")
def imports(kind: str | None = None, session: Session = Depends(get_session)):
    q = select(M.ImportRun).order_by(M.ImportRun.id.desc())
    if kind:
        q = q.where(M.ImportRun.kind == kind)
    names = _names(session)
    return [_out(r, names) for r in session.scalars(q).all()]


@router.get("/imports/{run_id}", response_model=ImportDetailOut, summary="One import with its check report")
def import_detail(run_id: int, session: Session = Depends(get_session)):
    return _detail(session, _get(session, run_id))


@router.get("/imports/{run_id}/file", summary="The uploaded file")
def import_file(run_id: int, session: Session = Depends(get_session)):
    run = _get(session, run_id)
    path = S.file_path(run) if run.file_sha256 else None
    if path is None or not path.exists():
        raise HTTPException(404, "The file of this import is not kept.")
    return FileResponse(path, filename=run.file_name)


@router.get("/imports/{run_id}/issues.csv", summary="Every row concerned by an error or a warning")
def import_issues(run_id: int, session: Session = Depends(get_session)):
    path = S.issues_path(_get(session, run_id))
    if not path.exists():
        raise HTTPException(404, "This import has no problem rows.")
    return FileResponse(path, filename=f"import-{run_id}-problems.csv", media_type="text/csv")


@router.post("/imports/{run_id}/publish", status_code=202, response_model=ImportDetailOut,
             summary="Make this import the live data (or publish an earlier one again)")
def publish(run_id: int, session: Session = Depends(get_session), admin: M.User = Depends(require_admin)):
    run = _get(session, run_id)
    if not S.can_publish(run):
        reason = ("fix the errors in the report and upload the file again" if run.report and run.report.get("errors")
                  else f"it is {run.status}")
        raise HTTPException(409, f"This import cannot be published: {reason}.")
    current = S.live(session, run.kind, run.academic_year)
    if run.status == "ready" and (current.id if current else None) != run.report.get("checked_against"):
        run.status = "uploaded"
        session.commit()
        worker.submit(S.run_check, run.id)
        raise HTTPException(409, "The live data changed since this file was checked: it is being checked again. "
                                 "Look at the new report, then publish.")
    again = run.status in ("superseded", "withdrawn")
    run.status, run.error = "publishing", None
    session.commit()
    worker.submit(S.run_publish, run.id, admin.id, again)
    return _detail(session, run)


@router.post("/imports/{run_id}/withdraw", status_code=202, response_model=ImportDetailOut,
             summary="Remove live data (a school year when another stays, or the NISR figures)")
def withdraw(run_id: int, session: Session = Depends(get_session), admin: M.User = Depends(require_admin)):
    run = _get(session, run_id)
    S.check_withdraw(session, run)
    run.status = "withdrawing"
    session.commit()
    worker.submit(S.run_withdraw, run.id, admin.id)
    return _detail(session, run)


@router.post("/imports/{run_id}/discard", response_model=ImportDetailOut, summary="Drop an import that is not live")
def discard(run_id: int, session: Session = Depends(get_session), admin: M.User = Depends(require_admin)):
    run = _get(session, run_id)
    if run.is_live or run.status not in ("ready", "failed"):
        raise HTTPException(409, f"Only a checked or failed import can be discarded (this one is {run.status}).")
    run.status = "discarded"
    audit(session, admin, "data.discard", S.label(run))
    session.commit()
    return _detail(session, run)


@router.post("/imports/{run_id}/recheck", status_code=202, response_model=ImportDetailOut, summary="Check again")
def recheck(run_id: int, session: Session = Depends(get_session)):
    run = _get(session, run_id)
    if run.status != "failed" or run.is_live:
        raise HTTPException(409, "Only a failed import can be checked again.")
    run.status, run.error = "uploaded", None
    session.commit()
    worker.submit(S.run_check, run.id)
    return _detail(session, run)


@router.get("/templates/{kind}", summary="An example file with the expected columns")
def template(kind: str, session: Session = Depends(get_session)) -> Response:
    if kind not in TEMPLATES:
        raise HTTPException(404, f"Unknown kind of data {kind!r}.")
    years = R.school_years(session)
    buf = BytesIO()
    TEMPLATES[kind](P.Horizon(years[-1]) if years else P.DEFAULT_HORIZON).to_excel(buf, index=False)
    return Response(buf.getvalue(), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="template_{kind}.xlsx"'})
