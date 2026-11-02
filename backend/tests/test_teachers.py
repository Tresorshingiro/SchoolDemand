"""Teachers per school and level (no database needed)."""
import numpy as np
import pandas as pd

from app.domain import teachers as T
from tests.test_horizon import tiny_roster as horizon_roster


def tiny_roster() -> pd.DataFrame:
    """test_horizon's school with a combination on every class group (full-day levels are counted by combination)."""
    r = horizon_roster()
    return r.assign(combination=r["combination"].fillna("General"))


def test_to_long_skips_blank_levels():
    wide = pd.DataFrame({"school_code": [1, 2], "total_primary_teachers": [20, None],
                         "total_preprimary_teachers": [None, 4], "Prof_sec_teacher_total": [None, None]})
    t = T.to_long(wide)
    assert t.values.tolist() == [[1, "Primary", 20], [2, "Pre-Primary", 4]]


def test_per_level_marks_missing_as_nan():
    roster = tiny_roster()  # school 1 offers every level
    got = T.per_level(roster, pd.DataFrame({"school_code": [1], "level": ["Primary"], "teachers": [12]}))
    assert got[(1, "Primary")] == 12 and np.isnan(got[(1, "Pre-Primary")])
    assert T.per_level(roster, None).isna().all()  # no teachers file: no teacher data anywhere


def test_students_without_teachers_is_an_issue():
    i = T.teacher_issues(tiny_roster(), pd.DataFrame({"school_code": [1], "level": ["Primary"], "teachers": [12]}))
    assert "Students but no teachers recorded" in set(i["issue"])
    assert (i["school_code"] == 1).all()


def test_teachers_but_no_students_is_an_issue():
    roster = tiny_roster()
    no_tvet = roster[roster["level"] != "TVET"]
    i = T.teacher_issues(no_tvet, pd.DataFrame({"school_code": [1, 1], "level": ["Primary", "TVET"],
                                                "teachers": [12, 5]}))
    assert "Teachers but no students" in set(i["issue"])


def test_zero_teachers_with_students_is_an_issue():
    i = T.teacher_issues(tiny_roster(), pd.DataFrame({"school_code": [1, 1], "level": ["Primary", "Pre-Primary"],
                                                      "teachers": [12, 0]}))
    assert "Pre-Primary" in " ".join(i.loc[i["issue"] == T.NO_TEACHERS, "detail"])


def test_the_mineduc_file():
    t = T.load_teachers()
    # 3,672 schools; 15 of them record no teachers at all (no teacher data, like a school not in the file)
    assert t["school_code"].nunique() == 3657 and set(t["level"]) == set(T.LEVEL_COLUMNS.values())
