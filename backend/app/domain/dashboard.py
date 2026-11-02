"""
The dashboard's data, in the compact shapes the frontend reads (dashboard/src/data.ts, projection.ts):

  current(roster)          2026: one record per school x level, one row per school x grade, combinations, meta
  projection_config(...)   how the projection works: years, levels, grades, how new students enter, default plan
  encode_projection(...)   one projection run: every school x level, school x grade and combination row, all years
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import analysis as A
from . import new_schools as NS
from . import projection as P
from . import rates as RT
from . import teachers as T

LEVEL_INDEX = {label: i for i, label in enumerate(A.LEVEL_ORDER)}
GRADE_INDEX = {grade: i for i, grade in enumerate(A.GRADE_ORDER)}


def _coords(lat, lon):
    ok = lat == lat and lon == lon and A.RW_LAT[0] <= lat <= A.RW_LAT[1] and A.RW_LON[0] <= lon <= A.RW_LON[1]
    return (round(float(lat), 6), round(float(lon), 6)) if ok else (None, None)


def combos_2026(roster: pd.DataFrame) -> dict:
    """Students and class groups per school, grade and combination (levels with combinations, all grades)."""
    d = roster[roster["level"].isin(P.COMBO_LEVELS)]
    t = d.groupby(["school_code", "grade", "combination"]).agg(st=(A.STUDENTS, "sum"), g=("room_key", "size")).reset_index()
    names = sorted(t["combination"].unique())
    idx = {n: i for i, n in enumerate(names)}
    return {"names": names,
            # [school, grade index into meta.grades, combination index into names, students, class groups]
            "rows": [[int(r.school_code), GRADE_INDEX[r.grade], idx[r.combination], int(r.st), int(r.g)]
                     for r in t.itertuples(index=False)]}


def current(roster: pd.DataFrame, *, source: str, built: str | None = None, teachers: pd.DataFrame | None = None,
            teachers_year: int | None = None, capacity: int | None = None) -> dict:
    """A school year's dataset: {"school_levels", "grades", "meta", "combos"}. `teachers` (school_code, level,
    teachers; teachers.py) of `teachers_year` give each school x level its "t" (None = no teacher data). `capacity`:
    students per room for every level (None = each level's own)."""
    s = A.school_table(roster, capacity)
    g = A.grade_table(roster, capacity)
    dq = pd.concat([A.data_quality(roster), T.teacher_issues(roster, teachers)], ignore_index=True)
    staff = T.per_level(roster, teachers)

    school_levels = []
    for row in s.itertuples(index=False):
        lat, lon = _coords(row.latitude, row.longitude)
        t = staff.get((row.school_code, row.level))
        school_levels.append({
            "c": int(row.school_code), "n": row.school_name, "d": row.district, "s": row.sector,
            "l": LEVEL_INDEX[row.level], "st": int(row.total_students), "g": int(row.total_classrooms),
            "ds": int(row.double_shift), "a": int(row.available), "r": int(row.required), "gap": int(row.gap),
            "t": None if t is None or pd.isna(t) else int(t), "y": lat, "x": lon,
        })
    grades = [
        [int(r.school_code), GRADE_INDEX[r.grade], int(r.total_students), int(r.total_classrooms),
         int(r.double_shift), int(r.available), int(r.required), int(r.gap)]
        for r in g.itertuples(index=False)
    ]
    school_issues: dict[str, list] = {}
    for (code, issue), n in dq.groupby(["school_code", "issue"]).size().items():
        school_issues.setdefault(str(int(code)), []).append([issue, int(n)])
    meta = {
        "built": built or date.today().isoformat(),
        "source": source,
        "levels": [{"key": k, "label": label, "grades": grades_, "capacity": capacity or cap, "fullDay": label in A.FULL_DAY}
                   for k, label, grades_, cap in A.LEVELS],
        "grades": A.GRADE_ORDER,
        "gradeColumns": ["school", "grade", "students", "classGroups", "doubleShift", "available", "required", "gap"],
        "roster": {"rows": len(roster), "schools": int(roster["school_code"].nunique()),
                   "students": int(roster[A.STUDENTS].sum())},
        "issues": {k: int(v) for k, v in dq["issue"].value_counts().items()},
        "schoolIssues": school_issues,
        "unmapped": sum(1 for r in {(x["c"], x["y"]) for x in school_levels} if r[1] is None),
        # the school year of the teachers ("t"; None = no teachers file) and the schools with teacher data
        "teachers": {"year": teachers_year if teachers is not None else None,
                     "schools": len({x["c"] for x in school_levels if x["t"] is not None})},
    }
    return {"school_levels": school_levels, "grades": grades, "meta": meta, "combos": combos_2026(roster)}


def projection_config(base: P.Base, catchment: pd.DataFrame, horizon: P.Horizon = P.DEFAULT_HORIZON,
                      population: dict[str, pd.DataFrame] | None = None,
                      estimated: dict[str, list[int]] | None = None, rates: RT.FlowRates | None = None) -> dict:
    """What the dashboard needs to show and edit the projection (the calculation itself runs on the server).
    `population` = the default intake plan (P.default_intake), `estimated` = its years not measured, `rates` the
    repetition and dropout rates the projection uses."""
    population = population if population is not None else P.default_intake(catchment, base.info)
    rates = rates if rates is not None else RT.load_rates()
    return {
        # repetition and dropout per district (and Rwanda): [repetition, dropout] as shares
        "rates": {"schoolYear": rates.school_year,
                  "districts": {d: [float(r.repetition), float(r.dropout)] for d, r in rates.table.iterrows()}},
        "baseYear": horizon.base,
        "years": horizon.years,
        "levels": [{"level": LEVEL_INDEX[label], "grades": grades, "capacity": P.CAPACITY[label],
                    "fullDay": label in A.FULL_DAY}
                   for label, grades in P.LEVELS],
        "grades": P.GRADES,
        "gradeIndex": [GRADE_INDEX[g] for g in P.GRADES],
        "intakes": P.INTAKES,
        "feeds": P.FEEDS,
        "schoolFeeds": P.SCHOOL_FEEDS,
        "population": {g: {d: [int(v) for v in row] for d, row in t.iterrows()} for g, t in population.items()},
        "estimated": estimated if estimated is not None else P.ESTIMATED,
        # children aged 3 in each pre-primary school's catchment (filled as P.fill_catchment): [school, year 1, ... 4]
        "catchment": {"years": horizon.future,
                      "rows": [[int(code), *(int(v) for v in row)] for code, row in catchment.iterrows()]},
        "defaultLabel": P.DEFAULT_LABEL,
        # combinations of each level (empty = level without combinations), most students first
        "combos": [base.combos.get(label, []) for label, _ in P.LEVELS],
    }


def encode_projection(schools: pd.DataFrame, grades: pd.DataFrame, combos: pd.DataFrame,
                      horizon: P.Horizon = P.DEFAULT_HORIZON) -> dict:
    """One projection run, all years, as rows of numbers (names and coordinates come from the 2026 dataset)."""
    s = schools.assign(l=schools["level"].map(LEVEL_INDEX))
    g = grades.assign(k=grades["grade"].map(GRADE_INDEX))
    names = sorted(combos["combination"].unique())
    c = combos.assign(k=combos["grade"].map(GRADE_INDEX), ni=combos["combination"].map({n: i for i, n in enumerate(names)}))
    return {
        "years": horizon.years,
        # [year, school, level index, students, class groups, double shift / no room, rooms, required, gap]
        "schools": s[["year", "school_code", "l", "students", "class_groups", "double_shift", "rooms", "required", "gap"]]
        .to_numpy().tolist(),
        # [year, school, grade index into meta.grades, students, class groups, double shift, rooms assigned, required, gap]
        "grades": g[["year", "school_code", "k", "students", "class_groups", "double_shift", "rooms", "required", "gap"]]
        .to_numpy().tolist(),
        # [year, school, grade index, combination index into names, students, class groups]
        "combos": {"names": names,
                   "rows": c[["year", "school_code", "k", "ni", "students", "class_groups"]].to_numpy().tolist()},
    }


def encode_planned(planned, rings: list[dict[str, list[int]]], details: list[dict]) -> list[dict]:
    """The planned new schools of a run (codes -1, -2 ... in the rows): where they are, what they offer, the existing
    schools in each level's ring, and the walk: `area` (GeoJSON outline for the map, may be null), `unreachable` (per
    level, nearby schools with no route), `snap_km` and `on_main_network` of the point."""
    return [{"c": NS.planned_code(i), "n": s.name, "d": s.district, "s": s.sector, "y": s.latitude, "x": s.longitude,
             "levels": [LEVEL_INDEX[label] for label, _ in s.classrooms],
             "classrooms": [n for _, n in s.classrooms], "opening": s.opening_year, "km": s.walking_km,
             "ring": {str(LEVEL_INDEX[label]): codes for label, codes in ring.items()},
             "area": d["area"], "snap_km": round(d["snap_km"], 3), "on_main_network": d["on_main_network"],
             "unreachable": {str(LEVEL_INDEX[label]): n for label, n in d["unreachable"].items()}}
            for i, (s, ring, d) in enumerate(zip(planned, rings, details))]
