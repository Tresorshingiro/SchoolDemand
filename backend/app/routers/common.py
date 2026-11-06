"""Helpers shared by the routers."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..domain import new_schools as NS
from ..schemas import Intake, PlannedSchoolIn
from ..services import repository as R
from ..services.store import Payload, store


def json_payload(request: Request, payload: Payload, *, max_age: int = 300) -> Response:
    """Send a prepared JSON body, gzipped when the browser accepts it. Private: only for the signed-in browser."""
    headers = {"Cache-Control": f"private, max-age={max_age}", "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(payload.gz, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(payload.raw, media_type="application/json", headers=headers)


def require_data() -> None:
    if not store.ready:
        raise HTTPException(503, "No data loaded yet: run the import job (python -m etl.load_version2), then reload.")


def complete_intake(intake: Intake | None) -> Intake:
    """Validate a plan and fill what it leaves out from the default plan (every district, every year)."""
    snap = store.snapshot
    defaults: Intake = snap.default_intake
    years = snap.horizon.future
    n_years = len(years)
    out: Intake = {g: {d: list(v) for d, v in t.items()} for g, t in defaults.items()}
    for grade, table in (intake or {}).items():
        if grade not in defaults:
            raise HTTPException(422, f"Unknown entry grade {grade!r}; the plan covers {', '.join(defaults)}.")
        for district, values in table.items():
            if district not in defaults[grade]:
                raise HTTPException(422, f"Unknown district {district!r}.")
            if len(values) != n_years or any((not isinstance(v, int)) or v < 0 for v in values):
                raise HTTPException(422, f"{grade} / {district}: expected {n_years} whole numbers >= 0 ({years[0]}-{years[-1]}).")
            out[grade][district] = list(values)
    return out


def complete_schools(schools: list[PlannedSchoolIn] | None, session: Session) -> tuple[NS.PlannedSchool, ...]:
    """Validate planned new schools and place them in their district and sector."""
    years = store.snapshot.horizon.future
    if schools and store.walking is None:
        raise HTTPException(422, NS.NO_WALKING)
    out = []
    for s in schools or []:
        if not s.levels or any(k not in NS.LEVEL_KEYS for k in s.levels) \
                or {NS.LEVEL_KEYS[k] for k in s.levels} not in NS.ALLOWED_LEVEL_SETS:
            raise HTTPException(422, "A new school offers one level, or Pre-Primary and Primary together.")
        if any(not 1 <= n <= 200 for n in s.levels.values()):
            raise HTTPException(422, f"{s.name}: the number of classrooms must be between 1 and 200.")
        if s.opening_year not in years:
            raise HTTPException(422, f"The opening year must be between {years[0]} and {years[-1]}.")
        place = R.locate(session, s.latitude, s.longitude)
        if place is None:
            raise HTTPException(422, "This point is outside Rwanda's sectors.")
        classrooms = tuple((label, s.levels[k]) for k, label in NS.LEVEL_KEYS.items() if k in s.levels)
        out.append(NS.PlannedSchool(s.name.strip(), s.latitude, s.longitude, place[0], place[1], classrooms,
                                    s.opening_year, float(s.walking_km)))
    return tuple(out)
