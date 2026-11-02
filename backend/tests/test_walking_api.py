"""The walking network through the API (needs the loaded database; reads and runs only, nothing is published)."""
from types import SimpleNamespace

from app.domain import walking as WK
from app.domain.walking import WalkingNetwork
from app.services import repository as R
from app.services.store import store

from .test_new_schools_api import body
from .walking_fixtures import GRID

RUN = "/api/projection/run"


def fake_run():
    return SimpleNamespace(id=999999, kind="walking_network", academic_year=None, file_name="x.osm.pbf", endpoint=None,
                           published_at=None, finished_at=None)


def test_no_network_refuses_planned_schools(viewer, monkeypatch):
    monkeypatch.setattr(store.snapshot, "network", None)
    r = viewer.client.post(RUN, json=body(name="No network"))
    assert r.status_code == 422 and r.json()["detail"] == "No walking network published yet."
    assert viewer.client.post(RUN, json={}).status_code == 200


def test_default_projection_does_not_touch_the_network(viewer, monkeypatch):
    monkeypatch.setattr(store.snapshot, "network", None)
    assert viewer.client.get("/api/projection/default").status_code == 200


def test_run_describes_the_walk(viewer, walking_grid):
    r = viewer.client.post(RUN, json=body(name="Described"))
    assert r.status_code == 200, r.text
    p = r.json()["planned"][0]
    assert p["area"]["type"] in ("Polygon", "MultiPolygon") and p["unreachable"] == {"1": 0}
    assert p["snap_km"] < 1 and p["on_main_network"] is True and p["ring"]["1"]


def test_config_says_if_a_network_is_live(viewer):
    config = viewer.client.get("/api/projection/config").json()
    assert isinstance(config["walkingNetwork"], bool)


def test_outline_failure_keeps_the_run(viewer, walking_grid, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no outline")

    monkeypatch.setattr(WK, "outline", boom)
    r = viewer.client.post(RUN, json=body(name="Outline fails"))
    assert r.status_code == 200 and r.json()["planned"][0]["area"] is None


def _load_with_live_network(monkeypatch, path):
    real = R.live_imports
    with monkeypatch.context() as m:
        m.setattr(R, "live_imports", lambda s: [*real(s), (fake_run(), None)])
        m.setattr(R, "network_file", lambda run: path)
        store.load()
        return store.snapshot.network


def test_missing_file_loads_without_a_network(viewer, monkeypatch, tmp_path):
    try:
        assert _load_with_live_network(monkeypatch, tmp_path / "gone.npz") is None
        assert store.ready
    finally:
        store.load()


def test_corrupt_file_loads_without_a_network(viewer, monkeypatch, tmp_path):
    bad = tmp_path / "bad.npz"
    bad.write_bytes(b"not a network")
    try:
        assert _load_with_live_network(monkeypatch, bad) is None
        assert store.ready
    finally:
        store.load()


def test_truncated_file_loads_without_a_network(viewer, monkeypatch, tmp_path):
    good, bad = tmp_path / "ok.npz", tmp_path / "cut.npz"
    GRID.save(good)
    bad.write_bytes(good.read_bytes()[:2000])
    try:
        assert _load_with_live_network(monkeypatch, bad) is None
        assert store.ready
    finally:
        store.load()


def test_config_is_not_cached_by_the_browser(viewer):
    r = viewer.client.get("/api/projection/config")
    assert "max-age=0" in r.headers["cache-control"]


def test_live_file_is_loaded(viewer, monkeypatch, tmp_path):
    path = tmp_path / "ok.npz"
    GRID.save(path)
    try:
        net = _load_with_live_network(monkeypatch, path)
        assert isinstance(net, WalkingNetwork) and net.nodes == GRID.nodes
        assert viewer.client.get("/api/projection/config").json()["walkingNetwork"] is True
    finally:
        store.load()
