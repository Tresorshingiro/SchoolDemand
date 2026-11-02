"""The walking network as a kind of upload: rules and checks (no database writes)."""
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException

from app.domain import projection as P
from app.imports import service as S
from app.imports.checks import CheckContext, check_walking_network
from tests.walking_samples import grid, write_pbf

LAT, LON = -1.95, 30.10
KM = 1 / 111.26   # degrees of longitude per km, about


def ctx(points: list[tuple[float, float]] | None, network_km: float | None = None) -> CheckContext:
    roster = pd.DataFrame({"school_code": range(1, len(points or []) + 1), "school_name": "S",
                           "latitude": [p[0] for p in points or []], "longitude": [p[1] for p in points or []]})
    return CheckContext(P.DEFAULT_HORIZON, set(), [], [2026] if points else [], set(), None, lambda y: roster, network_km)


def path_km(start_km: float, end_km: float) -> dict:
    """A path along the latitude, with a point every 50 m."""
    k = round((end_km - start_km) / 0.05)
    return {"points": [(LAT, LON + (start_km + 0.05 * t) * KM) for t in range(k + 1)], "tags": {"highway": "path"}}


def pbf(tmp_path, ways=None):
    path = tmp_path / "rwanda.osm.pbf"
    path.unlink(missing_ok=True)
    return write_pbf(path, ways or [path_km(0, 2)])


def on_path(k: int = 10) -> list[tuple[float, float]]:
    return [(LAT, LON + 2 * KM * t / k) for t in range(k)]


def codes(report: dict) -> set[str]:
    return {e["code"] for e in report}


def create(**kw):
    return S.create_upload(None, academic_year=None, user=None, **kw)


@pytest.mark.parametrize("name", ["rwanda.xlsx", "rwanda.csv", "rwanda.pbf"])
def test_this_kind_takes_only_osm_pbf(name):
    with pytest.raises(HTTPException) as e:
        create(kind="walking_network", file_name=name, content=b"x")
    assert e.value.status_code == 422 and ".osm.pbf" in e.value.detail


def test_other_kinds_still_refuse_pbf():
    with pytest.raises(HTTPException) as e:
        create(kind="catchment", file_name="a.osm.pbf", content=b"x")
    assert e.value.detail == "Upload an .xlsx or .csv file."


def test_size_limits():
    assert S.max_bytes("walking_network") == 200 * 1024 * 1024
    assert S.max_bytes("catchment") == 50 * 1024 * 1024
    with pytest.raises(HTTPException) as e:
        create(kind="walking_network", file_name="a.osm.pbf", content=b"a" * (S.max_bytes("walking_network") + 1))
    assert e.value.status_code == 413 and "200 MB" in e.value.detail


def test_no_walkable_ways_is_an_error(tmp_path):
    path = pbf(tmp_path, [{"points": [(LAT, LON), (LAT, LON + KM)], "tags": {"building": "yes"}}])
    parsed, rep = check_walking_network(path, None, ctx(on_path()))
    assert parsed is None and codes(rep.errors) == {"no_ways"}


def test_unreadable_file_is_an_error(tmp_path):
    path = tmp_path / "bad.osm.pbf"
    path.write_bytes(b"not a pbf")
    parsed, rep = check_walking_network(path, None, ctx(on_path()))
    assert parsed is None and codes(rep.errors) == {"unreadable"}


def test_under_90_percent_within_500m_is_an_error(tmp_path):
    far = (LAT + 0.1, LON)
    parsed, rep = check_walking_network(pbf(tmp_path), None, ctx([*on_path(8), far, far]))  # 80%
    assert parsed is None and "coverage" in codes(rep.errors)


def test_exactly_90_percent_passes(tmp_path):
    parsed, rep = check_walking_network(pbf(tmp_path), None, ctx([*on_path(9), (LAT + 0.1, LON)]))
    assert parsed is not None and not rep.errors


def test_under_90_percent_on_main_part_is_an_error(tmp_path):
    ways = [path_km(0, 2), path_km(5, 6)]
    parsed, rep = check_walking_network(pbf(tmp_path, ways), None, ctx([*on_path(8), (LAT, LON + 5 * KM), (LAT, LON + 6 * KM)]))
    assert parsed is None and "connected" in codes(rep.errors)


def test_warnings_list_far_and_disconnected_schools(tmp_path):
    ways = [path_km(0, 2), path_km(5, 6)]
    points =[*on_path(18), (LAT + 0.1, LON), (LAT, LON + 5 * KM)]
    parsed, rep = check_walking_network(pbf(tmp_path, ways), None, ctx(points))
    assert parsed is not None and {"far", "disconnected"} <= codes(rep.warnings)
    far = next(w for w in rep.warnings if w["code"] == "far")
    assert far["count"] == 1 and far["rows"][0]["school_code"] == 19


def test_shrunk_network_warns(tmp_path):
    _, rep = check_walking_network(pbf(tmp_path), None, ctx(on_path(), network_km=10))
    assert "shrunk" in codes(rep.warnings)
    _, rep = check_walking_network(pbf(tmp_path), None, ctx(on_path(), network_km=2.2))
    assert "shrunk" not in codes(rep.warnings)


def test_summary_fields(tmp_path):
    _, rep = check_walking_network(pbf(tmp_path), None, ctx(on_path()))
    assert rep.summary["km"] == pytest.approx(2, rel=0.02)
    assert rep.summary["within_100m"] == 1 and rep.summary["within_500m"] == 1 and rep.summary["on_main"] == 1


def test_works_before_any_school_data(tmp_path):
    parsed, rep = check_walking_network(pbf(tmp_path), None, ctx(None))
    assert parsed is not None and not rep.errors


def test_cannot_be_withdrawn():
    with pytest.raises(HTTPException) as e:
        S.check_withdraw(None, SimpleNamespace(is_live=True, kind="walking_network"))
    assert e.value.status_code == 409 and "Publish another" in e.value.detail


def test_same_file_allowed_when_network_file_is_lost(tmp_path, monkeypatch):
    live = SimpleNamespace(id=7, kind="walking_network", file_sha256="abc")
    monkeypatch.setattr(S, "network_path", lambda run: tmp_path / "gone.npz")
    assert S.already_live(live, "abc") is False
    grid(step=0.02).save(tmp_path / "gone.npz")
    assert S.already_live(live, "abc") is True
    assert S.already_live(live, "other") is False


def test_same_file_allowed_when_network_file_is_damaged(tmp_path, monkeypatch):
    live = SimpleNamespace(id=7, kind="walking_network", file_sha256="abc")
    good, bad = tmp_path / "ok.npz", tmp_path / "cut.npz"
    grid(step=0.02).save(good)
    bad.write_bytes(good.read_bytes()[:500])
    monkeypatch.setattr(S, "network_path", lambda run: bad)
    assert S.already_live(live, "abc") is False and S.network_usable(live) is False
    monkeypatch.setattr(S, "network_path", lambda run: good)
    assert S.already_live(live, "abc") is True and S.network_usable(live) is True


def test_publish_rebuilds_a_damaged_network_file(tmp_path, monkeypatch):
    bad = tmp_path / "cut.npz"
    bad.write_bytes(b"damaged")
    run = SimpleNamespace(id=7, kind="walking_network")
    monkeypatch.setattr(S, "network_path", lambda r: bad)
    rebuilt = grid(step=0.02)
    monkeypatch.setattr(S, "_check", lambda s, r: (rebuilt, {"errors": []}, None, 1))
    assert S._parsed(None, run) is rebuilt
    assert S.network_usable(run)


def test_other_kinds_same_file_is_already_live():
    assert S.already_live(SimpleNamespace(id=7, kind="catchment", file_sha256="abc"), "abc") is True
    assert S.already_live(None, "abc") is False


def test_consequence_text():
    assert S.consequence(None, SimpleNamespace(kind="walking_network")) == (
        "Replaces the walking network: the schools each planned school can take students from follow it.")
