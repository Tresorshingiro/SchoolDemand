"""Students per classroom and the switches through the API (needs the loaded database; reads and runs only)."""
import inspect

import pytest

from app.services.store import Store, store

RUN = "/api/projection/run"
PRE_PRIMARY = 0
GATENGA = {"name": "New school", "latitude": -1.998765, "longitude": 30.082429, "levels": {"PRI": 12},
           "opening_year": 2027, "walking_km": 2}


def run(viewer, **body) -> dict:
    r = viewer.client.post(RUN, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def rows(result: dict, year: int, level: int | None = None) -> list:
    return [x for x in result["schools"] if x[0] == year and (level is None or x[2] == level)]


@pytest.mark.parametrize("bad", [19, 101, 46.5, "x"])
def test_capacity_range(viewer, bad):
    assert viewer.client.post(RUN, json={"capacity": bad}).status_code == 422


def test_defaults_share_the_default_run(viewer):
    explicit = viewer.client.post(RUN, json={"capacity": 46, "repetition": True, "dropout": True})
    assert explicit.content == viewer.client.get("/api/projection/default").content


def test_capacity_changes_the_gap(viewer):
    a, b = run(viewer), run(viewer, capacity=30)
    x, y = rows(a, 2026, PRE_PRIMARY), rows(b, 2026, PRE_PRIMARY)
    assert sum(r[3] for r in x) == sum(r[3] for r in y)          # students
    assert sum(r[7] for r in y) > sum(r[7] for r in x)           # required


def test_switch_changes_projected_only(viewer):
    on, off = run(viewer), run(viewer, repetition=False)
    assert rows(on, 2026) == rows(off, 2026)
    assert rows(on, 2027) != rows(off, 2027)


def test_values_are_cached_apart(viewer):
    first, second, third = run(viewer, capacity=40), run(viewer, capacity=50), run(viewer, capacity=40)
    assert first == third and first != second


def test_planned_run_takes_the_values(viewer, walking_grid):
    a, b = run(viewer, schools=[GATENGA]), run(viewer, schools=[GATENGA], capacity=30)
    assert rows(a, 2027) != rows(b, 2027)


def test_year_data_capacity(viewer):
    a = viewer.client.get("/api/school-levels").json()
    b = viewer.client.get("/api/school-levels", params={"capacity": 30}).json()
    assert [r["st"] for r in a] == [r["st"] for r in b]
    assert sum(r["r"] for r in b) > sum(r["r"] for r in a)
    g = viewer.client.get("/api/grades", params={"capacity": 30}).json()
    assert sum(r[6] for r in g) > sum(r[6] for r in viewer.client.get("/api/grades").json())
    assert viewer.client.get("/api/school-levels", params={"capacity": 19}).status_code == 422


def test_reload_drops_cached_runs(viewer):
    run(viewer, capacity=33)
    viewer.client.get("/api/school-levels", params={"capacity": 33})
    assert len(store._runs) > 1 and store._year_runs
    store.load()
    assert len(store._runs) == 1 and not store._year_runs


def test_saved_plan_summaries_use_the_defaults():
    assert list(inspect.signature(Store.frames).parameters) == ["self", "intake", "planned"]
