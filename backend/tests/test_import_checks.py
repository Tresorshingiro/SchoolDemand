"""Reading and checking data files (no database needed)."""
import pandas as pd
import pytest

from app.domain import analysis as A
from app.imports.report import Report
from app.imports.rooms import room_ids
from app.imports.tables import pick_columns, read_table, year_columns


# ---------------------------------------------------------------- Task 3: tables, report, rooms
def test_read_csv_with_bom_and_semicolons(tmp_path):
    p = tmp_path / "plan.csv"
    p.write_bytes("﻿district_name;pop3_2028\nGasabo;1200\n".encode("utf-8"))
    df = read_table(p)
    assert list(df.columns) == ["district_name", "pop3_2028"] and df.iloc[0].tolist() == ["Gasabo", "1200"]


def test_read_xlsx_first_sheet(tmp_path):
    p = tmp_path / "c.xlsx"
    with pd.ExcelWriter(p) as w:
        pd.DataFrame({"School Code": [1], "Pop2028": [5]}).to_excel(w, index=False, sheet_name="first")
        pd.DataFrame({"x": [9]}).to_excel(w, index=False, sheet_name="second")
    assert list(read_table(p).columns) == ["School Code", "Pop2028"]


def test_pick_columns_ignores_case_spaces_underscores():
    df = pd.DataFrame(columns=["School Code", "GRADE", "students", "extra"])
    got, missing = pick_columns(df, ["school_code", "grade", "Number of students", "sector"],
                                aliases={"students": "Number of students"})
    assert list(got.columns) == ["school_code", "grade", "Number of students"] and missing == ["sector"]


def test_year_columns():
    df = pd.DataFrame(columns=["school_code", "Pop2028", "pop_2029", "Footprints_2028", "pop3_2030"])
    assert year_columns(df, "pop") == {2028: "Pop2028", 2029: "pop_2029"}
    assert year_columns(df, "pop3") == {2030: "pop3_2030"}


def test_report_keeps_20_rows_and_all_issues():
    r = Report()
    r.error("big", "Too big", pd.DataFrame({"row": range(2, 32)}))
    r.warning("none", "Nothing to show", pd.DataFrame({"row": []}))   # empty: not added
    r.warning("note", "A note without rows")
    j = r.to_json()
    assert not r.ok and j["errors"][0]["count"] == 30 and len(j["errors"][0]["rows"]) == Report.MAX_ROWS
    assert [w["code"] for w in j["warnings"]] == ["note"]
    assert len(r.issues()) == 30 and set(r.issues().columns) >= {"severity", "problem", "row"}


def test_room_ids_split_rooms_with_three_groups():
    df = pd.DataFrame({"school_code": [1, 1, 1, 1, 1, 2], "row": [2, 3, 4, 5, 6, 7],
                       "classroom_id": ["a", "a", "b", "b", "b", None]})
    assert room_ids(df).tolist() == ["a", "a", "b#1", "b#2", "b#3", "row-7"]


def test_room_ids_reproduce_version_2():
    """The rule gives exactly the rooms of Version 2.xlsx's test_code (same grouping of class groups)."""
    if not A.SOURCE_XLSX.exists():
        pytest.skip("Version 2.xlsx not present")
    df = A.load_roster().reset_index(drop=True)
    df["row"] = df.index + 2
    a = pd.DataFrame({"computed": df["school_code"].astype(str) + "|" + room_ids(df),
                      "file": df["school_code"].astype(str) + "|" + df[A.ROOM_ID].astype(str)})
    assert a.groupby("computed")["file"].nunique().max() == 1
    assert a.groupby("file")["computed"].nunique().max() == 1


# ---------------------------------------------------------------- Task 4: checks
from app.domain import projection as P  # noqa: E402
from app.imports.checks import ROSTER_COLUMNS, CheckContext, check_catchment, check_nisr, check_school_data  # noqa: E402


def school_file(**over) -> pd.DataFrame:
    """A small school-data file: one primary school with 3 class groups (2 share a room) and a nursery."""
    rows = [
        (110103, "EP GITEGA", "Nyarugenge", "Gitega", -1.95978, 30.05631, "P1", None, "P1 A", "r1", "Room 1", 50),
        (110103, "EP GITEGA", "Nyarugenge", "Gitega", -1.95978, 30.05631, "P1", None, "P1 B", "r1", "Room 1", 48),
        (110103, "EP GITEGA", "Nyarugenge", "Gitega", -1.95978, 30.05631, "P2", None, "P2 A", "r2", "Room 2", 45),
        (110107, "The Source", "Nyarugenge", "Gitega", -1.958822, 30.05572, "N1", None, "N1 A", "r9", "Room 9", 14),
    ]
    cols = ["school_code", "school_name", "district", "sector", "latitude", "longitude", "grade", "combination",
            "class_group", "classroom_id", "classroom_name", "Number of students"]
    df = pd.DataFrame(rows, columns=cols)
    for k, v in over.items():
        df[k] = v
    return df


def context(**over) -> CheckContext:
    previous = A.prepare_roster(school_file().assign(test_code=["r1", "r1", "r2", "r9"]))
    base = dict(horizon=P.Horizon(2026), sectors={("Nyarugenge", "Gitega")},
                districts=["Gasabo", "Kicukiro", "Nyarugenge"], live_years=[2026], preprimary={110107},
                catchment_totals=pd.DataFrame({2027: [100], 2028: [100], 2029: [100], 2030: [100]}, index=["Gasabo"]),
                roster_of=lambda y: previous)
    return CheckContext(**{**base, **over})


def test_good_school_file():
    roster, rep = check_school_data(school_file(), 2027, context())
    assert rep.ok, rep.errors
    assert list(roster.columns[:13]) == [
        "school_code", "school_name", "district", "sector", "latitude", "longitude", "grade", "combination",
        "class_group", "classroom_id", "classroom_name", A.STUDENTS, A.ROOM_ID]
    assert roster[A.ROOM_ID].tolist() == ["r1", "r1", "r2", "r9"]
    assert rep.changes["against"] == 2026 and rep.changes["replaces"] is False
    primary = next(r for r in rep.changes["levels"] if r["level"] == "Primary")
    assert primary["students"] == [143, 143]
    assert rep.summary["schools"] == 2 and rep.summary["class_groups"] == 4


def test_numbers_as_text_are_accepted():
    df = school_file(school_code=["110103.0", "110103", "110103", "110107"]).astype(str)
    roster, rep = check_school_data(df, 2027, context())
    assert rep.ok, rep.errors
    assert roster["school_code"].tolist() == [110103, 110103, 110103, 110107]
    assert roster[A.STUDENTS].tolist() == [50, 48, 45, 14]


@pytest.mark.parametrize("change, code", [
    (lambda d: d.drop(columns=["sector"]), "missing_columns"),
    (lambda d: d.iloc[0:0], "no_rows"),
    (lambda d: d.assign(grade=["P1", "P1", "Q7", "N1"]), "grade"),
    (lambda d: d.assign(**{"Number of students": [50, -1, 45, 14]}), "students"),
    (lambda d: d.assign(**{"Number of students": [50, 4.5, 45, 14]}), "students"),
    (lambda d: d.assign(school_code=[None, 110103, 110103, 110107]), "school_code"),
    (lambda d: d.assign(school_name=[None, None, None, "The Source"]), "school_name"),
])
def test_school_file_errors(change, code):
    roster, rep = check_school_data(change(school_file()), 2027, context())
    assert roster is None and code in [e["code"] for e in rep.errors]


def test_school_file_warnings():
    df = school_file(latitude=[-1.95978, -1.95978, -1.95978, None])      # the nursery cannot be placed
    df.loc[2, "classroom_id"] = None                                      # a class group without a room
    df.loc[0, "sector"] = "Nowhere"      # the school's first row: an unknown sector, and two sectors for one school
    roster, rep = check_school_data(df, 2027, context())
    codes = [w["code"] for w in rep.warnings]
    assert {"excluded", "no_classroom", "unknown_sector", "several_values"} <= set(codes)
    assert 110107 not in roster["school_code"].tolist()                   # excluded
    assert roster.loc[roster["class_group"] == "P2 A", A.ROOM_ID].iloc[0] == "row-4"
    excluded = next(w for w in rep.warnings if w["code"] == "excluded")
    assert "14 students" in excluded["message"]


def test_same_year_replaces():
    _, rep = check_school_data(school_file(), 2026, context())
    assert rep.changes["replaces"] is True and rep.changes["against"] == 2026


def test_catchment_file():
    raw = pd.DataFrame({"school_code": [110107, 999, 110107], "Pop2027": [40, 5, 41], "Pop2028": [42, 6, 43],
                        "footprints_2027": [1, 1, 1]})
    parsed, rep = check_catchment(raw, None, context())
    assert rep.ok and parsed.loc[110107].tolist() == [40, 42] and list(parsed.columns) == [2027, 2028]
    codes = {w["code"] for w in rep.warnings}
    assert {"duplicates", "unknown_schools", "years"} <= codes      # 999 is not pre-primary; 2029-2030 repeat 2028


@pytest.mark.parametrize("raw, code", [
    (pd.DataFrame({"code": [1], "Pop2027": [4]}), "missing_columns"),
    (pd.DataFrame({"school_code": [1]}), "missing_columns"),
    (pd.DataFrame({"school_code": [110107], "Pop2027": ["many"]}), "values"),
    (pd.DataFrame({"school_code": [110107], "Pop2027": [-4]}), "values"),
])
def test_catchment_errors(raw, code):
    parsed, rep = check_catchment(raw, None, context())
    assert parsed is None and code in [e["code"] for e in rep.errors]


def test_nisr_file():
    raw = pd.DataFrame({"District": ["gasabo", "Kicukiro"], "pop3_2027": [150, 90], "pop3_2028": [151, 91]})
    parsed, rep = check_nisr(raw, None, context())
    assert rep.ok and parsed.loc["Gasabo"].tolist() == [150, 151]
    codes = {w["code"] for w in rep.warnings}
    assert {"missing_districts", "years", "difference"} <= codes    # Nyarugenge missing; Gasabo 150 vs catchment 100


@pytest.mark.parametrize("raw, code", [
    (pd.DataFrame({"district_name": ["Atlantis"], "pop3_2027": [5]}), "unknown_districts"),
    (pd.DataFrame({"district_name": ["Gasabo", "gasabo"], "pop3_2027": [5, 6]}), "duplicates"),
    (pd.DataFrame({"district_name": ["Gasabo"], "pop_2027": [5]}), "missing_columns"),
])
def test_nisr_errors(raw, code):
    parsed, rep = check_nisr(raw, None, context())
    assert parsed is None and code in [e["code"] for e in rep.errors]


# ---------------------------------------------------------------- school data as a grade summary (MINEDUC layout)
def summary_file(**over) -> pd.DataFrame:
    """One row per school x grade x combination with classroom counts (the MINEDUC layout)."""
    rows = [
        (110103, "EP GITEGA", "Kigali City", "Nyarugenge", "Gitega", -1.95978, 30.05631, "PRIMARY", "P1", 1, 1, 98),
        (110103, "EP GITEGA", "Kigali City", "Nyarugenge", "Gitega", -1.95978, 30.05631, "PRIMARY", "P2", 1, 0, 45),
        (110103, "EP GITEGA", "Kigali City", "Nyarugenge", "Gitega", -1.95978, 30.05631, "PRIMARY", "P3", 0, 1, 30),
        (110103, "EP GITEGA", "Kigali City", "Nyarugenge", "Gitega", -1.95978, 30.05631, "MEG", "S4", 2, 0, 81),
        (110107, "The Source", "Kigali City", "Nyarugenge", "Gitega", -1.958822, 30.05572, "PRE PRIMARY", "N1", 0, 0, 14),
    ]
    cols = ["school_code", "school_name", "province", "district", "sector", "latitude", "longitude", "combination",
            "grade", "Number of classrooms", "Number of classrooms in double shift", "Number of students"]
    df = pd.DataFrame(rows, columns=cols)
    for k, v in over.items():
        df[k] = v
    return df


def test_grade_summary_becomes_class_groups():
    roster, rep = check_school_data(summary_file(), 2026, context())
    assert rep.ok, rep.errors
    assert rep.summary["layout"] == "grade summary" and rep.summary["students"] == 98 + 45 + 30 + 81 + 14
    t = A.grade_table(roster).set_index(["school_code", "grade"])
    # class groups = classrooms + double shift; rooms = classrooms; double shift as recorded
    assert t.loc[(110103, "P1"), ["total_students", "total_classrooms", "available", "double_shift"]].tolist() == [98, 2, 1, 1]
    assert t.loc[(110103, "P2"), ["total_classrooms", "available", "double_shift"]].tolist() == [1, 1, 0]
    # P3 has no room of its own: its group shares a Primary room, so Primary has 2 rooms for 4 groups
    s = A.school_table(roster).set_index(["school_code", "level"])
    assert s.loc[(110103, "Primary"), ["total_classrooms", "available", "double_shift"]].tolist() == [4, 2, 2]
    assert s.loc[(110103, "Upper Secondary"), ["total_classrooms", "available", "gap"]].tolist() == [2, 2, 0]
    # students shared between the grade's groups; combinations: fixed code for Primary, the file's for S4
    p1 = roster[roster["grade"] == "P1"]
    assert sorted(p1[A.STUDENTS].tolist()) == [49, 49] and set(p1["combination"]) == {"PR"}
    assert set(roster.loc[roster["grade"] == "S4", "class_group"]) == {"S4 MEG A", "S4 MEG B"}
    # the nursery has no classroom at all: one room is counted
    assert s.loc[(110107, "Pre-Primary"), ["total_classrooms", "available"]].tolist() == [1, 1]
    codes = {w["code"] for w in rep.warnings}
    assert {"no_own_room", "room_added"} <= codes
    assert set(roster.columns) >= set(ROSTER_COLUMNS)


def test_grade_summary_adds_up_split_grades():
    """A grade split over two rows by a filler combination is one grade: its students join the grade's rooms."""
    extra = summary_file().iloc[[1]].assign(combination=None, **{"Number of classrooms": 0, "Number of students": 5})
    roster, rep = check_school_data(pd.concat([summary_file(), extra], ignore_index=True), 2026, context())
    assert rep.ok, rep.errors
    t = A.grade_table(roster).set_index(["school_code", "grade"])
    assert t.loc[(110103, "P2"), ["total_students", "total_classrooms", "available", "double_shift"]].tolist() == [50, 1, 1, 0]
    assert "Repeated class group name" not in [w["message"] for w in rep.warnings]


def test_grade_summary_errors():
    roster, rep = check_school_data(summary_file(**{"Number of classrooms": [1, 1, "two", 2, 0]}), 2026, context())
    assert roster is None and "classrooms" in [e["code"] for e in rep.errors]
    roster, rep = check_school_data(summary_file().drop(columns=["sector"]), 2026, context())
    assert roster is None and "missing_columns" in [e["code"] for e in rep.errors]
