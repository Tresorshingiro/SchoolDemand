"""
In-memory store behind the API: the 2026 data and the projection inputs are read from the database once (at startup
and on /api/admin/reload) and served from memory. Responses are kept as ready-made JSON bytes, plain and gzipped.
Projection runs are cached per intake plan (least recently used first out).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

import pandas as pd

from ..config import settings
from ..db import SessionLocal
from ..domain import dashboard as D
from ..domain import projection as P
from . import repository as R


@dataclass(frozen=True)
class Payload:
    """A JSON response body, plain and gzipped."""
    raw: bytes
    gz: bytes

    @classmethod
    def of(cls, obj) -> Payload:
        raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return cls(raw, gzip.compress(raw, compresslevel=6))


@dataclass
class Snapshot:
    """Everything loaded from one state of the database."""
    roster: pd.DataFrame
    base: P.Base
    catchment: pd.DataFrame
    payloads: dict[str, Payload]  # meta, school-levels, grades, combos, projection-config, boundaries/*
    default_intake: dict[str, dict[str, list[int]]]  # the default plan: {"N1": {district: [2027 ...]}}
    import_run: dict
    loaded_at: float


def plan_key(intake: dict[str, dict[str, list[int]]] | None) -> str:
    return hashlib.sha1(json.dumps(intake or {}, sort_keys=True).encode()).hexdigest()


def intake_frames(intake: dict[str, dict[str, list[int]]]) -> dict[str, pd.DataFrame]:
    """{"N1": {district: [2027, 2028, ...]}} -> {"N1": district x year DataFrame} for P.project."""
    years = P.YEARS[1:]
    return {g: pd.DataFrame({d: v for d, v in t.items()}, index=years).T for g, t in intake.items() if t}


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snap: Snapshot | None = None
        self._runs: OrderedDict[str, Payload] = OrderedDict()

    @property
    def ready(self) -> bool:
        return self._snap is not None

    @property
    def snapshot(self) -> Snapshot:
        if self._snap is None:
            raise RuntimeError("No data loaded yet: run the import job (python -m etl.load_version2), then reload.")
        return self._snap

    def load(self) -> dict:
        """(Re)read the database. The previous data keeps being served until the new one is ready."""
        t0 = time.time()
        with SessionLocal() as session:
            run = R.latest_import(session)
            if run is None:
                raise RuntimeError("The database has no successful import yet: run python -m etl.load_version2")
            roster = R.read_roster(session)
            catchment = R.read_catchment(session, roster)
            shapes = R.boundaries(session)
            import_run = {"id": run.id, "source": run.endpoint, "finished": run.finished_at.isoformat() if run.finished_at else None}
        base = P.base_schools(roster)
        data = D.current(roster, source=run.endpoint or "database",
                         built=run.finished_at.date().isoformat() if run.finished_at else None)
        config = D.projection_config(base, catchment)
        payloads = {
            "meta": Payload.of(data["meta"]),
            "school-levels": Payload.of(data["school_levels"]),
            "grades": Payload.of(data["grades"]),
            "combos": Payload.of(data["combos"]),
            "projection-config": Payload.of(config),
            **{f"boundaries/{k}": Payload.of(v) for k, v in shapes.items()},
        }
        snap = Snapshot(roster, base, catchment, payloads, config["population"], import_run, time.time())
        default = self._compute(snap, None)
        with self._lock:
            self._snap = snap
            self._runs.clear()
            self._runs[plan_key(None)] = default
        return {"import_run": import_run, "class_groups": len(roster), "seconds": round(time.time() - t0, 1)}

    def payload(self, name: str) -> Payload:
        return self.snapshot.payloads[name]

    def projection(self, intake: dict[str, dict[str, list[int]]] | None) -> Payload:
        """The projection for an intake plan (None = the default catchment plan), cached."""
        key = plan_key(intake)
        with self._lock:
            if key in self._runs:
                self._runs.move_to_end(key)
                return self._runs[key]
            snap = self.snapshot
        result = self._compute(snap, intake)
        with self._lock:
            if self._snap is snap:  # not reloaded meanwhile
                self._runs[key] = result
                while len(self._runs) > max(settings.projection_cache_size, 1):
                    self._runs.popitem(last=False)
        return result

    @staticmethod
    def _compute(snap: Snapshot, intake: dict[str, dict[str, list[int]]] | None) -> Payload:
        _, schools, grades, combos = P.project(snap.roster, intake_frames(intake) if intake else None,
                                               catchment=snap.catchment, base=snap.base)
        return Payload.of(D.encode_projection(schools, grades, combos))


store = Store()
