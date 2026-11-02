"""The walking network (no database or OSM download needed)."""
import math
import time

import numpy as np
import pytest

from app.domain import walking as W
from app.domain.walking import WalkingNetwork
from tests.walking_samples import line, write_pbf

LAT = -1.95
KM_LON = 111.32 * math.cos(math.radians(LAT))
KM_LAT = 110.57


def east(km: float, lon0: float = 30.0) -> float:
    return lon0 + km / KM_LON


def north(km: float, lat0: float = LAT) -> float:
    return lat0 + km / KM_LAT


def straight(km: float = 1.0, nodes: int = 11, lon0: float = 30.0) -> WalkingNetwork:
    pts = [(LAT, east(km * k / (nodes - 1), lon0)) for k in range(nodes)]
    return WalkingNetwork.from_edges(*line(pts))


def walk(net, a, b, limit=20.0):
    return net.reach(a[0], a[1], np.array([b[0]]), np.array([b[1]]), limit)


def test_distance_counts_both_snaps_and_the_network():
    net = straight()
    r = walk(net, (north(0.1), east(0)), (north(0.1), east(1)))
    assert r.km[0] == pytest.approx(1.2, rel=0.01) and r.snap_km == pytest.approx(0.1, rel=0.01)


def test_same_node_is_the_two_snaps():
    net = straight()
    r = walk(net, (north(0.1), east(0)), (north(-0.2), east(0)))
    assert r.km[0] == pytest.approx(0.3, rel=0.01)


def test_disconnected_part_is_infinite_and_not_connected():
    a, b = line([(LAT, east(0)), (LAT, east(1))]), line([(LAT, east(0, 30.2)), (LAT, east(1, 30.2))], start=2)
    net = WalkingNetwork.from_edges(a[0] + b[0], a[1] + b[1], a[2] + b[2])
    r = walk(net, (LAT, east(0)), (LAT, east(0, 30.2)))
    assert np.isinf(r.km[0]) and not r.connected[0]


def test_limit_stops_the_search():
    net = straight(km=5)
    r = walk(net, (LAT, east(0)), (LAT, east(5)), limit=2.0)
    assert np.isinf(r.km[0]) and r.connected[0]
    assert walk(net, (LAT, east(0)), (LAT, east(1)), limit=2.0).km[0] == pytest.approx(1.0, rel=0.01)


def test_a_snap_longer_than_the_limit_reaches_nothing():
    net = straight()
    r = walk(net, (north(3), east(0)), (LAT, east(0)), limit=2.0)
    assert np.isinf(r.km[0]) and r.snap_km > 2 and len(r.reached_lat) == 0


def test_missing_coordinates_are_infinite():
    r = straight().reach(LAT, east(0), np.array([float("nan"), LAT]), np.array([east(0), float("nan")]), 2.0)
    assert np.isinf(r.km).all() and not r.connected.any()


def test_length_matches_geodesic_within_one_percent():
    net = straight(km=3)
    assert net.total_km == pytest.approx(3.0, rel=0.01)


def test_save_and_load_give_the_same_distances(tmp_path):
    net = straight()
    net.save(tmp_path / "n.network.npz")
    back = WalkingNetwork.load(tmp_path / "n.network.npz")
    a, b = walk(net, (north(0.1), east(0)), (LAT, east(1))), walk(back, (north(0.1), east(0)), (LAT, east(1)))
    assert a.km[0] == pytest.approx(b.km[0], rel=1e-5) and back.nodes == net.nodes


def test_spacing_keeps_lengths():
    net = straight(km=1, nodes=101)  # nodes every 10 m
    assert net.nodes < 50 and net.total_km == pytest.approx(1.0, rel=0.01)


def test_spacing_keeps_junctions():
    pts = [(LAT, east(k * 0.01)) for k in range(101)]
    la, lo, edges = line(pts)
    la, lo = [*la, north(0.5)], [*lo, east(0.5)]    # a side path joining the middle node
    net = WalkingNetwork.from_edges(la, lo, [*edges, (50, 101)])
    r = walk(net, (north(0.5), east(0.5)), (LAT, east(0)))
    assert r.km[0] == pytest.approx(1.0, rel=0.02)


def test_a_closed_loop_without_junctions_survives():
    k = 40
    pts = [(LAT + 0.01 * math.sin(2 * math.pi * t / k), 30 + 0.01 * math.cos(2 * math.pi * t / k)) for t in range(k)]
    net = WalkingNetwork.from_edges([p[0] for p in pts], [p[1] for p in pts], [(t, (t + 1) % k) for t in range(k)])
    assert net.total_km == pytest.approx(2 * math.pi * 1.11, rel=0.02)


def test_two_routes_between_the_same_points_keep_the_shorter():
    la, lo = [LAT, LAT, north(1)], [east(0), east(1), east(0.5)]
    net = WalkingNetwork.from_edges(la, lo, [(0, 1), (1, 0), (0, 2), (2, 1)])
    assert walk(net, (LAT, east(0)), (LAT, east(1))).km[0] == pytest.approx(1.0, rel=0.01)


def _way(tags, lon0):
    return {"points": [(LAT, east(0, lon0)), (LAT, east(1, lon0))], "tags": tags}


@pytest.mark.parametrize("kind", sorted(W.SKIP_HIGHWAYS))
def test_from_pbf_leaves_out_each_skipped_kind(tmp_path, kind):
    path = write_pbf(tmp_path / "a.osm.pbf", [_way({"highway": "path"}, 30.0), _way({"highway": kind}, 30.2)])
    assert W.WalkingNetwork.from_pbf(path).total_km == pytest.approx(1.0, rel=0.01)


@pytest.mark.parametrize("tags", [{"highway": "path", "foot": "no"}, {"highway": "path", "access": "private"},
                                  {"highway": "path", "access": "no"}, {"building": "yes"}])
def test_from_pbf_leaves_out_no_foot_access(tmp_path, tags):
    path = write_pbf(tmp_path / "a.osm.pbf", [_way({"highway": "path"}, 30.0), _way(tags, 30.2)])
    assert W.WalkingNetwork.from_pbf(path).total_km == pytest.approx(1.0, rel=0.01)


@pytest.mark.parametrize("kind", ["path", "footway", "track", "residential", "unclassified", "primary"])
def test_from_pbf_keeps_walkable_kinds(tmp_path, kind):
    path = write_pbf(tmp_path / "a.osm.pbf", [_way({"highway": kind}, 30.0)])
    assert W.WalkingNetwork.from_pbf(path).total_km == pytest.approx(1.0, rel=0.01)


def test_ways_work_both_ways(tmp_path):
    path = write_pbf(tmp_path / "a.osm.pbf", [_way({"highway": "residential", "oneway": "yes"}, 30.0)])
    r = walk(W.WalkingNetwork.from_pbf(path), (LAT, east(1)), (LAT, east(0)))
    assert r.km[0] == pytest.approx(1.0, rel=0.01)


def test_from_pbf_without_walkable_ways_fails(tmp_path):
    path = write_pbf(tmp_path / "a.osm.pbf", [_way({"building": "yes"}, 30.0)])
    with pytest.raises(ValueError, match="no walkable ways"):
        W.WalkingNetwork.from_pbf(path)


def test_reached_points_are_inside_the_limit():
    net = straight(km=5, nodes=51)
    r = walk(net, (LAT, east(0)), (LAT, east(1)), limit=2.0)
    assert len(r.reached_lat) > 2
    assert (r.reached_lon <= east(2.1)).all() and r.reached_lon.max() >= east(1.8)


def _ring_points(n: int = 500):
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return LAT + 0.01 * np.sin(t), 30.0 + 0.01 * np.cos(t)


def test_outline_is_a_closed_polygon_around_the_point():
    shape = W.outline(LAT, 30.0, *_ring_points())
    ring = shape["coordinates"][0]
    assert shape["type"] == "Polygon" and ring[0] == ring[-1] and len(ring) >= 40
    assert min(p[0] for p in ring) < 30.0 < max(p[0] for p in ring)
    assert min(p[1] for p in ring) < LAT < max(p[1] for p in ring)


def test_outline_includes_the_point_when_the_walk_goes_one_way():
    la, lo = _ring_points()
    east_side = lo > 30.0
    ring = W.outline(LAT, 30.0, la[east_side], lo[east_side])["coordinates"][0]
    assert [30.0, LAT] in ring


def test_outline_needs_three_points():
    assert W.outline(LAT, 30.0, np.array([LAT, LAT]), np.array([30.1, 30.2])) is None


def test_outline_of_thousands_of_points_is_fast():
    la, lo = _ring_points(5000)
    start = time.perf_counter()
    W.outline(LAT, 30.0, la, lo)
    assert time.perf_counter() - start < 0.2


def test_coverage_shares():
    c = straight().coverage(np.array([LAT, north(0.2), north(0.8)]), np.array([east(0.5)] * 3))
    assert c["within_100m"] == pytest.approx(1 / 3) and c["within_500m"] == pytest.approx(2 / 3)
    assert c["on_main"] == 1 and c["km"] == pytest.approx(1.0, rel=0.01)


def test_coverage_ignores_nothing_when_coordinates_are_missing():
    c = straight().coverage(np.array([LAT, float("nan")]), np.array([east(0), east(0)]))
    assert c["within_100m"] == 0.5


def test_on_main_network_false_on_a_small_fragment():
    a = line([(LAT, east(k * 0.1)) for k in range(11)])
    b = line([(LAT, east(0, 30.2)), (LAT, east(0.1, 30.2))], start=11)
    net = WalkingNetwork.from_edges(a[0] + b[0], a[1] + b[1], a[2] + b[2])
    assert walk(net, (LAT, east(0)), (LAT, east(1))).on_main_network
    assert not walk(net, (LAT, east(0, 30.2)), (LAT, east(1))).on_main_network
