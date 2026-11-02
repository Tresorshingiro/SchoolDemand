"""
In-memory store behind the API: the 2026 data and the projection inputs are read from the database once (at startup
and on /api/admin/reload) and served from memory. Responses are kept as ready-made JSON bytes, plain and gzipped.
Projection runs are cached per intake plan (least recently used first out).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass

import pandas as pd

from ..config import settings
from ..db import SessionLocal
from ..domain import dashboard as D
from ..domain import new_schools as NS
from ..domain import projection as P
from ..domain import rates as RT
from ..domain import walking as WK
from . import repository as R

log = logging.getLogger("school_planning.store")


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
    rates: RT.FlowRates               # repetition and dropout (on unless a what-if run switches them off)
    payloads: dict[str, Payload]      # meta/<y>, school-levels/<y>, grades/<y>, combos/<y>, projection-config, boundaries/*
    default_intake: dict[str, dict[str, list[int]]]  # the default plan: {"N1": {district: [year 1 ... 4]}}
    import_run: list[dict]            # the live imports (sources)
    loaded_at: float
    year_inputs: dict[int, dict]      # D.current's keyword arguments of each year (a what-if students per classroom)
    network: WK.WalkingNetwork | None = None  # planned schools' walking distance; None = none published or file lost

    @property
    def roster(self) -> pd.DataFrame:
        return self.rosters[self.horizon.base]


@dataclass(frozen=True)
class Assumptions:
    """What a person is trying on the dashboard; nothing is saved. Students per classroom for every level, and whether
    repetition and dropout apply."""
    capacity: int = 46
    repetition: bool = True
    dropout: bool = True

    @property
    def is_default(self) -> bool:
        return self == Assumptions()


DEFAULTS = Assumptions()


def plan_key(intake: dict[str, dict[str, list[int]]] | None, planned: tuple[NS.PlannedSchool, ...] = (),
             assumptions: Assumptions = DEFAULTS) -> str:
    key = {"intake": intake or {}, "schools": [asdict(s) for s in planned]} if planned else intake or {}
    if not assumptions.is_default:
        key = {"plan": key, "assumptions": asdict(assumptions)}
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()


def intake_frames(intake: dict[str, dict[str, list[int]]], horizon: P.Horizon) -> dict[str, pd.DataFrame]:
    """{"N1": {district: [year 1, ...]}} -> {"N1": district x year DataFrame} for P.project."""
    return {g: pd.DataFrame({d: v for d, v in t.items()}, index=horizon.future).T for g, t in intake.items() if t}


def _read_network(run) -> WK.WalkingNetwork | None:
    """The live network's routing file; without it only planned schools stop working."""
    path = R.network_file(run)
    try:
        return WK.WalkingNetwork.load(path)
    except Exception as e:  # noqa: BLE001 — missing, cut short or damaged: never stops the rest of the dashboard
        log.warning("walking network of import %s could not be read (%s): planned schools are unavailable", run.id, e)
        return None


def _source(run, name: str | None) -> dict:
    return {"kind": run.kind, "year": run.academic_year, "file": run.file_name or run.endpoint,
            "publishedAt": run.published_at.isoformat() if run.published_at else None, "publishedBy": name}


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snap: Snapshot | None = None
        self._runs: OrderedDict[str, Payload] = OrderedDict()
        self._year_runs: OrderedDict[tuple[int, int], dict[str, Payload]] = OrderedDict()

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
            rates = R.read_rates(session)
            if rates is None:
                raise RuntimeError("No repetition and dropout rates published yet: run python -m etl.load_version2, "
                                   "or upload them in the admin portal.")
            # each school year shows the teachers of the newest teachers year not after it
            t_years = R.teacher_years(session)
            teachers = {y: (ty, R.read_teachers(session, ty)) if (ty := max([t for t in t_years if t <= y], default=None))
                        else (None, None) for y in years}
            shapes = R.boundaries(session)
            sources = [_source(run, name) for run, name in live]
            network_run = next((run for run, _ in live if run.kind == "walking_network"), None)
            network = _read_network(network_run) if network_run is not None else None
        base = P.base_schools(rosters[horizon.base])
        population = P.default_intake(catchment, base.info, nisr)
        measured = set() if nisr.empty else {int(c) for c in nisr.columns}
        estimated = {"N1": [y for y in P.estimated_years(pop, horizon) if y not in measured]}
        config = {**D.projection_config(base, catchment, horizon, population, estimated, rates),
                  "walkingNetwork": network is not None}
        payloads = {"projection-config": Payload.of(config),
                    **{f"boundaries/{k}": Payload.of(v) for k, v in shapes.items()}}
        year_inputs = {}
        for y, roster in rosters.items():
            run = school[y]
            when = run.published_at or run.finished_at
            t_year, t = teachers[y]
            year_inputs[y] = {"source": run.file_name or run.endpoint or "database",
                              "built": when.date().isoformat() if when else None, "teachers": t, "teachers_year": t_year}
            data = D.current(roster, **year_inputs[y])
            meta = {**data["meta"], "actualYears": years, "baseYear": horizon.base,
                    "projectionYears": horizon.future, "sources": sources}
            payloads.update({f"meta/{y}": Payload.of(meta), f"school-levels/{y}": Payload.of(data["school_levels"]),
                             f"grades/{y}": Payload.of(data["grades"]), f"combos/{y}": Payload.of(data["combos"])})
        snap = Snapshot(rosters, horizon, base, catchment, rates, payloads, config["population"], sources, time.time(),
                        year_inputs, network)
        default = self._compute(snap, None)
        with self._lock:
            self._snap = snap
            self._runs.clear()
            self._year_runs.clear()
            self._runs[plan_key(None)] = default
        return {"import_run": sources, "class_groups": len(snap.roster), "years": years,
                "seconds": round(time.time() - t0, 1)}

    def payload(self, name: str) -> Payload:
        return self.snapshot.payloads[name]

    def year_payload(self, name: str, year: int | None, capacity: int | None = None) -> Payload:
        """A per-year payload (meta, school-levels, grades, combos) of a published school year (default: the base). With
        `capacity` (school-levels and grades): that year at this many students per classroom, calculated once and kept."""
        snap = self.snapshot
        y = year or snap.horizon.base
        if y not in snap.rosters:
            raise KeyError(f"No data for {y}: the school years are {', '.join(str(k) for k in snap.rosters)}.")
        if capacity is None or capacity == DEFAULTS.capacity:
            return snap.payloads[f"{name}/{y}"]
        key = (y, capacity)
        with self._lock:
            if key in self._year_runs:
                self._year_runs.move_to_end(key)
                return self._year_runs[key][name]
        data = D.current(snap.rosters[y], **snap.year_inputs[y], capacity=capacity)
        result = {"school-levels": Payload.of(data["school_levels"]), "grades": Payload.of(data["grades"])}
        with self._lock:
            if self._snap is snap:  # not reloaded meanwhile
                self._year_runs[key] = result
                while len(self._year_runs) > max(settings.projection_cache_size, 1):
                    self._year_runs.popitem(last=False)
        return result[name]

    def projection(self, intake: dict[str, dict[str, list[int]]] | None,
                   planned: tuple[NS.PlannedSchool, ...] = (), assumptions: Assumptions = DEFAULTS) -> Payload:
        """The projection for an intake plan (None = the default catchment plan), planned new schools and what-if
        assumptions, cached."""
        key = plan_key(intake, planned, assumptions)
        with self._lock:
            if key in self._runs:
                self._runs.move_to_end(key)
                return self._runs[key]
            snap = self.snapshot
        result = self._compute(snap, intake, planned, assumptions)
        with self._lock:
            if self._snap is snap:  # not reloaded meanwhile
                self._runs[key] = result
                while len(self._runs) > max(settings.projection_cache_size, 1):
                    self._runs.popitem(last=False)
        return result

    def frames(self, intake: dict[str, dict[str, list[int]]] | None,
               planned: tuple[NS.PlannedSchool, ...] = ()) -> tuple[pd.DataFrame, ...]:
        """One projection run as data frames (info, schools, grades, combos), not cached, with the default assumptions
        (a saved plan's summary must not depend on what someone is trying on screen)."""
        return self._frames(self.snapshot, intake, planned)

    @staticmethod
    def _frames(snap: Snapshot, intake: dict[str, dict[str, list[int]]] | None,
                planned: tuple[NS.PlannedSchool, ...] = (), assumptions: Assumptions = DEFAULTS,
                reaches=None) -> tuple[pd.DataFrame, ...]:
        rates = RT.switched(snap.rates, assumptions.repetition, assumptions.dropout)
        capacity = None if assumptions.capacity == DEFAULTS.capacity else assumptions.capacity
        return NS.project(snap.roster, intake_frames(intake or snap.default_intake, snap.horizon), planned,
                          catchment=snap.catchment, base=snap.base, horizon=snap.horizon, rates=rates, capacity=capacity,
                          network=snap.network, reaches=reaches)

    @staticmethod
    def _outline(school: NS.PlannedSchool, reach: WK.Reach) -> dict | None:
        """The map's outline of the walking area; a failure here never fails the run."""
        try:
            return WK.outline(school.latitude, school.longitude, reach.reached_lat, reach.reached_lon)
        except Exception as e:  # noqa: BLE001
            log.warning("walking area outline failed: %s", e)
            return None

    @classmethod
    def _compute(cls, snap: Snapshot, intake: dict[str, dict[str, list[int]]] | None,
                 planned: tuple[NS.PlannedSchool, ...] = (), assumptions: Assumptions = DEFAULTS) -> Payload:
        rings, details, reaches = [], [], None
        if planned:
            if snap.network is None:
                raise NS.NoWalkingNetwork("No walking network published yet.")
            b = NS.with_planned(snap.base, planned)
            reaches = NS.reach_table(b, planned, snap.network)
            rings = NS.rings(b, planned, snap.network, reaches)
            details = [{"area": cls._outline(s, r), "unreachable": u, "snap_km": r.snap_km,
                        "on_main_network": r.on_main_network}
                       for s, r, u in zip(planned, reaches, NS.unreachable(b, planned, reaches))]
        _, schools, grades, combos = cls._frames(snap, intake, planned, assumptions, reaches)
        return Payload.of({**D.encode_projection(schools, grades, combos, snap.horizon),
                           "planned": D.encode_planned(planned, rings, details)})


store = Store()
