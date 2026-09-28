"""Helpers shared by the routers."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import Response

from ..domain import projection as P
from ..schemas import Intake
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
    defaults: Intake = store.snapshot.default_intake
    n_years = len(P.YEARS) - 1
    out: Intake = {g: {d: list(v) for d, v in t.items()} for g, t in defaults.items()}
    for grade, table in (intake or {}).items():
        if grade not in defaults:
            raise HTTPException(422, f"Unknown entry grade {grade!r}; the plan covers {', '.join(defaults)}.")
        for district, values in table.items():
            if district not in defaults[grade]:
                raise HTTPException(422, f"Unknown district {district!r}.")
            if len(values) != n_years or any((not isinstance(v, int)) or v < 0 for v in values):
                raise HTTPException(422, f"{grade} / {district}: expected {n_years} whole numbers >= 0 ({P.YEARS[1]}-{P.YEARS[-1]}).")
            out[grade][district] = list(values)
    return out
