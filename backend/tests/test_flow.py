"""Repetition and dropout: reading the rates and the flow in the projection (no database needed)."""
import math

import pandas as pd
import pytest

from app.domain import analysis as A
from app.domain import projection as P
from app.domain import rates as RT
from tests.flow_samples import sheet, two_sheets
from tests.test_horizon import tiny_roster


# ---------------------------------------------------------------- the rates file
def test_reads_the_latest_average():
    long = RT.read_sheets(two_sheets())
    assert sorted(long["end_year"].unique()) == [2023, 2024]
    r = RT.latest(long)
    assert r.school_year == "2023/24"
    assert r.table.loc["Gasabo"].tolist() == [0.107, 0.035]


def test_missing_sheet_is_an_error():
    with pytest.raises(ValueError, match="Dropout"):
        RT.read_sheets({"Repetition Rate": sheet("x", {"Rwanda": (0.1, 0.1)})})


def test_unknown_district_uses_rwanda():
    r = RT.FlowRates("2023/24", pd.DataFrame({"repetition": [0.1, 0.2], "dropout": [0.01, 0.05]},
                                             index=["Gasabo", "Rwanda"]))
    rep, drop = RT.school_rates(r, pd.Series(["Gasabo", "Unknown", "Huye"]))
    assert rep.tolist() == [0.1, 0.2, 0.2] and drop.tolist() == [0.01, 0.05, 0.05]


def test_the_mineduc_file():
    r = RT.load_rates()
    assert r.school_year == "2023/24" and len(r.table) == 31
    assert r.table.loc["Rwanda"].tolist() == pytest.approx([0.204, 0.049])


# ---------------------------------------------------------------- the flow in the projection
RATES = RT.FlowRates("2023/24", pd.DataFrame({"repetition": [0.2], "dropout": [0.05]}, index=["Rwanda"]))


def tiny_roster_with(students: int) -> pd.DataFrame:
    """tiny_roster with every class group of `students` students."""
    r = tiny_roster()
    r[A.STUDENTS] = students
    return r


def run(rates: RT.FlowRates, roster: pd.DataFrame | None = None):
    roster = roster if roster is not None else tiny_roster()
    catch = pd.DataFrame({y: [40] for y in P.YEARS[1:]}, index=pd.Index([1], name="school_code"))
    return P.project(roster, catchment=catch, rates=rates)


def year_grades(g: pd.DataFrame, year: int, measure: str = "students") -> pd.Series:
    return g[g["year"] == year].set_index("grade")[measure]


def test_hand_worked_primary():
    # every grade 40 in 2026, r = 0.2, d = 0.05: repeaters 8, dropouts 2, promoted 30
    y = year_grades(run(RATES)[2], 2027)
    assert y["P2"] == 30 + 8          # promoted P1 + repeaters of P2
    assert y["P6"] == 30 + 8
    assert y["S1"] == 8 + 30          # its repeaters + the promoted P6 of the district (one school)


def test_students_are_conserved():
    # Pre-Primary 2026: 120 students; 2027 = 120 - 6 dropouts - 30 promoted N3 + 40 new N1 = 124
    y = year_grades(run(RATES)[2], 2027)
    assert (y["N1"], y["N2"], y["N3"]) == (48, 38, 38)
    assert y["P1"] == 30 + 8          # the promoted N3 (same school) + repeaters of P1


def test_zero_rates_keep_todays_students():
    y = year_grades(run(RT.ZERO)[2], 2027)
    assert y["P2"] == 40 and y["S2"] == 40 and y["N1"] == 40   # the plain cohort shift


def test_zero_rates_keep_todays_class_groups():
    # S4 2026: PCB 60 students in 3 groups of 20, S5 empty: the groups move up with their cohort (3, not ceil(60/46))
    r = tiny_roster()
    pcb = r[r["grade"] == "S4"].iloc[[0, 0, 0]].assign(combination="PCB", **{A.STUDENTS: 20})
    pcb[A.ROOM_ID] = ["p1", "p2", "p3"]
    r = A.prepare_roster(pd.concat([r, pcb], ignore_index=True))
    _, _, g, c = run(RT.ZERO, r)
    s5 = c[(c["year"] == 2027) & (c["grade"] == "S5")].set_index("combination")
    assert s5.loc["PCB", "class_groups"] == 3 and s5.loc["MEG", "class_groups"] == 1


def test_small_grades_never_go_negative():
    high = RT.FlowRates("x", pd.DataFrame({"repetition": [0.5], "dropout": [0.5]}, index=["Rwanda"]))
    _, s, g, c = run(high, tiny_roster_with(1))
    assert (s["students"] >= 0).all() and (g["students"] >= 0).all() and (c["students"] >= 0).all()


def test_combinations_add_up_to_the_grade():
    _, _, g, c = run(RATES)
    a = c.groupby(["year", "school_code", "grade"])["students"].sum()
    b = g.set_index(["year", "school_code", "grade"])["students"].reindex(a.index)
    assert (a == b).all()
    assert year_grades(g, 2027)["S5"] == 30       # the promoted S4 MEG of 2026 (S5 had no students then)


def test_group_size_does_not_drift():
    # P1..P6 of 258 students in 7 groups each: a cohort keeps its size of 258/7 as it moves up, so 4 years on P6
    # holds CEILING(students / (258 / 7)) groups — not more because each year's rounding up shrank the size
    r = tiny_roster()
    p = r[r["grade"].str.startswith("P")]
    many = pd.concat([p.assign(**{A.STUDENTS: s}) for s in (37, 37, 37, 37, 37, 37, 36)], ignore_index=True)
    many[A.ROOM_ID] = [f"r{k}" for k in range(len(many))]
    r = A.prepare_roster(pd.concat([r[~r["grade"].str.startswith("P")], many], ignore_index=True))
    _, _, g, _ = run(RATES, r)
    p6 = g[(g["year"] == 2030) & (g["grade"] == "P6")].iloc[0]
    assert p6["class_groups"] == math.ceil(p6["students"] / (258 / 7) - 1e-9)


def test_small_combination_intake_never_corrupts_the_groups():   # final review, Important 1
    # S4 2026: MEG 40 students in 1 group, PCB 2 students in 2 groups; S3 of 3 students feeds a tiny S4 intake that the
    # student split gives all to MEG while the group split gave PCB a group: a combination group without students must
    # not leave a group size of 0 behind (0 / 0 the year after)
    r = tiny_roster()
    r.loc[r["grade"] == "S3", A.STUDENTS] = 3
    pcb = r[r["grade"] == "S4"].iloc[[0, 0]].assign(combination="PCB", **{A.STUDENTS: 1})
    pcb[A.ROOM_ID] = ["p1", "p2"]
    r = A.prepare_roster(pd.concat([r, pcb], ignore_index=True))
    _, s, g, c = run(RT.ZERO, r)
    for f in (s, g, c):
        assert f["class_groups"].between(0, 10_000).all()
    assert not ((c["students"] > 0) & (c["class_groups"] == 0)).any()
    assert not ((c["students"] == 0) & (c["class_groups"] > 0)).any()


def test_entry_groups_count_the_students_they_hold():
    # S4 2026: MEG 25 and PCB 25 students in 5 groups of 5 each; S3 of 7 feeds S4 only. r = 0.3: each combination keeps
    # ROUND(7.5) = 8 repeaters (16 in all, where the grade's ROUND(15.0) is 15) and 5 promoted S3 arrive: S4 2027 holds
    # 21 students, so 5 groups of at most 5 (not 4, counted from the grade's 20)
    r = tiny_roster()
    r = r[~r["grade"].isin(["L3", "Y1", "S4"])]
    r.loc[r["grade"] == "S3", A.STUDENTS] = 7
    base = tiny_roster().query("grade == 'S4'").iloc[0]
    s4 = pd.DataFrame([{**base.to_dict(), "combination": combo, A.STUDENTS: 5, A.ROOM_ID: f"{combo}{k}"}
                       for combo in ("MEG", "PCB") for k in range(5)])
    r = A.prepare_roster(pd.concat([r, s4], ignore_index=True))
    rates = RT.FlowRates("x", pd.DataFrame({"repetition": [0.3], "dropout": [0.0]}, index=["Rwanda"]))
    got = run(rates, r)[2].query("year == 2027 and grade == 'S4'").iloc[0]
    assert (got["students"], got["class_groups"]) == (21, 5)


def test_class_groups_follow_students():
    groups = year_grades(run(RATES)[2], 2027, "class_groups")
    assert groups["P2"] == math.ceil(38 / 40)      # 38 students, the school's P2 groups are of 40
    assert groups["N1"] == math.ceil(48 / 40)
