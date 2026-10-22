"""
Planned new schools in the projection — "what if we build a school here?"
(docs/superpowers/specs/2026-10-20-new-school-planning-design.md).

A planned school is a point on the map with one level (or Pre-Primary and Primary together), a number of classrooms,
an opening year and a walking distance. It joins the projection as an extra school with no students in the base
year and its classrooms as rooms. From its opening year, every year, it takes the extra students of the crowded
schools of its level within walking distance (its ring) — students their rooms cannot seat — up to its own places.
Nothing else changes: the actual data never sees planned schools, and without any the projection is unchanged.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import analysis as A
from . import projection as P

LEVEL_KEYS = {key: label for key, label, _, _ in A.LEVELS}  # "NUR" -> "Pre-Primary", ...
LEVEL_LABELS = [label for label, _ in P.LEVELS]
# A standard school: 2 classrooms per projected grade (TVET without the L1-L2 short courses)
DEFAULT_CLASSROOMS = {label: 2 * len(grades) for label, grades in P.LEVELS}
DEFAULT_WALKING_KM = {label: 2.0 if label in ("Pre-Primary", "Primary") else 3.0 for label in LEVEL_LABELS}
# One level, or Pre-Primary and Primary together
ALLOWED_LEVEL_SETS = [{label} for label in LEVEL_LABELS] + [{"Pre-Primary", "Primary"}]


@dataclass(frozen=True)
class PlannedSchool:
    name: str
    latitude: float
    longitude: float
    district: str
    sector: str
    classrooms: tuple[tuple[str, int], ...]  # (level label, rooms), in level order
    opening_year: int
    walking_km: float


def planned_code(i: int) -> int:
    """School code of the i-th planned school: negative, so it never clashes with a MINEDUC code."""
    return -(i + 1)


def with_planned(base: P.Base, planned: Sequence[PlannedSchool]) -> P.Base:
    """The base with one row per planned school added at the end: no students or class groups, its classrooms as
    rooms of its level(s)."""
    if not planned:
        return base
    k = len(planned)
    info = pd.DataFrame({
        "school_code": [planned_code(i) for i in range(k)],
        "school_name": [s.name for s in planned],
        "district": [s.district for s in planned],
        "sector": [s.sector for s in planned],
        "latitude": [float(s.latitude) for s in planned],
        "longitude": [float(s.longitude) for s in planned],
    })
    rooms = np.zeros((k, len(LEVEL_LABELS)), dtype=int)
    for i, s in enumerate(planned):
        for label, n in s.classrooms:
            rooms[i, LEVEL_LABELS.index(label)] = n

    def grow(a: np.ndarray) -> np.ndarray:
        return np.concatenate([a, np.zeros((k, *a.shape[1:]), dtype=a.dtype)])

    return P.Base(
        info=pd.concat([base.info, info], ignore_index=True),
        rooms=np.vstack([base.rooms, rooms]),
        students=grow(base.students),
        groups=grow(base.groups),
        combos=base.combos,
        combo_students={k_: grow(v) for k_, v in base.combo_students.items()},
        combo_groups={k_: grow(v) for k_, v in base.combo_groups.items()},
    )


# ---------------------------------------------------------------- the ring: schools within walking distance
def distance_km(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Great-circle distance in km from one point to many (inf where a coordinate is missing)."""
    p1, p2 = math.radians(lat), np.radians(lats)
    a = (np.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * np.cos(p2) * np.sin(np.radians(lons - lon) / 2) ** 2)
    d = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return np.where(np.isfinite(d), d, np.inf)


def _coords(base: P.Base) -> tuple[np.ndarray, np.ndarray]:
    return (base.info["latitude"].to_numpy(dtype=float), base.info["longitude"].to_numpy(dtype=float))


def _ring(base: P.Base, row: int, li: int, km: float, eligible: np.ndarray) -> np.ndarray:
    """Rows of the schools offering level `li` within `km` of school `row` (among `eligible`)."""
    lats, lons = _coords(base)
    d = distance_km(lats[row], lons[row], lats, lons)
    ok = eligible & (base.rooms[:, li] > 0) & (d <= km)
    ok[row] = False
    return np.nonzero(ok)[0]


def rings(base: P.Base, planned: Sequence[PlannedSchool]) -> list[dict[str, list[int]]]:
    """For each planned school (base = with_planned(...)): level -> codes of the existing schools in its ring."""
    n = len(base.info) - len(planned)
    existing = np.arange(len(base.info)) < n
    codes = base.info["school_code"].to_numpy()
    return [{label: [int(c) for c in codes[_ring(base, n + i, LEVEL_LABELS.index(label), s.walking_km, existing)]]
             for label, _ in s.classrooms} for i, s in enumerate(planned)]


# ---------------------------------------------------------------- taking the extra students
def _level_rooms(base: P.Base, st: P.YearState, rows: np.ndarray, li: int) -> tuple[np.ndarray, np.ndarray]:
    """(rooms assigned to each grade, rooms required by each grade) of `rows` for level `li` this year — the room
    sharing P.project does."""
    label, grades = P.LEVELS[li]
    cols = [P.GRADES.index(g) for g in grades]
    cap = P.CAPACITY[label]
    s, g, rooms = st.students[rows][:, cols], st.groups[rows][:, cols], base.rooms[rows, li]
    if label in A.FULL_DAY:
        if label in st.c_students:
            cs, cg = st.c_students[label][rows], st.c_groups[label][rows]
            need = np.maximum(cg, np.ceil(cs / cap).astype(int)).sum(axis=2)
        else:
            need = np.maximum(g, np.ceil(s / cap).astype(int))
        return P.share_by_need(rooms, need), need
    need = np.ceil(s / cap).astype(int)
    return P.share_rooms(rooms, g, need), need


def _need(students: int, groups: int, cap: int) -> int:
    """Rooms a combination (or a full-day grade without combinations) needs: MAX(class groups, CEILING(students / cap))."""
    return max(int(groups), math.ceil(students / cap))


def _move_groups(cs: np.ndarray, cg: np.ndarray, rs: np.ndarray, rg: np.ndarray, assigned: int, own: int,
                 cap: int) -> tuple[int, int]:
    """Full-day levels: move class groups one at a time from a giver (students `cs`, groups `cg` per combination) to
    the new school (`rs`, `rg`), each in its own combination and of at most `cap` students, while the giver needs more
    rooms than it was assigned and the new school has a free room. Arrays are changed in place; returns (students
    moved, giver groups removed)."""
    moved = removed = 0
    giver_need = sum(_need(s, g, cap) for s, g in zip(cs, cg))
    own_need = sum(_need(s, g, cap) for s, g in zip(rs, rg))
    while giver_need > assigned and own_need < own:
        done = False
        for c in sorted(np.nonzero(cs > 0)[0], key=lambda c: -_need(cs[c], cg[c], cap)):  # largest need first
            t = min(cap, math.ceil(cs[c] / cg[c]) if cg[c] else int(cs[c]))
            left = int(cs[c]) - t
            groups_left = int(cg[c]) - 1 if cg[c] > 1 or left == 0 else int(cg[c])
            before = _need(cs[c], cg[c], cap)
            if _need(left, groups_left, cap) >= before:
                continue  # moving it would not free a room
            removed += int(cg[c]) - max(groups_left, 0)
            cs[c], cg[c] = left, max(groups_left, 0)
            rs[c] += t
            rg[c] += 1
            moved += t
            giver_need += _need(cs[c], cg[c], cap) - before
            own_need += 1
            done = True
            break
        if not done:
            break
    return moved, removed


def _take(base: P.Base, st: P.YearState, row: int, li: int, rooms_new: int, ring: np.ndarray) -> None:
    """The planned school `row` takes the extra students of the `ring` schools in every grade of level `li`."""
    if not len(ring):
        return
    label, grades = P.LEVELS[li]
    cols = [P.GRADES.index(g) for g in grades]
    cap = P.CAPACITY[label]
    full_day = label in A.FULL_DAY
    assigned, need = _level_rooms(base, st, ring, li)
    # Only the crowded schools give (classroom gap of the level < 0), the largest shortage first
    if full_day:
        required = need.sum(axis=1)
    else:
        required = np.ceil(st.students[ring][:, cols].sum(axis=1) / cap).astype(int)
    gap = base.rooms[ring, li] - required
    order = [j for j in np.argsort(gap, kind="stable") if gap[j] < 0]
    own = P._largest_remainder(np.array([rooms_new]), np.ones((1, len(cols))))[0]  # even split, ties to lower grades
    s, g = st.students, st.groups
    combos = label in st.c_students
    for k, col in enumerate(cols):
        for j in order:
            r = ring[j]
            if s[r, col] <= 0:
                continue
            if not full_day:
                size = s[r, col] / g[r, col] if g[r, col] else cap
                take = int(min(max(0, s[r, col] - assigned[j, k] * cap), max(0, own[k] * cap - s[row, col])))
                if take <= 0:
                    continue
                s[r, col] -= take
                g[r, col] = math.ceil(s[r, col] / size) if s[r, col] else 0
                s[row, col] += take
                g[row, col] = math.ceil(s[row, col] / cap)
                continue
            # Full day: class groups move one by one, each keeping its combination (views into the combination arrays;
            # a level without combinations is one combination)
            if combos:
                cs, cg = st.c_students[label][r, k], st.c_groups[label][r, k]
                rs, rg = st.c_students[label][row, k], st.c_groups[label][row, k]
            else:
                cs, cg = s[r, col:col + 1], g[r, col:col + 1]
                rs, rg = s[row, col:col + 1], g[row, col:col + 1]
            groups_before = int(rg.sum())
            moved, removed = _move_groups(cs, cg, rs, rg, int(assigned[j, k]), int(own[k]), cap)
            if combos and moved:  # keep the grade totals in step with the combinations
                s[r, col] -= moved
                g[r, col] -= removed
                s[row, col] += moved
                g[row, col] += int(rg.sum()) - groups_before


def transfer_hook(base: P.Base, planned: Sequence[PlannedSchool]) -> Callable[[P.YearState], None]:
    """The P.project hook that lets the planned schools (rows at the end of `base`) take their students each year:
    in order of opening year (then as listed); a ring includes a planned school handled before it."""
    n = len(base.info) - len(planned)
    sequence = sorted(range(len(planned)), key=lambda i: (planned[i].opening_year, i))

    def hook(st: P.YearState) -> None:
        eligible = np.zeros(len(base.info), dtype=bool)
        eligible[:n] = True
        for i in sequence:
            s = planned[i]
            if st.year < s.opening_year:
                continue
            row = n + i
            for label, rooms_new in s.classrooms:
                li = LEVEL_LABELS.index(label)
                _take(base, st, row, li, rooms_new, _ring(base, row, li, s.walking_km, eligible))
            eligible[row] = True  # open: in the rings of the planned schools handled after it

    return hook


def summary(before: pd.DataFrame, after: pd.DataFrame, info: pd.DataFrame, planned: Sequence[PlannedSchool],
            horizon: P.Horizon) -> dict:
    """What a plan changes (school x level x year frames of project() without and with it; `info` with the planned
    schools): per level of the planned schools, for Rwanda and each planned school's district, per projected year —
    classrooms short and schools in deficit, [before, after]."""
    district = info.set_index("school_code")["district"]
    levels = {label for s in planned for label, _ in s.classrooms}
    areas = ["Rwanda", *sorted({s.district for s in planned})]

    def figures(frame: pd.DataFrame, label: str, area: str, year: int) -> tuple[int, int]:
        f = frame[(frame["level"] == label) & (frame["year"] == year)]
        if area != "Rwanda":
            f = f[f["school_code"].map(district) == area]
        gap = f["gap"]
        return int(-gap[gap < 0].sum()), int((gap < 0).sum())

    out: dict[str, dict] = {}
    for label in [lv for lv in LEVEL_LABELS if lv in levels]:
        out[label] = {}
        for area in areas:
            out[label][area] = {}
            for y in horizon.future:
                (sb, db), (sa, da) = figures(before, label, area, y), figures(after, label, area, y)
                out[label][area][str(y)] = {"short": [sb, sa], "deficit_schools": [db, da]}
    return {"base_year": horizon.base, "levels": out}


def project(roster: pd.DataFrame, intake: dict[str, pd.DataFrame] | None = None,
            planned: Sequence[PlannedSchool] = (), *, catchment: pd.DataFrame | None = None,
            base: P.Base | None = None, horizon: P.Horizon = P.DEFAULT_HORIZON,
            ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """P.project with the planned schools included (P.project itself when there are none)."""
    if not planned:
        return P.project(roster, intake, catchment=catchment, base=base, horizon=horizon)
    b = with_planned(base if base is not None else P.base_schools(roster), planned)
    info, *frames = P.project(roster, intake, catchment=catchment, base=b, horizon=horizon,
                              after_intake=transfer_hook(b, planned))
    # A planned school is not in the figures before it opens (nor in the base year)
    opening = pd.Series({planned_code(i): s.opening_year for i, s in enumerate(planned)})
    keep = [f[~(f["year"] < f["school_code"].map(opening).fillna(-1))].reset_index(drop=True) for f in frames]
    return info, *keep
