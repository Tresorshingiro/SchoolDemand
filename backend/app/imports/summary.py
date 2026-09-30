"""School data as a grade summary (MINEDUC's layout): one row per school x grade x combination with the number of
classrooms, classrooms in double shift and students, instead of one row per class group.

It is turned into class-group rows so that the rest of the checks, the database and the engine are unchanged:
* class groups = classrooms + classrooms in double shift (a room in double shift holds a second group);
* the grade's classrooms are its own rooms; its groups are spread over them (the first ones get the second group);
* students are shared evenly between the grade's class groups (whole numbers, the first groups get the remainder);
* a grade without a classroom of its own shares a room of another grade of the same level at the school (else of any
  level; else it gets one room) — its groups count as double shift, as MINEDUC records them;
* Pre-Primary, Primary and Lower Secondary take one combination each (PPR, PR, OL, as in the class-group data);
  the other levels keep the file's combination / trade. Rows of the same school, grade and combination are added up
  first (MINEDUC sometimes splits a grade over two rows with a filler combination: "PRIMARY", "PRE PRIMARY", empty).
"""
from __future__ import annotations

import pandas as pd

from ..domain import analysis as A
from ..domain import projection as P
from .report import Report
from .tables import pick_columns

CLASSROOMS = "Number of classrooms"
DOUBLE_SHIFT = "Number of classrooms in double shift"
REQUIRED = ["school_code", "school_name", "district", "sector", "latitude", "longitude", "grade", CLASSROOMS,
            DOUBLE_SHIFT, A.STUDENTS]
ALIASES = {"students": A.STUDENTS, "classrooms": CLASSROOMS, "double_shift": DOUBLE_SHIFT}
LEVEL_COMBINATION = {"Pre-Primary": "PPR", "Primary": "PR", "Lower Secondary": "OL"}  # levels without combinations


def is_summary(raw: pd.DataFrame) -> bool:
    """A grade summary has the classroom counts and no class_group column."""
    got, missing = pick_columns(raw, [CLASSROOMS, DOUBLE_SHIFT, "class_group"], aliases=ALIASES)
    return missing == ["class_group"]


def _label(grade: str, combination, i: int, combo_level: bool) -> str:
    letter = chr(65 + i) if i < 26 else str(i + 1)
    return f"{grade} {combination} {letter}" if combo_level and combination else f"{grade} {letter}"


def expand_summary(raw: pd.DataFrame, rep: Report) -> pd.DataFrame | None:
    """Class-group rows (the class-group layout's columns, with test_code and the file row in "row"), or None when
    the file has errors (added to `rep`)."""
    df, missing = pick_columns(raw, REQUIRED, ["combination"], ALIASES)
    if missing:
        rep.error("missing_columns", "Missing columns: " + ", ".join(missing))
        return None
    df = df.reset_index(drop=True)
    df.insert(0, "row", df.index + 2)
    show = ["row", "school_code", "school_name", "grade"]
    numbers = {}
    for col in (CLASSROOMS, DOUBLE_SHIFT, A.STUDENTS):
        n = pd.to_numeric(df[col], errors="coerce")
        bad = n.isna() | (n % 1 != 0) | (n < 0)
        rep.error("students" if col == A.STUDENTS else "classrooms", f"{col} empty, negative or not a whole number",
                  df.loc[bad, [*show, col]])
        numbers[col] = n
    code = pd.to_numeric(df["school_code"], errors="coerce")
    if not rep.ok:
        return None
    df["code"] = code
    df["grade"] = df["grade"].astype(str).str.strip().str.upper()
    df["level"] = df["grade"].map(A.GRADE_TO_LEVEL)
    if "combination" not in df:
        df["combination"] = None
    fixed = df["level"].map(LEVEL_COMBINATION)
    df["combination"] = fixed.where(fixed.notna(), df["combination"].where(df["combination"].isna(),
                                                                         df["combination"].astype(str).str.strip()))
    # one row per school x grade x combination: rows that differ only by a filler combination ("PRIMARY", empty ...)
    # are one grade (the first row's details are kept)
    df[CLASSROOMS], df[DOUBLE_SHIFT], df[A.STUDENTS] = (numbers[c].astype(int) for c in (CLASSROOMS, DOUBLE_SHIFT, A.STUDENTS))
    key = [df["code"], df["grade"], df["combination"].fillna("")]
    sums = df.groupby(key, dropna=False)[[CLASSROOMS, DOUBLE_SHIFT, A.STUDENTS]].transform("sum")
    df[[CLASSROOMS, DOUBLE_SHIFT, A.STUDENTS]] = sums
    df = df[~pd.concat(key, axis=1).duplicated()].reset_index(drop=True)
    rooms_n, shift_n, students_n = df[CLASSROOMS], df[DOUBLE_SHIFT], df[A.STUDENTS]

    empty = (students_n == 0) & (rooms_n == 0) & (shift_n == 0)
    rep.warning("empty_rows", "Rows without students or classrooms (left out)", df.loc[empty, show])
    over = shift_n > rooms_n
    rep.warning("double_shift_over", "More classrooms in double shift than classrooms (class groups = both added up)",
                df.loc[over & (rooms_n > 0), [*show, CLASSROOMS, DOUBLE_SHIFT]])

    # the rooms of each grade row; the first room of each school x level and of each school, for grades without one
    own = {i: [f"r{df.at[i, 'row']}-{k + 1}" for k in range(rooms_n[i])] for i in df.index}
    names = {room: f"{df.at[i, 'grade']} room {k + 1}" for i, rs in own.items() for k, room in enumerate(rs)}
    by_level, by_school = {}, {}
    for i in df.index:
        if own[i]:
            by_level.setdefault((df.at[i, "code"], df.at[i, "level"]), own[i][0])
            by_school.setdefault(df.at[i, "code"], own[i][0])

    rows, borrowed, created = [], [], []
    for i in df.index:
        if empty[i]:
            continue
        r = df.loc[i]
        n = max(int(rooms_n[i] + shift_n[i]), 1)
        rooms = own[i]
        if not rooms:
            shared = by_level.get((r["code"], r["level"])) or by_school.get(r["code"])
            if shared is None:
                shared = f"r{r['row']}-1"
                names[shared] = f"{r['grade']} room 1"
                created.append(i)
            else:
                borrowed.append(i)
            rooms = [shared]
        combo_level = r["level"] in P.COMBO_LEVELS
        base, extra = divmod(int(students_n[i]), n)
        for g in range(n):
            room = rooms[g % len(rooms)]
            rows.append({"row": r["row"], "school_code": r["school_code"], "school_name": r["school_name"],
                         "district": r["district"], "sector": r["sector"], "latitude": r["latitude"],
                         "longitude": r["longitude"], "grade": r["grade"], "combination": r["combination"],
                         "class_group": _label(r["grade"], r["combination"], g, combo_level),
                         "classroom_id": room, "classroom_name": names[room],
                         A.STUDENTS: base + (1 if g < extra else 0), A.ROOM_ID: room})
    rep.warning("no_own_room", "Grade without a classroom of its own: its class groups share a room of another grade "
                               "(counted as double shift)", df.loc[borrowed, [*show, A.STUDENTS]])
    rep.warning("room_added", "School without any classroom for these students: counted as one room",
                df.loc[created, [*show, A.STUDENTS]])
    return pd.DataFrame(rows)
