"""Planned new schools through the API (needs the database, like test_api.py)."""
import pytest

GATENGA = {"latitude": -1.998765, "longitude": 30.082429}   # inside Gatenga sector, Kicukiro


def body(**kw):
    s = {"name": "New school", **GATENGA, "levels": {"PRI": 12}, "opening_year": 2028, "walking_km": 2}
    return {"schools": [{**s, **kw}]}


def test_run_with_a_planned_school(viewer):
    r = viewer.client.post("/api/projection/run", json=body())
    assert r.status_code == 200, r.text
    p = r.json()["planned"][0]
    assert p["c"] == -1 and p["d"] == "Kicukiro" and p["s"] == "Gatenga" and p["opening"] == 2028
    assert p["levels"] == [1] and p["classrooms"] == [12] and p["ring"]["1"]
    assert any(row[1] == -1 for row in r.json()["schools"])


def test_off_is_the_default_run(viewer):          # Review Focus 5
    viewer.client.post("/api/projection/run", json=body())
    off = viewer.client.post("/api/projection/run", json={"schools": []}).json()
    default = viewer.client.get("/api/projection/default").json()
    assert off == default and default["planned"] == []


def test_outside_rwanda(viewer):                  # Review Focus 1
    r = viewer.client.post("/api/projection/run", json=body(latitude=-2.2, longitude=29.2))
    assert r.status_code == 422 and "outside Rwanda" in r.json()["detail"]


@pytest.mark.parametrize("levels", [{"PRI": 12, "LSE": 6}, {}, {"XYZ": 3}, {"PRI": 0}])
def test_level_rules(viewer, levels):
    assert viewer.client.post("/api/projection/run", json=body(levels=levels)).status_code == 422


def test_pre_primary_and_primary_together(viewer):
    r = viewer.client.post("/api/projection/run", json=body(levels={"NUR": 6, "PRI": 12}))
    assert r.status_code == 200 and r.json()["planned"][0]["levels"] == [0, 1]


def test_opening_year_inside_the_horizon(viewer):
    r = viewer.client.post("/api/projection/run", json=body(opening_year=2026))
    assert r.status_code == 422 and "2027" in r.json()["detail"]
