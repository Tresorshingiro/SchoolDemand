"""Planned schools reach schools on foot, not in a straight line (no database needed)."""
import numpy as np
import pandas as pd
import pytest

from app.domain import new_schools as NS
from app.domain import projection as P
from app.domain import rates as RT
from tests.test_new_schools import C138, catch, ring_roster, roster, school
from tests.walking_samples import GraphWalking as WalkingNetwork
from tests.walking_samples import line

LAT, LON = -1.95, 30.10
KM_LAT, KM_LON = 110.57, 111.26


def at(north_km: float, east_km: float) -> tuple[float, float]:
    return LAT + north_km / KM_LAT, LON + east_km / KM_LON


def two_schools(p2: tuple[float, float]):
    """School 1 at the planned point; school 2 elsewhere; both Primary."""
    return roster([(1, LAT, LON, "P1", 46, "1a", None), (2, p2[0], p2[1], "P1", 46, "2a", None),
                   (2, p2[0], p2[1], "P1", 46, "2a", None)])


def u_path() -> WalkingNetwork:
    """A path from the planned point 0.75 km north, 1.5 km east and 0.75 km south: 3 km on foot, 1.5 km in a line."""
    pts = [at(0, 0), at(0.75, 0), at(0.75, 1.5), at(0, 1.5)]
    return WalkingNetwork.from_edges(*line(pts))


def base_and_planned(r, net_school, km=2.0):
    planned = [school(opening_year=2027, walking_km=km, classrooms=(("Primary", 12),))]
    return NS.with_planned(P.base_schools(r), planned), planned


def test_a_school_near_in_a_line_but_far_on_foot_is_out():
    r = two_schools(at(0, 1.5))
    b, planned = base_and_planned(r, None, km=2.0)
    assert NS.rings(b, planned, u_path())[0]["Primary"] == [1]
    b, planned = base_and_planned(r, None, km=4.0)
    assert NS.rings(b, planned, u_path())[0]["Primary"] == [1, 2]


def fragments() -> WalkingNetwork:
    a = line([at(0, 0), at(0, 0.3)])
    c = line([at(0, 1.0), at(0, 1.3)], start=2)
    return WalkingNetwork.from_edges(a[0] + c[0], a[1] + c[1], a[2] + c[2])


def test_a_separate_part_counts_as_unreachable():
    r = two_schools(at(0, 1.0))
    b, planned = base_and_planned(r, None)
    net = fragments()
    assert NS.rings(b, planned, net)[0]["Primary"] == [1]
    assert NS.unreachable(b, planned, NS.reach_table(b, planned, net))[0] == {"Primary": 1}


def test_connected_but_too_far_is_not_unreachable():
    r = two_schools(at(0, 1.5))
    b, planned = base_and_planned(r, None)
    assert NS.unreachable(b, planned, NS.reach_table(b, planned, u_path()))[0] == {"Primary": 0}


def test_no_network_raises_with_planned_schools():
    with pytest.raises(NS.NoWalkingNetwork):
        NS.project(ring_roster(), planned=[school()], catchment=C138, rates=RT.ZERO)


def test_no_network_needed_without_planned_schools():
    r = ring_roster()
    for x, y in zip(NS.project(r, catchment=C138, rates=RT.ZERO), P.project(r, catchment=C138, rates=RT.ZERO)):
        pd.testing.assert_frame_equal(x, y)


def test_later_planned_school_can_take_from_an_earlier_one():
    r = two_schools(at(0, 0.2))
    net = WalkingNetwork.from_edges(*line([at(0, 0), at(0, 2)]))
    planned = [school(name="First", opening_year=2027, classrooms=(("Primary", 1),)),
               school(name="Second", opening_year=2028, latitude=at(0, 0.5)[0], longitude=at(0, 0.5)[1],
                      classrooms=(("Primary", 12),))]
    b = NS.with_planned(P.base_schools(r), planned)
    reaches = NS.reach_table(b, planned, net)
    row_first = len(b.info) - 2
    assert np.isfinite(reaches[1].km[row_first])   # the first planned school is within the second's walking distance


def test_distances_calculated_once_per_run(monkeypatch):
    net = WalkingNetwork.from_edges(*line([at(0, 0), at(0, 2)]))
    calls = []
    real = net.reach
    monkeypatch.setattr(net, "reach", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    NS.project(ring_roster(), planned=[school(opening_year=2027), school(opening_year=2028)], catchment=C138,
               rates=RT.ZERO, network=net)
    assert len(calls) == 2
