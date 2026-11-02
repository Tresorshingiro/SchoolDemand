"""
Teachers per school and level (MINEDUC) — pupils per teacher on the dashboard.

The file has one row per public / government-aided school: school_code, its place (province ... village),
school_status, the teachers of each level (blank = none), total_teaching_staff (the sum of the levels) and
total_administrative_staff. Private schools are not in it.

Which schools count:
* A school not in the file has no teacher data: it is left out of every teacher figure (never 0 teachers).
* A school in the file with students in a level whose teacher column is blank: no teacher data for that level, and a
  data-quality issue ("Students but no teachers recorded").
* Teachers recorded for a level the school has no students in: kept, and an issue ("Teachers but no students").
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import analysis as A

TEACHERS_XLSX = A.DATA_DIR / "Teachers.xlsx"
LEVEL_COLUMNS = {  # file column -> level label
    "total_preprimary_teachers": "Pre-Primary",
    "total_primary_teachers": "Primary",
    "total_lower_secondary_teachers": "Lower Secondary",
    "total_upper_secondary_teachers": "Upper Secondary",
    "total_tvet_teachers": "TVET",
    "Prof_sec_teacher_total": "Professional Education",
}
STAFF_COLUMNS = ["school_status", "total_teaching_staff", "total_administrative_staff"]
NO_TEACHERS = "Students but no teachers recorded"
NO_STUDENTS = "Teachers but no students"


def to_long(df: pd.DataFrame) -> pd.DataFrame:
    """File rows (canonical column names) -> school_code, level, teachers for the level cells that are not blank."""
    cols = [c for c in LEVEL_COLUMNS if c in df]
    t = df.melt(id_vars="school_code", value_vars=cols, var_name="level", value_name="teachers").dropna(subset=["teachers"])
    t["level"] = t["level"].map(LEVEL_COLUMNS)
    order = {label: i for i, label in enumerate(A.LEVEL_ORDER)}
    t = t.astype({"school_code": "int64", "teachers": int})
    return t.sort_values(["school_code", "level"], key=lambda s: s.map(order) if s.name == "level" else s
                         ).reset_index(drop=True)[["school_code", "level", "teachers"]]


def load_teachers(path: Path = TEACHERS_XLSX) -> pd.DataFrame:
    """to_long of a teachers workbook (the development file by default)."""
    return to_long(pd.read_excel(path))


def per_level(roster: pd.DataFrame, teachers: pd.DataFrame | None) -> pd.Series:
    """Teachers of each school x level of the roster (A.school_table), NaN = no teacher data."""
    keys = pd.MultiIndex.from_frame(A.school_table(roster)[["school_code", "level"]])
    if teachers is None or teachers.empty:
        return pd.Series(float("nan"), index=keys, name="teachers")
    t = teachers.set_index(["school_code", "level"])["teachers"].astype(float)
    return t.reindex(keys).rename("teachers")


def teacher_issues(roster: pd.DataFrame, teachers: pd.DataFrame | None) -> pd.DataFrame:
    """Data-quality issues of the teachers against the roster: school_code, issue, detail."""
    cols = ["school_code", "issue", "detail"]
    if teachers is None or teachers.empty:
        return pd.DataFrame(columns=cols)
    students = A.school_table(roster).set_index(["school_code", "level"])["total_students"]
    t = teachers.set_index(["school_code", "level"])["teachers"]
    in_file = set(teachers["school_code"])
    recorded = t[t > 0].index  # a level with 0 teachers has none recorded
    missing = students[(students > 0) & ~students.index.isin(recorded)
                       & students.index.get_level_values(0).isin(in_file)]
    extra = t[(t > 0) & ~t.index.isin(students[students > 0].index) & t.index.get_level_values(0).isin(
        set(roster["school_code"]))]
    rows = [{"school_code": c, "issue": NO_TEACHERS, "detail": f"{lvl}: {int(n)} students, no teachers"}
            for (c, lvl), n in missing.items()]
    rows += [{"school_code": c, "issue": NO_STUDENTS, "detail": f"{lvl}: {int(n)} teachers, no students"}
             for (c, lvl), n in extra.items()]
    return pd.DataFrame(rows, columns=cols)
