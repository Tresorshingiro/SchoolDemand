"""The projection engine on any horizon (no database needed)."""
import numpy as np
import pandas as pd

from app.domain import analysis as A
from app.domain import dashboard as D
from app.domain import projection as P


def tiny_roster() -> pd.DataFrame:
    """One school with every level's entry grades (enough for the engine)."""
    grades = ["N1", "N2", "N3", "P1", "P2", "P3", "P4", "P5", "P6", "S1", "S2", "S3", "S4", "L3", "Y1"]
    combo = {"S4": "MEG", "L3": "SOD", "Y1": "TTC"}
    rows = [{"school_code": 1, "school_name": "School", "district": "Gasabo", "sector": "Remera", "latitude": -1.95,
             "longitude": 30.1, "grade": g, "combination": combo.get(g), "class_group": f"{g}A", "classroom_id": f"r{g}",
             "classroom_name": g, A.STUDENTS: 40, A.ROOM_ID: f"r{g}"} for g in grades]
    return A.prepare_roster(pd.DataFrame(rows))


def test_horizon_years():
    h = P.Horizon(2027)
    assert h.years == [2027, 2028, 2029, 2030, 2031] and h.future == [2028, 2029, 2030, 2031]
    assert P.DEFAULT_HORIZON.years == P.YEARS == [2026, 2027, 2028, 2029, 2030]


def test_fill_catchment_on_a_later_horizon():
    pop = pd.DataFrame({2027: [10.0, np.nan], 2028: [12.0, np.nan], 2029: [np.nan, 7.0]},
                       index=pd.Index([1, 2], name="school_code"))
    n1 = pd.Series({1: 5.0, 2: 3.0, 3: 4.0})
    t = P.fill_catchment(pop, n1, P.Horizon(2027))
    assert list(t.columns) == [2028, 2029, 2030, 2031]
    assert t.loc[1].tolist() == [12, 12, 12, 12]      # 2029 onwards: its last known value
    assert t.loc[2].tolist() == [3, 7, 7, 7]          # before its first figure: its N1 students
    assert t.loc[3].tolist() == [4, 4, 4, 4]          # no figure at all: its N1 students


def test_fill_catchment_default_horizon_unchanged():
    pop = pd.DataFrame({2027: [10.0], 2028: [np.nan], 2029: [8.0], 2030: [8.0]}, index=[1])
    t = P.fill_catchment(pop, pd.Series({1: 5.0}))
    assert list(t.columns) == [2027, 2028, 2029, 2030] and t.loc[1].tolist() == [10, 10, 8, 8]


def test_estimated_years():
    pop = pd.DataFrame({2027: [1.0, 2.0], 2028: [3.0, 4.0], 2029: [5.0, 6.0], 2030: [5.0, 6.0]})
    assert P.estimated_years(pop) == [2030]                          # 2030 repeats 2029
    assert P.estimated_years(pop, P.Horizon(2027)) == [2030, 2031]   # 2031 is not in the data
    assert P.estimated_years(pd.DataFrame(), P.Horizon(2027)) == [2028, 2029, 2030, 2031]


def test_default_intake_follows_nisr():
    info = pd.DataFrame({"school_code": [1, 2, 3], "district": ["A", "A", "B"]})
    catch = pd.DataFrame({2027: [10, 20, 5], 2028: [11, 21, 6], 2029: [12, 22, 7], 2030: [13, 23, 8]}, index=[1, 2, 3])
    assert P.default_intake(catch, info)["N1"].loc["A"].tolist() == [30, 32, 34, 36]
    nisr = pd.DataFrame({2027: [100.0], 2028: [110.0]}, index=["A"])
    t = P.default_intake(catch, info, nisr)["N1"]
    assert t.loc["A"].tolist() == [100, 110, 110, 110]   # years after the NISR file repeat its last year
    assert t.loc["B"].tolist() == [5, 6, 7, 8]           # a district without NISR figures: catchment totals


def test_project_on_a_later_horizon():
    roster = tiny_roster()
    h = P.Horizon(2027)
    catch = pd.DataFrame({y: [50] for y in h.future}, index=pd.Index([1], name="school_code"))
    info, schools, grades, combos = P.project(roster, catchment=catch, horizon=h)
    assert sorted(schools["year"].unique()) == h.years
    n1 = grades[grades["grade"] == "N1"].set_index("year")["students"]
    assert n1[2027] == 40 and n1[2028] == 50
    assert D.encode_projection(schools, grades, combos, h)["years"] == h.years
    cfg = D.projection_config(P.base_schools(roster), catch, h, P.default_intake(catch, info), {"N1": [2031]})
    assert cfg["baseYear"] == 2027 and cfg["years"] == h.years and cfg["catchment"]["years"] == h.future
    assert cfg["estimated"] == {"N1": [2031]} and cfg["population"]["N1"]["Gasabo"] == [50, 50, 50, 50]
