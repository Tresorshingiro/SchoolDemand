"""Planned new schools in the projection (no database needed)."""
import pandas as pd

from app.domain import analysis as A
from app.domain import new_schools as NS
from app.domain import projection as P
from tests.test_horizon import tiny_roster


def roster(groups) -> pd.DataFrame:
    """Rows (school_code, latitude, longitude, grade, students, room id, combination) -> a prepared roster."""
    rows = [{"school_code": c, "school_name": f"School {c}", "district": "Gasabo", "sector": "Remera", "latitude": lat,
             "longitude": lon, "grade": g, "combination": combo, "class_group": f"{g}{k}", "classroom_id": room,
             "classroom_name": room, A.STUDENTS: st, A.ROOM_ID: room}
            for k, (c, lat, lon, g, st, room, combo) in enumerate(groups)]
    return A.prepare_roster(pd.DataFrame(rows))


def ring_roster() -> pd.DataFrame:
    """School 1 (-1.950, 30.100): pre-primary feeding 138 children a year into P1, which has 3 groups of 46 in 2 rooms
    (crowded). School 2, 0.6 km away: one P1 group of 40 in its own room (not crowded). School 3, 11 km away:
    crowded like school 1."""
    g = []
    for grade in ("N1", "N2", "N3"):
        g += [(1, -1.950, 30.100, grade, 46, f"1{grade}{k}", None) for k in range(3)]
    g += [(1, -1.950, 30.100, "P1", 46, room, None) for room in ("1a", "1b", "1b")]
    g += [(2, -1.955, 30.100, "P1", 40, "2a", None)]
    g += [(3, -1.950, 30.200, "P1", 46, room, None) for room in ("3a", "3b", "3b")]
    return roster(g)


def s1_roster() -> pd.DataFrame:
    """School 1: Lower Secondary with 1 room and 3 S1 groups of 30 (2 without a room). School 9: P5 of 90, the
    district's P6 in 2027 and so its new S1 in 2028."""
    g = [(1, -1.950, 30.100, "S1", 30, "1s", None) for _ in range(3)]
    g += [(9, -1.950, 30.100, "P5", 45, f"9p{k}", None) for k in range(2)]
    return roster(g)


def nursery_roster() -> pd.DataFrame:
    """School 1: Pre-Primary with 3 groups of 46 in 1 room in each of N1-N3, and one P1 group of 40."""
    g = []
    for grade in ("N1", "N2", "N3"):
        g += [(1, -1.950, 30.100, grade, 46, f"1{grade}", None) for _ in range(3)]
    g += [(1, -1.950, 30.100, "P1", 40, "1p", None)]
    return roster(g)


def p1(grades, code, year, grade="P1"):
    g = grades[(grades.school_code == code) & (grades.grade == grade) & (grades.year == year)]
    return int(g["students"].sum())


NEAR = dict(latitude=-1.951, longitude=30.101)


def catch(h=P.DEFAULT_HORIZON, value=50):
    return pd.DataFrame({y: [value] for y in h.future}, index=pd.Index([1], name="school_code"))


def school(**kw):
    d = dict(name="New", latitude=-1.95, longitude=30.1, district="Gasabo", sector="Remera",
             classrooms=(("Primary", 12),), opening_year=2028, walking_km=2.0)
    return NS.PlannedSchool(**{**d, **kw})


def test_defaults():
    assert NS.DEFAULT_CLASSROOMS == {"Pre-Primary": 6, "Primary": 12, "Lower Secondary": 6,
                                     "Upper Secondary": 6, "TVET": 6, "Professional Education": 6}
    assert NS.DEFAULT_WALKING_KM["Primary"] == 2 and NS.DEFAULT_WALKING_KM["TVET"] == 3


def test_no_planned_schools_is_todays_projection():
    r = tiny_roster()
    a = P.project(r, catchment=catch())
    b = NS.project(r, catchment=catch())
    for x, y in zip(a, b):
        pd.testing.assert_frame_equal(x, y)


def test_with_planned_adds_an_empty_row():
    b = NS.with_planned(P.base_schools(tiny_roster()), [school()])
    assert b.info["school_code"].tolist()[-1] == -1
    assert b.students[-1].sum() == 0 and b.rooms[-1].tolist() == [0, 12, 0, 0, 0, 0]


def test_planned_school_appears_in_the_results():
    _, schools, _, _ = NS.project(tiny_roster(), planned=[school()], catchment=catch())
    s = schools[schools["school_code"] == -1]
    assert sorted(s["year"]) == [2028, 2029, 2030] and (s["rooms"] == 12).all()   # from its opening year


# ---------------------------------------------------------------- taking the extra students
C138 = catch(value=138)


def test_distance_km():
    d = NS.distance_km(-1.950, 30.100, pd.Series([-1.955, -1.950, float("nan")]).to_numpy(),
                       pd.Series([30.100, 30.200, 30.1]).to_numpy())
    assert 0.5 < d[0] < 0.6 and 11 < d[1] < 11.2 and d[2] == float("inf")


def test_takes_only_the_extra_students_of_crowded_ring_schools():
    _, _, before, _ = NS.project(ring_roster(), catchment=C138)
    _, _, after, _ = NS.project(ring_roster(), planned=[school(**NEAR)], catchment=C138)
    other = lambda g, c: g[g.school_code == c].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(other(before, 2), other(after, 2))      # not crowded: gives nothing
    pd.testing.assert_frame_equal(other(before, 3), other(after, 3))      # outside 2 km
    moved = p1(before, 1, 2028) - p1(after, 1, 2028)
    assert moved > 0 and p1(after, -1, 2028) == moved


def test_years_before_opening_unchanged():
    _, s0, _, _ = NS.project(ring_roster(), catchment=C138)
    _, s1, _, _ = NS.project(ring_roster(), planned=[school(**NEAR)], catchment=C138)
    keep = lambda s: s[(s.year < 2028) & (s.school_code > 0)].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(keep(s0), keep(s1))


def test_never_more_than_its_places():
    _, _, g, _ = NS.project(ring_roster(), planned=[school(**NEAR, classrooms=(("Primary", 6),))], catchment=C138)
    assert (g[g.school_code == -1]["students"] <= 46).all()      # 6 rooms over 6 grades = 1 room per grade
    assert g[g.school_code == -1]["students"].sum() > 0


def test_moves_up_and_keeps_taking_every_year():
    _, _, g, _ = NS.project(ring_roster(), planned=[school(**NEAR)], catchment=C138)
    assert p1(g, -1, 2028) > 0 and p1(g, -1, 2029) > 0           # takes extra P1 again in 2029
    assert p1(g, -1, 2029, "P2") >= p1(g, -1, 2028)              # its 2028 P1 moved up


def test_empty_when_no_ring_school_is_crowded():   # Review Focus 2
    _, s0, _, _ = NS.project(ring_roster(), catchment=C138)
    _, s1, _, _ = NS.project(ring_roster(), planned=[school(latitude=-2.5, longitude=29.5)], catchment=C138)
    assert (s1[s1.school_code == -1]["students"] == 0).all()
    pd.testing.assert_frame_equal(s0, s1[s1.school_code > 0].reset_index(drop=True))


def test_overlapping_rings_earlier_opening_first():   # Review Focus 3
    a = school(name="A", **NEAR, classrooms=(("Primary", 6),), opening_year=2029)
    b = school(name="B", latitude=-1.951, longitude=30.102, classrooms=(("Primary", 6),), opening_year=2028)
    _, _, before, _ = NS.project(ring_roster(), catchment=C138)
    _, _, g, _ = NS.project(ring_roster(), planned=[a, b], catchment=C138)
    assert p1(g, -2, 2028) > 0 and p1(g, -1, 2028) == 0          # B opens first
    # 2029: both P1s were taken that year, only from school 1 (school 2 is not crowded): together = what school 1 lost
    assert p1(g, -1, 2029) + p1(g, -2, 2029) == p1(before, 1, 2029) - p1(g, 1, 2029)
    assert p1(g, -1, 2029) <= 46 and p1(g, -2, 2029) <= 46       # 1 room per grade each


def test_school_without_coordinates_never_gives():    # Review Focus 4
    r = ring_roster()
    r.loc[r.school_code == 1, ["latitude", "longitude"]] = float("nan")
    _, _, g, _ = NS.project(r, planned=[school(**NEAR)], catchment=C138)
    assert g[g.school_code == -1]["students"].sum() == 0


def test_full_day_takes_whole_groups_without_a_room():
    _, _, g, _ = NS.project(s1_roster(), planned=[school(classrooms=(("Lower Secondary", 6),), walking_km=3.0)],
                            catchment=catch())
    row = g[(g.school_code == -1) & (g.grade == "S1") & (g.year == 2028)].iloc[0]
    giver = g[(g.school_code == 1) & (g.grade == "S1") & (g.year == 2028)].iloc[0]
    assert row["class_groups"] == 2 and row["students"] == 60      # the 2 groups of 30 without a room
    assert giver["class_groups"] <= giver["rooms"]                 # no S1 group left without a room


def test_moved_groups_keep_their_combination():
    # School 1: Upper Secondary with 1 room and 4 S4 groups of 30 (2 MEG, 2 PCB) — S6 in 2028
    r = roster([(1, -1.950, 30.100, "S4", 30, "1u", combo) for combo in ("MEG", "MEG", "PCB", "PCB")])
    _, _, g, c = NS.project(r, planned=[school(classrooms=(("Upper Secondary", 6),), walking_km=3.0)],
                            catchment=catch())
    new = c[(c.school_code == -1) & (c.year == 2028) & (c.grade == "S6")]
    assert new["class_groups"].sum() == 2 and new["students"].sum() == p1(g, -1, 2028, "S6") == 60
    assert set(new["combination"]) <= {"MEG", "PCB"}
    giver = c[(c.school_code == 1) & (c.year == 2028) & (c.grade == "S6")]
    assert giver["students"].sum() == p1(g, 1, 2028, "S6") == 60


def need(c, code, year, grade):
    """Rooms a grade needs on a full-day level: Σ combinations max(groups, ceil(students / 46))."""
    f = c[(c.school_code == code) & (c.year == year) & (c.grade == grade)]
    return int(sum(max(g, -(-s // 46)) for s, g in zip(f["students"], f["class_groups"])))


def short(schools, level, year):
    gap = schools[(schools.level == level) & (schools.year == year)]["gap"]
    return int(-gap[gap < 0].sum())


def test_uneven_combinations_reduce_the_shortage():   # final review #1
    # School 1, S4 in 2026 (S6 in 2028), 1 room: MEG 1 group of 60, PCB 3 groups of 20 -> needs 2 + 3 = 5 rooms
    r = roster([(1, -1.950, 30.100, "S4", 60, "1u", "MEG")]
               + [(1, -1.950, 30.100, "S4", 20, "1u", "PCB") for _ in range(3)])
    plan = [school(classrooms=(("Upper Secondary", 6),), walking_km=3.0)]
    _, s0, _, _ = NS.project(r, catchment=catch())
    _, s1, g, c = NS.project(r, planned=plan, catchment=catch())
    assert need(c, -1, 2028, "S6") <= 2                       # its 2 rooms of S6
    assert need(c, 1, 2028, "S6") == 5 - need(c, -1, 2028, "S6")
    assert short(s1, "Upper Secondary", 2028) < short(s0, "Upper Secondary", 2028)
    new = g[(g.school_code == -1) & (g.year == 2028) & (g.grade == "S6")].iloc[0]
    assert new["students"] <= 46 * new["class_groups"]


def test_many_combinations_reduce_the_shortage():     # final review #1, the reviewer's case
    # 2 rooms; S4 (S6 in 2028): MEG 2 groups of 40, PCB / HEG / MCB 1 group of 12 each -> needs 5 rooms
    rows = [(1, -1.950, 30.100, "S4", 40, f"r{k}", "MEG") for k in range(2)]
    rows += [(1, -1.950, 30.100, "S4", 12, "r0", c) for c in ("PCB", "HEG", "MCB")]
    plan = [school(classrooms=(("Upper Secondary", 6),), walking_km=3.0)]
    _, s0, _, _ = NS.project(roster(rows), catchment=catch())
    _, s1, _, c = NS.project(roster(rows), planned=plan, catchment=catch())
    assert need(c, -1, 2028, "S6") <= 2
    assert short(s1, "Upper Secondary", 2028) == short(s0, "Upper Secondary", 2028) - need(c, -1, 2028, "S6") < \
        short(s0, "Upper Secondary", 2028)


def test_moved_groups_never_exceed_46():              # final review #2
    r = roster([(1, -1.950, 30.100, "S1", 60, "1s", None) for _ in range(3)])   # S3 in 2028: 3 groups of 60, 1 room
    _, s0, _, _ = NS.project(r, catchment=catch())
    _, s1, g, _ = NS.project(r, planned=[school(classrooms=(("Lower Secondary", 6),), walking_km=3.0)], catchment=catch())
    new = g[(g.school_code == -1) & (g.year == 2028) & (g.grade == "S3")].iloc[0]
    assert new["students"] > 0 and new["students"] <= 46 * new["class_groups"] and new["required"] <= 2
    assert short(s1, "Lower Secondary", 2028) < short(s0, "Lower Secondary", 2028)


def test_not_in_the_figures_before_it_opens():         # final review #3
    _, s0, g0, _ = NS.project(ring_roster(), catchment=C138)
    _, s1, g1, _ = NS.project(ring_roster(), planned=[school(**NEAR)], catchment=C138)
    early = lambda s: s[s.year < 2028].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(early(s0), early(s1))
    pd.testing.assert_frame_equal(early(g0), early(g1))
    assert (s1[s1.school_code == -1]["year"] >= 2028).all()


def test_a_school_that_is_not_short_gives_nothing():  # final review #7 (only crowded schools give)
    # 2027: P2 47 students and P3 40, one room each -> required 2 = rooms (gap 0), though P2 has 1 student over 46
    r = roster([(4, -1.950, 30.100, "P1", 47, "4a", None), (4, -1.950, 30.100, "P2", 40, "4b", None)])
    _, s, g, _ = NS.project(r, planned=[school(opening_year=2027)], catchment=catch())
    gap = s[(s.school_code == 4) & (s.year == 2027)]["gap"].iloc[0]
    assert gap == 0 and g[g.school_code == -1]["students"].sum() == 0


def test_pre_primary_and_primary_together_feeds_its_own_p1():
    s = school(classrooms=(("Pre-Primary", 6), ("Primary", 12)), **NEAR)
    _, _, g, _ = NS.project(nursery_roster(), planned=[s], catchment=C138)
    n3_2028 = p1(g, -1, 2028, "N3")
    assert n3_2028 > 0 and p1(g, -1, 2029) >= n3_2028           # its own N3 moved up to its own P1


def test_rings_lists_the_nearby_schools_of_the_level():
    b = NS.with_planned(P.base_schools(ring_roster()), [school(**NEAR)])
    assert NS.rings(b, [school(**NEAR)]) == [{"Primary": [1, 2]}]
