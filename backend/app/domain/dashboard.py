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
from . import projection as P

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


def current(roster: pd.DataFrame, *, source: str, built: str | None = None) -> dict:
    """The 2026 dataset: {"school_levels", "grades", "meta", "combos"}."""
    s = A.school_table(roster)
    g = A.grade_table(roster)
    dq = A.data_quality(roster)

    school_levels = []
    for row in s.itertuples(index=False):
        lat, lon = _coords(row.latitude, row.longitude)
        school_levels.append({
            "c": int(row.school_code), "n": row.school_name, "d": row.district, "s": row.sector,
            "l": LEVEL_INDEX[row.level], "st": int(row.total_students), "g": int(row.total_classrooms),
            "ds": int(row.double_shift), "a": int(row.available), "r": int(row.required), "gap": int(row.gap),
            "y": lat, "x": lon,
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
        "levels": [{"key": k, "label": label, "grades": grades_, "capacity": cap, "fullDay": label in A.FULL_DAY}
                   for k, label, grades_, cap in A.LEVELS],
        "grades": A.GRADE_ORDER,
        "gradeColumns": ["school", "grade", "students", "classGroups", "doubleShift", "available", "required", "gap"],
        "roster": {"rows": len(roster), "schools": int(roster["school_code"].nunique()),
                   "students": int(roster[A.STUDENTS].sum())},
        "issues": {k: int(v) for k, v in dq["issue"].value_counts().items()},
        "schoolIssues": school_issues,
        "unmapped": sum(1 for r in {(x["c"], x["y"]) for x in school_levels} if r[1] is None),
    }
    return {"school_levels": school_levels, "grades": grades, "meta": meta, "combos": combos_2026(roster)}


def projection_config(base: P.Base, catchment: pd.DataFrame, horizon: P.Horizon = P.DEFAULT_HORIZON,
                      population: dict[str, pd.DataFrame] | None = None,
                      estimated: dict[str, list[int]] | None = None) -> dict:
    """What the dashboard needs to show and edit the projection (the calculation itself runs on the server).
    `population` = the default intake plan (P.default_intake), `estimated` = its years not measured."""
    population = population if population is not None else P.default_intake(catchment, base.info)
    return {
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
