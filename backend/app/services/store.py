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
    rosters: dict[int, pd.DataFrame]  # every published school year
    horizon: P.Horizon                # base = the newest school year
    base: P.Base
    catchment: pd.DataFrame
    payloads: dict[str, Payload]      # meta/<y>, school-levels/<y>, grades/<y>, combos/<y>, projection-config, boundaries/*
    default_intake: dict[str, dict[str, list[int]]]  # the default plan: {"N1": {district: [year 1 ... 4]}}
    import_run: list[dict]            # the live imports (sources)
    loaded_at: float

    @property
    def roster(self) -> pd.DataFrame:
        return self.rosters[self.horizon.base]


def plan_key(intake: dict[str, dict[str, list[int]]] | None) -> str:
    return hashlib.sha1(json.dumps(intake or {}, sort_keys=True).encode()).hexdigest()


def intake_frames(intake: dict[str, dict[str, list[int]]], horizon: P.Horizon) -> dict[str, pd.DataFrame]:
    """{"N1": {district: [year 1, ...]}} -> {"N1": district x year DataFrame} for P.project."""
    return {g: pd.DataFrame({d: v for d, v in t.items()}, index=horizon.future).T for g, t in intake.items() if t}


def _source(run, name: str | None) -> dict:
    return {"kind": run.kind, "year": run.academic_year, "file": run.file_name or run.endpoint,
            "publishedAt": run.published_at.isoformat() if run.published_at else None, "publishedBy": name}


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
            live = R.live_imports(session)
            school = {run.academic_year: run for run, _ in live if run.kind == "school_data"}
            if not school:
                raise RuntimeError("No published school data yet: run python -m etl.load_version2, "
                                   "or upload it in the admin portal.")
            years = sorted(school)
            horizon = P.Horizon(years[-1])
            rosters = {y: R.read_roster(session, y) for y in years}
            pop = R.read_catchment_population(session)
            catchment = R.read_catchment(session, rosters[horizon.base], horizon, pop)
            nisr = R.read_nisr(session)
            shapes = R.boundaries(session)
            sources = [_source(run, name) for run, name in live]
        base = P.base_schools(rosters[horizon.base])
        population = P.default_intake(catchment, base.info, nisr)
        measured = set() if nisr.empty else {int(c) for c in nisr.columns}
        estimated = {"N1": [y for y in P.estimated_years(pop, horizon) if y not in measured]}
        config = D.projection_config(base, catchment, horizon, population, estimated)
        payloads = {"projection-config": Payload.of(config),
                    **{f"boundaries/{k}": Payload.of(v) for k, v in shapes.items()}}
        for y, roster in rosters.items():
            run = school[y]
            when = run.published_at or run.finished_at
            data = D.current(roster, source=run.file_name or run.endpoint or "database",
                             built=when.date().isoformat() if when else None)
            meta = {**data["meta"], "actualYears": years, "baseYear": horizon.base,
                    "projectionYears": horizon.future, "sources": sources}
            payloads.update({f"meta/{y}": Payload.of(meta), f"school-levels/{y}": Payload.of(data["school_levels"]),
                             f"grades/{y}": Payload.of(data["grades"]), f"combos/{y}": Payload.of(data["combos"])})
        snap = Snapshot(rosters, horizon, base, catchment, payloads, config["population"], sources, time.time())
        default = self._compute(snap, None)
        with self._lock:
            self._snap = snap
            self._runs.clear()
            self._runs[plan_key(None)] = default
        return {"import_run": sources, "class_groups": len(snap.roster), "years": years,
                "seconds": round(time.time() - t0, 1)}

    def payload(self, name: str) -> Payload:
        return self.snapshot.payloads[name]

    def year_payload(self, name: str, year: int | None) -> Payload:
        """A per-year payload (meta, school-levels, grades, combos) of a published school year (default: the base)."""
        snap = self.snapshot
        y = year or snap.horizon.base
        if y not in snap.rosters:
            raise KeyError(f"No data for {y}: the school years are {', '.join(str(k) for k in snap.rosters)}.")
        return snap.payloads[f"{name}/{y}"]

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
        _, schools, grades, combos = P.project(snap.roster, intake_frames(intake or snap.default_intake, snap.horizon),
                                               catchment=snap.catchment, base=snap.base, horizon=snap.horizon)
        return Payload.of(D.encode_projection(schools, grades, combos, snap.horizon))


store = Store()
