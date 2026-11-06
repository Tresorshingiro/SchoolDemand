"""Planned schools' walking distance through the API (needs the loaded database; the Esri Rwanda service is replaced by
a street grid, or by a stand-in that fails)."""
from app.domain import walking as WK
from app.services.store import store

from .test_new_schools_api import body
from .walking_fixtures import GRID

RUN = "/api/projection/run"
NOT_SET_UP = "Walking distance is not set up on this server."


def test_not_set_up_refuses_planned_schools(viewer, monkeypatch):
    monkeypatch.setattr(store, "walking", None)
    r = viewer.client.post(RUN, json=body(name="No service"))
    assert r.status_code == 422 and r.json()["detail"] == NOT_SET_UP
    assert viewer.client.post(RUN, json={}).status_code == 200


def test_default_projection_does_not_need_the_service(viewer, monkeypatch):
    monkeypatch.setattr(store, "walking", None)
    assert viewer.client.get("/api/projection/default").status_code == 200


def test_run_describes_the_walk(viewer, walking_grid):
    r = viewer.client.post(RUN, json=body(name="Described"))
    assert r.status_code == 200, r.text
    p = r.json()["planned"][0]
    assert p["area"]["type"] in ("Polygon", "MultiPolygon") and p["unreachable"] == {"1": 0}
    assert p["snap_km"] < 1 and p["on_main_network"] is True and p["ring"]["1"]


def test_config_says_if_planned_schools_are_available(viewer, monkeypatch):
    monkeypatch.setattr(store, "walking", GRID)
    assert viewer.client.get("/api/projection/config").json()["walkingNetwork"] is True
    monkeypatch.setattr(store, "walking", None)
    assert viewer.client.get("/api/projection/config").json()["walkingNetwork"] is False


def test_config_is_not_cached_by_the_browser(viewer):
    r = viewer.client.get("/api/projection/config")
    assert "max-age=0" in r.headers["cache-control"]


class Down:
    def reach(self, *a, **k):
        raise WK.WalkingUnavailable("The Esri Rwanda routing service could not be reached. Try again in a moment.")

    def status(self):
        return {"configured": True, "ok": False, "message": "could not be reached"}


def test_service_down_answers_503_and_the_rest_works(viewer, monkeypatch):
    monkeypatch.setattr(store, "walking", Down())
    r = viewer.client.post(RUN, json=body(name="Service down"))
    assert r.status_code == 503 and "could not be reached" in r.json()["detail"]
    assert viewer.client.post(RUN, json={}).status_code == 200


def test_admin_sees_the_service_status(client, monkeypatch):
    monkeypatch.setattr(store, "walking", None)
    r = client.get("/api/admin/data/walking").json()
    assert r["configured"] is False and r["ok"] is False and "ESRI_USERNAME" in r["message"]
    monkeypatch.setattr(store, "walking", Down())
    assert client.get("/api/admin/data/walking").json() == {"configured": True, "ok": False,
                                                            "message": "could not be reached"}


def test_viewer_cannot_see_the_service_status(viewer):
    assert viewer.client.get("/api/admin/data/walking").status_code == 403
