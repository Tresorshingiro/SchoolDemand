"""
Classroom projection 2026-2030, all levels — shared data layer.

Ages the 2026 roster forward one grade per year, brings in new students at the
entry grade of each level, and shares each school's existing classrooms between
the grades of a level every year — the same measures as the 2026 analysis
(students, class groups, double shift, available, required, gap) for every
school x level x grade x year.

The dashboard runs the same algorithm in the browser (dashboard/src/projection.ts)
so planners can type their own intake; keep the two in step.

Levels projected
----------------
Pre-Primary N1-N3, Primary P1-P6, Lower Secondary S1-S3, Upper Secondary S4-S6,
TVET L3-L5 and TTC Y1-Y3. TVET L1-L2 (short courses) are left out: their class
groups, students and rooms are not part of the projection.

New students (year y = 2027 ... 2030)
-------------------------------------
* N1 = the children aged 3 in y living in each pre-primary school's catchment area
  (Chachement area.xlsx, Pop2027 ... Pop2030: NISR age 3 shared to schools by GIS).
  A school without a figure for a year keeps its last known one (its 2026 N1 when it
  has none). The file repeats 2029 for 2030 and is used as given. Every child is
  assumed to enter; repetition is not modelled.
  The intake plan (editable, district x year) defaults to the district totals of these
  figures; a district's plan is shared to its schools in proportion to their catchment:
      new N1(school) = ROUND(plan x school catchment / district catchment)   (half up)
* P1 = the N3 of y-1 (children who did not attend pre-primary are not added, as the
  user decided). A school offering primary takes its own N3; the N3 of schools without
  primary (stand-alone nurseries) is pooled by sector and shared to the sector's primary
  schools by their 2026 P1 (the district when a sector has no P1 to receive it).
* S1 = every P6 pupil of the district in y-1 (all of P6 moves on).
* S4 / L3 / Y1 = every S3 student of the district in y-1, split by the district's
  2026 mix of S4 / L3 / Y1 students.
* A district (or sector) pool of new students of a grade is shared to its schools in
  proportion to each school's students of that grade in 2026:
      new(school) = ROUND(pool x school share)          (half up)
  New students are formed into class groups at the school's 2026 average group size
  for that grade: CEILING(new / group size).

Cohorts (per school)
--------------------
Inside a level students and class groups move up one grade a year; the last
grade leaves the level (N3 and P6 and S3 and the final grades leave the school's
count — P6 and S3 re-enter secondary through the district pools above).

Combinations (Upper Secondary, TVET, TTC)
-----------------------------------------
Class groups there follow a subject combination or trade (MEG, Math and Science
Stream Two, SOD, ACC ...). The projection also splits each grade by combination —
a breakdown only, the grade figures above are unchanged:
* Students and class groups keep their combination as they move up (S4 MEG -> S5 MEG).
* The new S4 / L3 / Y1 students of a school are split between combinations in
  proportion to the school's 2026 students of each combination in that grade, and
  its new class groups in proportion to its 2026 class groups of each combination
  (whole numbers, largest remainder, ties to the combination listed first), so the
  combinations always add up to the grade.

Classrooms (per school and level, every year)
---------------------------------------------
* Rooms = the school's 2026 distinct physical rooms used by the level (no
  construction assumed). A room used by two levels counts in both, as in the
  2026 analysis.
* Level: Double Shift = MAX(0, class groups - rooms); Required = CEILING(students /
  capacity); Gap = rooms - required. For 2026 this reproduces the current analysis
  exactly (TVET without L1-L2).
* Sharing rooms between the grades of a level:
    more class groups than rooms -> rooms are shared out in proportion to each grade's
                                    class groups; the extra groups are on double shift.
    enough rooms                 -> every class group keeps a room; spare rooms go to the
                                    grades whose students need more rooms than they have
                                    groups; any rooms left over stay spare.
  Shares are whole rooms (largest remainder, ties to the lower grade). Grade Double Shift =
  class groups - rooms assigned; grade Gap = rooms assigned - CEILING(grade students / capacity).
* Full-day levels (Lower and Upper Secondary, TVET, TTC — analysis.FULL_DAY) have no double
  shift: every class group needs its own room and combinations never share.
      rooms needed (grade) = SUM over combinations of MAX(class groups, CEILING(students / capacity))
      Required (school)    = SUM of the grades' rooms needed
  Rooms are shared between grades in proportion to the rooms each grade needs (every grade gets
  what it needs when the school has enough). Double Shift = MAX(0, class groups - rooms) there
  means class groups without a room; they are also in the gap through Required.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import analysis as A

CATCHMENT_XLSX = A.DATA_DIR / "Chachement area.xlsx"  # children aged 3 per pre-primary school catchment, 2027-2030
BASE_YEAR = 2026
YEARS = [2026, 2027, 2028, 2029, 2030]

SHORT_COURSES = {"L1", "L2"}  # TVET short courses, not projected
# (level label, grades) in display order
LEVELS = [(label, [g for g in grades if g not in SHORT_COURSES]) for _, label, grades, _ in A.LEVELS]
GRADES = [g for _, grades in LEVELS for g in grades]
CAPACITY = {label: A.CAPACITY[label] for label, _ in LEVELS}

INTAKES = {"N1": 3}  # entry grade -> age of the children who enter it (catchment population)
SCHOOL_FEEDS = [("N3", "P1")]  # leavers -> entry grade next year, in the same school (else pooled by sector)
FEEDS = [("P6", ["S1"]), ("S3", ["S4", "L3", "Y1"])]  # leavers of a grade -> entry grades next year, per district
ENTRY = {grades[0] for _, grades in LEVELS}
COMBO_LEVELS = ["Upper Secondary", "TVET", "TTC"]  # levels whose class groups follow a combination / trade
DEFAULT_LABEL = "Catchment"  # name of the default intake plan


def round_half_up(x):
    return np.floor(np.asarray(x, dtype=float) + 0.5).astype(int)


# ---------------------------------------------------------------- intake (new N1 / P1 per district)
def load_intake_csv(path: Path) -> dict[str, pd.DataFrame]:
    """District x year tables from a CSV with columns district_name, pop3_2027 ...

    Returns {entry grade: table} for each age found (pop3 -> N1; older pop6 columns are ignored)."""
    t = pd.read_csv(path, thousands=",").set_index("district_name")
    t.index.name = "district"
    out = {}
    for grade, age in INTAKES.items():
        cols = {c: int(m.group(1)) for c in t.columns if (m := re.fullmatch(rf"pop{age}_(\d{{4}})", str(c)))}
        if cols:
            out[grade] = t[list(cols)].rename(columns=cols).astype(int)
    return out


def read_catchment() -> tuple[pd.DataFrame, pd.Series]:
    """The catchment file: (children aged 3 per school_code x 2027-2030, NaN when missing; 2026 N1 enrolment)."""
    c = pd.read_excel(CATCHMENT_XLSX).set_index("school_code")
    return c[[f"Pop{y}" for y in YEARS[1:]]].set_axis(YEARS[1:], axis=1), c["N1"]


def fill_catchment(pop: pd.DataFrame, n1: pd.Series) -> pd.DataFrame:
    """Children aged 3 in each pre-primary school's catchment: school_code x 2027-2030 (whole numbers).

    A missing year takes the school's last known value, its 2026 N1 enrolment when it has none."""
    t = pd.concat([n1.rename(BASE_YEAR), pop.reindex(columns=YEARS[1:])], axis=1)
    return t.ffill(axis=1).fillna(0).round().astype(int)[YEARS[1:]]


def load_catchment() -> pd.DataFrame:
    """fill_catchment of the catchment file."""
    return fill_catchment(*read_catchment())


def default_intake(catchment: pd.DataFrame, info: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Default intake plan: {"N1": district x year} = the district totals of the school catchments."""
    district = info.set_index("school_code")["district"]
    return {"N1": catchment.groupby(district.reindex(catchment.index).to_numpy()).sum()}


def load_population() -> dict[str, pd.DataFrame]:
    """default_intake from the files (catchment file and roster)."""
    return default_intake(load_catchment(), A._school_info(A.load_roster()))


ESTIMATED = {"N1": [2030]}  # intake years not measured: the catchment file repeats 2029 for 2030


# ---------------------------------------------------------------- 2026 base
@dataclass
class Base:
    info: pd.DataFrame      # one row per school: code, name, district, sector, coordinates
    rooms: np.ndarray       # n x levels: 2026 physical rooms used by the level (0 = level not offered)
    students: np.ndarray    # n x GRADES
    groups: np.ndarray      # n x GRADES
    combos: dict[str, list[str]]           # combination level -> its combinations, most students first
    combo_students: dict[str, np.ndarray]  # combination level -> n x grades of the level x combinations
    combo_groups: dict[str, np.ndarray]


def base_schools(roster: pd.DataFrame) -> Base:
    df = roster[roster["grade"].isin(GRADES)]
    info = A._school_info(df).sort_values(["district", "sector", "school_name", "school_code"]).reset_index(drop=True)
    codes = info["school_code"]

    def by_grade(values: str, agg: str) -> np.ndarray:
        t = df.pivot_table(index="school_code", columns="grade", values=values, aggfunc=agg, fill_value=0)
        return t.reindex(index=codes, columns=GRADES, fill_value=0).to_numpy(dtype=int)

    rooms = (df.groupby(["school_code", "level"])["room_key"].nunique().unstack(fill_value=0)
             .reindex(index=codes, columns=[label for label, _ in LEVELS], fill_value=0).to_numpy(dtype=int))

    combos, c_students, c_groups = {}, {}, {}
    for label, grades in LEVELS:
        if label not in COMBO_LEVELS:
            continue
        d = df[df["level"] == label]
        tot = d.groupby("combination")[A.STUDENTS].sum().reset_index()
        names = tot.sort_values([A.STUDENTS, "combination"], ascending=[False, True])["combination"].tolist()
        combos[label] = names
        c_students[label] = _by_combo(d, codes, grades, names, A.STUDENTS, "sum")
        c_groups[label] = _by_combo(d, codes, grades, names, "room_key", "count")  # one row = one class group
    return Base(info, rooms, by_grade(A.STUDENTS, "sum"), by_grade("room_key", "size"), combos, c_students, c_groups)


def _by_combo(d: pd.DataFrame, codes: pd.Series, grades: list[str], names: list[str], values: str, agg: str) -> np.ndarray:
    """n x grades x combinations array of `values` aggregated per school, grade and combination."""
    t = d.pivot_table(index="school_code", columns=["grade", "combination"], values=values, aggfunc=agg, fill_value=0)
    cols = pd.MultiIndex.from_product([grades, names])
    return t.reindex(index=codes, columns=cols, fill_value=0).to_numpy(dtype=int).reshape(len(codes), len(grades), len(names))


def district_totals(info: pd.DataFrame, values: np.ndarray) -> pd.DataFrame:
    """District x grade totals of an n x GRADES array."""
    return pd.DataFrame(values, columns=GRADES).groupby(info["district"].to_numpy()).sum()


# ---------------------------------------------------------------- room sharing
def _largest_remainder(total: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Split each row's `total` whole units in proportion to `weights` (rows with zero weight get nothing)."""
    wsum = weights.sum(axis=1, keepdims=True)
    share = np.divide(total[:, None] * weights, wsum, out=np.zeros(weights.shape), where=wsum > 0)
    alloc = np.floor(share).astype(int)
    left = (np.where(wsum[:, 0] > 0, total, 0) - alloc.sum(axis=1)).astype(int)
    order = np.argsort(-(share - alloc), axis=1, kind="stable")  # largest fractions first, ties to lower grade
    for i in np.nonzero(left)[0]:
        alloc[i, order[i, : left[i]]] += 1
    return alloc


def share_rooms(rooms: np.ndarray, groups: np.ndarray, required: np.ndarray) -> np.ndarray:
    """Rooms assigned to each grade (n x grades of the level) — see the module docstring."""
    g_total = groups.sum(axis=1)
    crowded = g_total > rooms
    assigned = np.where(crowded[:, None], _largest_remainder(rooms, groups), groups)
    # Enough rooms: spare rooms go to grades needing more rooms than they have groups.
    extra_need = np.maximum(required - groups, 0)
    spare = np.where(crowded, 0, rooms - g_total)
    enough = spare >= extra_need.sum(axis=1)
    extra = np.where(enough[:, None], extra_need, _largest_remainder(spare, extra_need))
    return assigned + np.where(crowded[:, None], 0, extra)


def share_by_need(rooms: np.ndarray, need: np.ndarray) -> np.ndarray:
    """Full-day levels: each grade gets the rooms it needs, or a proportional share when the school has too few."""
    enough = rooms >= need.sum(axis=1)
    return np.where(enough[:, None], need, _largest_remainder(rooms, need))


# ---------------------------------------------------------------- projection
def project(roster: pd.DataFrame, intake: dict[str, pd.DataFrame] | None = None, *,
            catchment: pd.DataFrame | None = None, base: Base | None = None,
            ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the projection. `intake` = {"N1": district x year}; default: the catchment totals (default_intake).
    `catchment` (school_code x year, see fill_catchment) and `base` (base_schools) default to the files / the
    roster; the API passes them in, prepared once from the database.

    Returns (info, schools, grades, combos):
    info    one row per school (code, name, district, sector, coordinates)
    schools one row per school x level x year: students, class_groups, rooms, double_shift, required, gap
    grades  one row per school x level x year x grade: the same, with the rooms assigned to the grade
    combos  one row per school x grade x combination x year with students or class groups
            (Upper Secondary, TVET, TTC): students, class_groups"""
    b = base if base is not None else base_schools(roster)
    catchment = catchment if catchment is not None else load_catchment()
    intake = {**default_intake(catchment, b.info), **(intake or {})}
    info, gi = b.info, {g: k for k, g in enumerate(GRADES)}
    district = info["district"]
    n = len(info)

    d_2026 = district_totals(info, b.students)
    share = {g: np.divide(b.students[:, gi[g]], district.map(d_2026[g]).to_numpy(),
                          out=np.zeros(n), where=b.students[:, gi[g]] > 0) for g in ENTRY}
    size = {g: np.divide(b.students[:, gi[g]], b.groups[:, gi[g]],
                         out=np.full(n, float(CAPACITY[A.GRADE_TO_LEVEL[g]])), where=b.groups[:, gi[g]] > 0)
            for g in ENTRY}
    mix = {}
    for _, targets in FEEDS:
        entrants = d_2026[targets].sum(axis=1)
        for t in targets:
            mix[t] = district.map(d_2026[t] / entrants).fillna(0).to_numpy()

    # N1: each school's catchment, scaled so its district adds up to the plan
    catch = catchment.reindex(info["school_code"]).fillna(0).to_numpy(dtype=float)  # n x YEARS[1:]
    catch_total = pd.DataFrame(catch).groupby(district.to_numpy()).transform("sum").to_numpy()
    # N3 -> P1: schools offering the target level keep their own leavers; the others' leavers are pooled by
    # sector (district when the sector has none of the target grade) and shared by the 2026 students of that grade
    offers = {dst: b.rooms[:, [label for label, _ in LEVELS].index(A.GRADE_TO_LEVEL[dst])] > 0 for _, dst in SCHOOL_FEEDS}
    sector = (district + "|" + info["sector"]).to_numpy()

    def pool_share(dst: str, key: np.ndarray) -> np.ndarray:
        weight = np.where(offers[dst], b.students[:, gi[dst]], 0).astype(float)
        total = pd.Series(weight).groupby(key).transform("sum").to_numpy()
        return np.divide(weight, total, out=np.zeros(n), where=total > 0)

    sector_share = {dst: pool_share(dst, sector) for _, dst in SCHOOL_FEEDS}
    district_share = {dst: pool_share(dst, district.to_numpy()) for _, dst in SCHOOL_FEEDS}

    students, groups = b.students.copy(), b.groups.copy()
    c_students = {k: v.copy() for k, v in b.combo_students.items()}
    c_groups = {k: v.copy() for k, v in b.combo_groups.items()}
    level_grades = dict(LEVELS)
    school_frames, grade_frames, combo_frames = [], [], []
    for year in YEARS:
        if year > BASE_YEAR:
            prev_s, prev_g = students, groups
            students, groups = np.zeros_like(prev_s), np.zeros_like(prev_g)
            for _, grades in LEVELS:
                for k in range(1, len(grades)):
                    students[:, gi[grades[k]]] = prev_s[:, gi[grades[k - 1]]]
                    groups[:, gi[grades[k]]] = prev_g[:, gi[grades[k - 1]]]
            new = {}
            yi = YEARS.index(year) - 1
            for g in INTAKES:
                table = intake[g]
                plan = district.map(table[year]).fillna(0).to_numpy() if year in table.columns else np.zeros(n)
                new[g] = round_half_up(np.divide(plan * catch[:, yi], catch_total[:, yi],
                                                 out=np.zeros(n), where=catch_total[:, yi] > 0))
            for src, dst in SCHOOL_FEEDS:
                leavers = prev_s[:, gi[src]]
                away = np.where(offers[dst], 0, leavers).astype(float)
                sec_pool = pd.Series(away).groupby(sector).transform("sum").to_numpy()
                # sectors with leavers but no school to receive them: their leavers go to the district
                homeless = np.where(pd.Series(sector_share[dst]).groupby(sector).transform("sum").to_numpy() > 0, 0, away)
                dis_pool = pd.Series(homeless).groupby(district.to_numpy()).transform("sum").to_numpy()
                new[dst] = (np.where(offers[dst], leavers, 0) + round_half_up(sec_pool * sector_share[dst])
                            + round_half_up(dis_pool * district_share[dst]))
            for src, targets in FEEDS:
                pool = district.map(pd.Series(prev_s[:, gi[src]]).groupby(district.to_numpy()).sum()).to_numpy()
                for t in targets:
                    new[t] = round_half_up(pool * mix[t] * share[t])
            for g, v in new.items():
                students[:, gi[g]] = v
                groups[:, gi[g]] = np.ceil(v / size[g]).astype(int)
            for label in COMBO_LEVELS:  # combinations move up with their cohort; new entrants split by the 2026 mix
                e = gi[level_grades[label][0]]
                prev_cs, prev_cg = c_students[label], c_groups[label]
                c_students[label], c_groups[label] = np.zeros_like(prev_cs), np.zeros_like(prev_cg)
                c_students[label][:, 1:], c_groups[label][:, 1:] = prev_cs[:, :-1], prev_cg[:, :-1]
                c_students[label][:, 0] = _largest_remainder(students[:, e], b.combo_students[label][:, 0])
                c_groups[label][:, 0] = _largest_remainder(groups[:, e], b.combo_groups[label][:, 0])

        for label in COMBO_LEVELS:
            cs, cg = c_students[label], c_groups[label]
            i, k, c = np.nonzero((cs > 0) | (cg > 0))
            combo_frames.append(pd.DataFrame({
                "school_code": info["school_code"].to_numpy()[i],
                "level": label,
                "year": year,
                "grade": np.array(level_grades[label])[k],
                "combination": np.array(b.combos[label], dtype=object)[c],
                "students": cs[i, k, c],
                "class_groups": cg[i, k, c],
            }))

        for li, (label, grades) in enumerate(LEVELS):
            has = b.rooms[:, li] > 0
            cols = [gi[g] for g in grades]
            cap = CAPACITY[label]
            st, gr, rooms = students[has][:, cols], groups[has][:, cols], b.rooms[has, li]
            if label in A.FULL_DAY:  # every class group needs a room; combinations never share
                if label in c_students:
                    cs, cg = c_students[label][has], c_groups[label][has]
                    g_required = np.maximum(cg, np.ceil(cs / cap).astype(int)).sum(axis=2)
                else:
                    g_required = np.maximum(gr, np.ceil(st / cap).astype(int))
                g_rooms = share_by_need(rooms, g_required)
            else:
                g_required = np.ceil(st / cap).astype(int)
                g_rooms = share_rooms(rooms, gr, g_required)
            codes = info.loc[has, "school_code"].to_numpy()
            m = len(codes)
            grade_frames.append(pd.DataFrame({
                "school_code": np.repeat(codes, len(grades)),
                "level": label,
                "year": year,
                "grade": np.tile(grades, m),
                "students": st.ravel(),
                "class_groups": gr.ravel(),
                "rooms": g_rooms.ravel(),
                "double_shift": np.maximum(gr - g_rooms, 0).ravel(),
                "required": g_required.ravel(),
                "gap": (g_rooms - g_required).ravel(),
            }))
            total, g_total = st.sum(axis=1), gr.sum(axis=1)
            if label in A.FULL_DAY:
                required = g_required.sum(axis=1)
            else:
                required = np.array([math.ceil(s / cap) for s in total], dtype=int)
            school_frames.append(pd.DataFrame({
                "school_code": codes,
                "level": label,
                "year": year,
                "students": total,
                "class_groups": g_total,
                "rooms": rooms,
                "double_shift": np.maximum(g_total - rooms, 0),
                "required": required,
                "gap": rooms - required,
            }))

    return (info, pd.concat(school_frames, ignore_index=True), pd.concat(grade_frames, ignore_index=True),
            pd.concat(combo_frames, ignore_index=True))


def entrants(info: pd.DataFrame, grades: pd.DataFrame) -> pd.DataFrame:
    """Students in each entry grade by district and year (the new students from 2027)."""
    e = grades[grades["grade"].isin(ENTRY)].merge(info[["school_code", "district"]], on="school_code")
    return e.pivot_table(index=["grade", "district"], columns="year", values="students", aggfunc="sum", fill_value=0)


def summary(schools: pd.DataFrame) -> pd.DataFrame:
    """National totals per level and year."""
    out = schools.groupby(["level", "year"], sort=False).agg(
        schools=("school_code", "size"),
        students=("students", "sum"),
        class_groups=("class_groups", "sum"),
        rooms=("rooms", "sum"),
        double_shift=("double_shift", "sum"),
        required=("required", "sum"),
        net_gap=("gap", "sum"),
        short=("gap", lambda s: int(-s[s < 0].sum())),
        deficit_schools=("gap", lambda s: int((s < 0).sum())),
    )
    return out


if __name__ == "__main__":
    roster = A.load_roster()
    _, schools, _, combos = project(roster)
    print("New students: N1 / P1 = NISR ages 3 / 6 (N1 2030 estimated); S1 = P6 of the year before; "
          "S4 / L3 / Y1 = S3 of the year before, district 2026 mix")
    print(summary(schools).to_string())
    print(combos.pivot_table(index=["level", "combination"], columns="year", values="students", aggfunc="sum",
                             fill_value=0).to_string())
