"""
Classroom sufficiency analysis — shared data layer.

Loads the classroom roster, applies the business rules from
Data_Transformation_Brief.docx and returns the aggregated tables used by the
Excel workbook, the dashboard and the written report.

Business rules
--------------
* One source row = one class group (e.g. P1A). Several class groups can share a
  physical room, identified by (school_code, test_code).

Source: Version 2.xlsx — the 2026 roster restricted to the 4,837 schools located
inside Rwanda, with `test_code` as the cleaned room ID. It equals classroom_id
except that a room recorded with 3+ class groups (a data-entry error — a room
holds at most a morning and an afternoon session) is split into one room per
group. The original classroom_id is kept for reference.
* Total Classrooms            = number of class groups (rows)
* Classrooms in Double Shift  = class groups - distinct physical rooms
                                (one extra session per extra group in a room)
* Classrooms Available        = Total - Double Shift  (= distinct physical rooms)
* Required Classrooms         = CEILING(Total Students / capacity)
* Gap                         = Available - Required  (negative = deficit)

  Example agreed with the client: P1 with 6 rooms, 3 of them used by two
  groups -> 9 class groups, 3 double shift, 6 available.

* Full-day levels (Lower and Upper Secondary, TVET, Professional Education) have no double shift:
  every class group needs its own room, and different combinations never share.
      Required = SUM over grade x combination of MAX(class groups, CEILING(students / capacity))
  Rooms are counted as recorded, so a class group sharing a room ID with another
  group has no room of its own: it shows in Double Shift (read "class groups
  without a room" for these levels) and in the gap through Required.

* Grade level counts rooms within the grade. School level counts rooms across
  all grades of the level, so a room shared by two grades counts once there —
  school totals for Double Shift / Available can therefore differ from the sum
  of the grade rows.
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]  # repository root (backend/app/domain/analysis.py)
# Source files (roster, catchments, boundaries): data-sources/ in the repository, /data in the API container
DATA_DIR = Path(os.environ.get("SCHOOL_DATA_DIR", ROOT / "data-sources"))
SOURCE_XLSX = DATA_DIR / "Version 2.xlsx"
CACHE = Path(os.environ.get("SCHOOL_CACHE_DIR", ROOT / "output" / ".cache")) / f"{SOURCE_XLSX.stem}.pkl"

STUDENTS = "Number of students"
ROOM_ID = "test_code"  # cleaned physical room ID (see module docstring)

# Level definitions, in display order. Capacity defaults to the brief's 45.
LEVELS = [
    # key,      label,              grades,                          capacity
    ("NUR", "Pre-Primary",      ["N1", "N2", "N3"],                   45),
    ("PRI", "Primary",          ["P1", "P2", "P3", "P4", "P5", "P6"], 45),
    ("LSE", "Lower Secondary",  ["S1", "S2", "S3"],                   45),
    ("USE", "Upper Secondary",  ["S4", "S5", "S6"],                   45),
    ("TVE", "TVET",             ["L1", "L2", "L3", "L4", "L5"],       45),
    ("TTC", "Professional Education", ["Y1", "Y2", "Y3"],             45),
]
GRADE_TO_LEVEL = {g: label for _, label, grades, _ in LEVELS for g in grades}
LEVEL_ORDER = [label for _, label, _, _ in LEVELS]
GRADE_ORDER = [g for _, _, grades, _ in LEVELS for g in grades]
CAPACITY = {label: cap for _, label, _, cap in LEVELS}
# Levels that study full day: no double shift, every class group needs its own room (see module docstring)
FULL_DAY = ["Lower Secondary", "Upper Secondary", "TVET", "Professional Education"]

# Rwanda bounding box (with a small margin) for coordinate sanity checks.
RW_LAT = (-2.9, -1.0)
RW_LON = (28.8, 31.0)

LARGE_GROUP = 90  # students in one class group considered suspicious
UNKNOWN = "Unknown"  # label for schools with no district / sector

# Rwanda's districts by province (the dashboard's province charts and the database's provinces table)
PROVINCES = {
    "City of Kigali": ["Gasabo", "Kicukiro", "Nyarugenge"],
    "Eastern Province": ["Bugesera", "Gatsibo", "Kayonza", "Kirehe", "Ngoma", "Nyagatare", "Rwamagana"],
    "Northern Province": ["Burera", "Gakenke", "Gicumbi", "Musanze", "Rulindo"],
    "Southern Province": ["Gisagara", "Huye", "Kamonyi", "Muhanga", "Nyamagabe", "Nyanza", "Nyaruguru", "Ruhango"],
    "Western Province": ["Karongi", "Ngororero", "Nyabihu", "Nyamasheke", "Rubavu", "Rusizi", "Rutsiro"],
}


def _fix_mojibake(text):
    """Repair UTF-8 text that was decoded as Windows-1252 (e.g. 'CÃ‚LINS' -> 'CÂLINS')."""
    if not isinstance(text, str) or not re.search("[ÃÂâ]", text):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def load_roster(refresh: bool = False) -> pd.DataFrame:
    """Read the source workbook (cached as a pickle — the xlsx takes ~1 min) and prepare it (prepare_roster)."""
    if CACHE.exists() and not refresh and CACHE.stat().st_mtime > SOURCE_XLSX.stat().st_mtime:
        df = pd.read_pickle(CACHE)
    else:
        df = pd.read_excel(SOURCE_XLSX)
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            df.to_pickle(CACHE)
        except OSError:
            pass  # read-only location (e.g. the API container): no cache
    return prepare_roster(df)


def prepare_roster(df: pd.DataFrame) -> pd.DataFrame:
    """Roster rows (the Version 2.xlsx columns, from the file or the database) ready for the analysis:
    repaired text, upper-case grades, level and room key."""
    df = df.copy()
    for col in ("school_name", "class_group", "classroom_name"):
        df[col] = df[col].map(_fix_mojibake)
    df["grade"] = df["grade"].str.strip().str.upper()
    df["level"] = df["grade"].map(GRADE_TO_LEVEL)
    df["room_key"] = df["school_code"].astype(str) + "|" + df[ROOM_ID].astype(str)
    return df


def _school_info(df: pd.DataFrame) -> pd.DataFrame:
    """One row per school: name, district, sector, coordinates (first non-null)."""
    info = (
        df.groupby("school_code")
        .agg(
            school_name=("school_name", "first"),
            district=("district", "first"),
            sector=("sector", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
        )
        .reset_index()
    )
    info[["district", "sector"]] = info[["district", "sector"]].fillna(UNKNOWN)
    return info


def _aggregate(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    out = (
        df.groupby(keys)
        .agg(
            total_students=(STUDENTS, "sum"),
            total_classrooms=("room_key", "size"),
            physical_rooms=("room_key", "nunique"),
        )
        .reset_index()
    )
    out["double_shift"] = out["total_classrooms"] - out["physical_rooms"]
    out["available"] = out["physical_rooms"]
    out["capacity"] = out["level"].map(CAPACITY)
    out["required"] = [math.ceil(s / c) for s, c in zip(out["total_students"], out["capacity"])]
    need = room_need(df[df["level"].isin(FULL_DAY)], keys)
    out = out.merge(need, on=keys, how="left")
    out["required"] = out["need"].where(out["level"].isin(FULL_DAY), out["required"]).astype(int)
    out["gap"] = out["available"] - out["required"]
    return out.drop(columns=["physical_rooms", "need"])


def room_need(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Rooms needed by full-day levels, per `keys` (column "need"): SUM over grade x combination of
    MAX(class groups, CEILING(students / capacity))."""
    by = list(dict.fromkeys([*keys, "grade", "combination"]))
    t = df.groupby(by).agg(st=(STUDENTS, "sum"), g=("room_key", "size")).reset_index()
    t["need"] = [max(g, math.ceil(s / CAPACITY[lvl])) for g, s, lvl in zip(t["g"], t["st"], t["level"])]
    return t.groupby(keys, as_index=False)["need"].sum()


def _sort(df: pd.DataFrame, with_grade: bool) -> pd.DataFrame:
    df = df.copy()
    df["_lvl"] = df["level"].map({l: i for i, l in enumerate(LEVEL_ORDER)})
    cols = ["district", "sector", "school_name", "school_code", "_lvl"]
    if with_grade:
        df["_grd"] = df["grade"].map({g: i for i, g in enumerate(GRADE_ORDER)})
        cols.append("_grd")
    return df.sort_values(cols, na_position="last").drop(columns=[c for c in ("_lvl", "_grd") if c in df])


def grade_table(df: pd.DataFrame) -> pd.DataFrame:
    """Section 3a — one row per school x grade."""
    t = _aggregate(df, ["school_code", "level", "grade"])
    t = t.merge(_school_info(df), on="school_code", how="left")
    return _sort(t, with_grade=True).reset_index(drop=True)


def school_table(df: pd.DataFrame) -> pd.DataFrame:
    """Section 3b — one row per school x level (grades rolled up)."""
    t = _aggregate(df, ["school_code", "level"])
    t = t.merge(_school_info(df), on="school_code", how="left")
    return _sort(t, with_grade=False).reset_index(drop=True)


def data_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Row-level list of issues found in the source roster."""
    issues: list[pd.DataFrame] = []
    base = ["school_code", "school_name", "district", "grade", "class_group", "classroom_id", "classroom_name", STUDENTS]

    def add(mask: pd.Series, issue: str, detail) -> None:
        sub = df.loc[mask, base].copy()
        if sub.empty:
            return
        sub.insert(0, "issue", issue)
        sub["detail"] = detail(sub) if callable(detail) else detail
        issues.append(sub)

    # Class group label points at a different grade than the grade column.
    cg = df["class_group"].fillna("").str.upper().str.replace(" ", "")
    label_grade = cg.str.extract(r"^([NPSLY])(\d)")[0] + cg.str.extract(r"^([NPSLY])(\d)")[1]
    mismatch = label_grade.notna() & (label_grade != df["grade"])
    add(mismatch, "Grade / class group mismatch",
        lambda s: "Grade column says " + s["grade"] + ", class group label suggests " + label_grade[s.index])

    add(df[STUDENTS] > LARGE_GROUP, f"Class group over {LARGE_GROUP} students",
        lambda s: s[STUDENTS].astype(str) + " students in one group")
    add(df[STUDENTS] <= 2, "Class group of 1-2 students",
        lambda s: s[STUDENTS].astype(str) + " student(s) in one group")

    dup = df.duplicated(["school_code", "grade", "class_group"], keep=False) & df["class_group"].notna()
    add(dup, "Repeated class group name", "Same school, grade and class group appears more than once")

    add(df["class_group"].isna(), "Missing class group", "class_group is empty")

    groups_per_room = df.groupby("room_key")["room_key"].transform("size")
    add(groups_per_room >= 3, "Room shared by 3+ class groups",
        lambda s: groups_per_room[s.index].astype(str) + " class groups use this room")

    grades_per_room = df.groupby("room_key")["grade"].transform("nunique")
    levels_per_room = df.groupby("room_key")["level"].transform("nunique")
    add((grades_per_room > 1) & (levels_per_room == 1), "Room shared across grades",
        "Room used by more than one grade of the same level (counted once at school level)")
    add(levels_per_room > 1, "Room shared across levels",
        "Room used by more than one school level (counted as available in each level)")

    schools_per_id = df.groupby("classroom_id")["school_code"].transform("nunique")
    add(schools_per_id > 1, "Classroom ID used by several schools",
        "Same classroom_id appears under different school codes")

    no_xy = df["latitude"].isna() | df["longitude"].isna()
    out_xy = ~no_xy & ~(df["latitude"].between(*RW_LAT) & df["longitude"].between(*RW_LON))
    first_row = ~df.duplicated("school_code")
    add(no_xy & first_row, "Missing coordinates", "School cannot be placed on the map")
    add(out_xy & first_row, "Coordinates outside Rwanda",
        lambda s: "lat " + df.loc[s.index, "latitude"].astype(str) + ", lon " + df.loc[s.index, "longitude"].astype(str))
    add((df["district"].isna()) & first_row, "Missing district / sector", "district and sector are empty")

    out = pd.concat(issues, ignore_index=True) if issues else pd.DataFrame(columns=["issue", *base, "detail"])
    return out


if __name__ == "__main__":
    roster = load_roster()
    g, s, dq = grade_table(roster), school_table(roster), data_quality(roster)
    print("grade rows", len(g), "school-level rows", len(s))
    print(s.groupby("level", sort=False)[["total_students", "total_classrooms", "double_shift", "available", "required", "gap"]].sum())
    print(dq["issue"].value_counts())
