"""Students per classroom and the repetition / dropout switches in the engine (no database needed)."""
import math
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from app.domain import analysis as A
from app.domain import dashboard as D
from app.domain import new_schools as NS
from app.domain import projection as P
from app.domain import rates as RT
from tests.test_new_schools import C138, catch, nursery_roster, ring_roster, roster, s1_roster, school
from tests.walking_samples import grid

RATES = RT.FlowRates("2023/24", pd.DataFrame({"repetition": [0.2], "dropout": [0.1]}, index=[RT.NATIONAL]))


def s1_full() -> pd.DataFrame:
    """Three S1 groups of 46 students, each in its own room."""
    return roster([(1, -1.95, 30.1, "S1", 46, f"r{k}", "OL") for k in range(3)])


def level(schools, label, year):
    return schools[(schools["level"] == label) & (schools["year"] == year)]


def test_defaults_are_identical():
    a = P.project(nursery_roster(), catchment=C138, rates=RATES)
    b = P.project(nursery_roster(), catchment=C138, rates=RATES, capacity=46)
    for x, y in zip(a, b):
        pd.testing.assert_frame_equal(x, y)


def test_pre_primary_required_follows_capacity():
    _, schools, _, _ = P.project(nursery_roster(), catchment=C138, rates=RT.ZERO, capacity=40)
    row = level(schools, "Pre-Primary", 2026).iloc[0]
    assert row["students"] == 414 and row["required"] == math.ceil(414 / 40) and row["gap"] == row["rooms"] - row["required"]


def test_grade_rows_follow_capacity():
    _, _, grades, _ = P.project(nursery_roster(), catchment=C138, rates=RT.ZERO, capacity=40)
    g = grades[(grades["grade"] == "N1") & (grades["year"] == 2026)].iloc[0]
    assert g["required"] == math.ceil(138 / 40)


def test_full_day_streams_hold_the_requirement():
    args = dict(catchment=catch(), rates=RT.ZERO)
    high = level(P.project(s1_roster(), capacity=60, **args)[1], "Lower Secondary", 2026)
    default = level(P.project(s1_roster(), **args)[1], "Lower Secondary", 2026)
    assert high["required"].tolist() == default["required"].tolist() == [3]   # 3 streams, each needs a room


def test_full_day_required_rises_when_capacity_falls():
    _, schools, _, _ = P.project(s1_full(), catchment=catch(), rates=RT.ZERO, capacity=20)
    assert level(schools, "Lower Secondary", 2026)["required"].tolist() == [7]   # MAX(3, CEILING(138 / 20))


def test_streams_do_not_change_with_capacity():
    runs = [P.project(nursery_roster(), catchment=C138, rates=RATES, capacity=c)[1] for c in (20, 46, 100)]
    assert runs[0]["class_groups"].tolist() == runs[1]["class_groups"].tolist() == runs[2]["class_groups"].tolist()


def test_capacity_does_not_touch_globals():
    before = dict(P.CAPACITY), dict(A.CAPACITY)

    def run(c):
        return P.project(nursery_roster(), catchment=C138, rates=RATES, capacity=c)[1]

    alone = {c: run(c)["required"].tolist() for c in (20, 100)}
    with ThreadPoolExecutor(4) as pool:
        together = list(pool.map(run, [20, 100, 20, 100]))
    assert [t["required"].tolist() for t in together] == [alone[20], alone[100], alone[20], alone[100]]
    assert (dict(P.CAPACITY), dict(A.CAPACITY)) == before


def test_planned_school_streams_use_capacity_every_year():
    _, _, grades, _ = NS.project(ring_roster(), planned=[school(opening_year=2027)], catchment=C138, rates=RT.ZERO,
                                 capacity=30, network=grid())
    new = grades[(grades["school_code"] == -1) & (grades["students"] > 0)]
    assert len(new) > 1 and new["year"].nunique() > 1
    assert (new["class_groups"] == (new["students"] / 30).map(math.ceil)).all()


def test_existing_school_streams_keep_the_default_fallback_with_planned_schools_off():
    a = NS.project(ring_roster(), catchment=C138, rates=RT.ZERO, capacity=30)[1]
    b = NS.project(ring_roster(), catchment=C138, rates=RT.ZERO)[1]
    assert a["class_groups"].tolist() == b["class_groups"].tolist()


def test_switched_off_rates():
    off = RT.switched(RATES, repetition=False)
    assert off.table["repetition"].tolist() == [0] and off.table["dropout"].tolist() == [0.1]
    assert RT.switched(RATES, dropout=False).table["dropout"].tolist() == [0]
    assert RATES.table["repetition"].tolist() == [0.2]   # the original stays as it was
    assert off.school_year == RATES.school_year


def test_both_off_equals_no_rates():
    a = P.project(nursery_roster(), catchment=C138, rates=RT.switched(RATES, repetition=False, dropout=False))
    b = P.project(nursery_roster(), catchment=C138, rates=RT.ZERO)
    for x, y in zip(a, b):
        pd.testing.assert_frame_equal(x, y)


def test_both_off_moves_a_cohort_up_whole():
    _, _, grades, _ = P.project(nursery_roster(), catchment=C138,
                                rates=RT.switched(RATES, repetition=False, dropout=False))
    n1 = grades[(grades["grade"] == "N1") & (grades["year"] == 2026)]["students"].sum()
    n2 = grades[(grades["grade"] == "N2") & (grades["year"] == 2027)]["students"].sum()
    assert n1 == n2


def test_actual_year_ignores_switches():
    on = P.project(nursery_roster(), catchment=C138, rates=RATES)[1]
    off = P.project(nursery_roster(), catchment=C138, rates=RT.switched(RATES, repetition=False))[1]
    a, b = on[on["year"] == 2026], off[off["year"] == 2026]
    pd.testing.assert_frame_equal(a, b)
    assert not on[on["year"] == 2027]["students"].equals(off[off["year"] == 2027]["students"])


def test_school_table_capacity():
    t = A.school_table(nursery_roster(), capacity=40)
    row = t[t["level"] == "Pre-Primary"].iloc[0]
    assert row["required"] == math.ceil(414 / 40) and row["gap"] == row["available"] - row["required"]
    g = A.grade_table(s1_full(), capacity=20)
    assert g["required"].tolist() == [7]


def test_dashboard_dataset_capacity():
    data = D.current(nursery_roster(), source="test", capacity=40)
    pre = next(r for r in data["school_levels"] if r["l"] == 0)
    assert pre["r"] == math.ceil(414 / 40)
    assert {lv["capacity"] for lv in data["meta"]["levels"]} == {40}
