"""The Esri Rwanda walking service client (domain/walking.py), against a fake ArcGIS server (no network access)."""
import json
import math
import time
from types import SimpleNamespace

import numpy as np
import pytest

from app.domain import walking as W

ROUTING = "https://esri.test/server/rest/services/Routing/NetworkAnalysis/NAServer"
PORTAL = "https://esri.test/portal"
LAT, LON = -1.95, 30.10
KM_LAT = 110.57
KM_LON = 111.32 * math.cos(math.radians(LAT))


def east(km: float) -> float:
    return LON + km / KM_LON


WALK_MODE = {"name": "Walking", "type": "WALK", "impedanceAttributeName": "Length", "distanceAttributeName": "Length",
             "timeAttributeName": "DriveTime", "restrictionAttributeNames": ["Oneway"],
             "attributeParameterValues": [{"attributeName": "Oneway", "parameterName": "Restriction Usage",
                                           "value": "Prohibited"}]}
DESCRIPTION = {"supportedTravelModes": [{"name": "Time", "type": "AUTOMOBILE"}, WALK_MODE],
               "networkDataset": {"networkAttributes": [{"name": "Length", "units": "esriNAUMeters",
                                                         "usageType": "esriNAUTCost"}]}}
SQUARE = [[[30.0, -1.9], [30.1, -1.9], [30.1, -2.0], [30.0, -2.0], [30.0, -1.9]]]  # clockwise: an Esri outer ring


class FakeEsri:
    """Answers like the Esri Rwanda services. Distance along the network = 1.5 x the straight line (metres); `no_route`
    = target positions (of the request) with no route; `snap` = metres to the network of every point."""

    def __init__(self, *, no_route=(), unlocated=(), snap=0.0, origin_snap=0.0, origin_status=0, area=SQUARE):
        self.calls: list[tuple[str, dict]] = []
        self.no_route, self.unlocated = set(no_route), set(unlocated)
        self.snap, self.origin_snap, self.origin_status, self.area = snap, origin_snap, origin_status, area
        self.tokens = 0
        self.expire_next = 0  # answer "Invalid token" to this many routing requests
        self.fail: str | None = None  # a path that answers an error

    def __call__(self, url: str, data: dict) -> dict:
        self.calls.append((url, data))
        if url.endswith("/generateToken"):
            self.tokens += 1
            return {"token": f"token-{self.tokens}", "expires": (time.time() + 3600) * 1000}
        assert data["token"].startswith("token-")
        if self.expire_next:
            self.expire_next -= 1
            return {"error": {"code": 498, "message": "Invalid token.", "details": []}}
        path = url.removeprefix(ROUTING + "/")
        if self.fail and path == self.fail:
            return {"error": {"code": 400, "message": "Unable to complete operation.", "details": ["Solver failed."]}}
        if path == "OriginDestinationCostMatrix":
            return DESCRIPTION
        if path.endswith("solveODCostMatrix"):
            assert json.loads(data["travelMode"])["restrictionAttributeNames"] == []
            (o,) = json.loads(data["origins"])["features"]
            dests = json.loads(data["destinations"])["features"]
            row = {}
            for k, f in enumerate(dests, start=1):
                if k - 1 in self.no_route or k - 1 in self.unlocated:
                    continue
                g = f["geometry"]
                d = math.hypot((g["x"] - o["geometry"]["x"]) * KM_LON, (g["y"] - o["geometry"]["y"]) * KM_LAT) * 1000
                row[str(k)] = [1.5 * d]
            return {"odCostMatrix": {"costAttributeNames": ["Length"], "1": row},
                    "origins": {"features": [{"attributes": {"ObjectID": 1, "Name": "0", "Status": self.origin_status,
                                                             "DistanceToNetworkInMeters": self.origin_snap}}]},
                    "destinations": {"features": [
                        {"attributes": {"ObjectID": k, "Name": f["attributes"]["Name"],
                                        "Status": 1 if k - 1 in self.unlocated else 0,
                                        "DistanceToNetworkInMeters": self.origin_snap if k == 1 else self.snap}}
                        for k, f in enumerate(dests, start=1)]}}
        if path.endswith("solveServiceArea"):
            return {"saPolygons": {"features": [{"geometry": {"rings": self.area}}] if self.area else []}}
        raise AssertionError(path)

    def solves(self, kind: str = "solveODCostMatrix") -> list[dict]:
        return [d for u, d in self.calls if u.endswith(kind)]


def service(fake: FakeEsri, **k) -> W.EsriWalking:
    return W.EsriWalking(ROUTING, portal_url=PORTAL, username="svc", password="secret", http=fake, **k)


def walk(w, targets_km: list[float], limit=2.0):
    """Targets east of the point, at these straight-line distances (km)."""
    lons = np.array([east(k) for k in targets_km])
    return w.reach(LAT, LON, np.full(len(lons), LAT), lons, limit)


def test_distance_is_both_snaps_and_the_network():
    fake = FakeEsri(snap=100, origin_snap=50)
    r = walk(service(fake), [1.0])
    assert r.km[0] == pytest.approx((50 + 1500 + 100) / 1000, rel=1e-3) and r.snap_km == pytest.approx(0.05)


def test_beyond_the_limit_on_foot_is_out_but_connected():
    r = walk(service(FakeEsri()), [1.0, 1.6], limit=2.0)  # 1.5 and 2.4 km on foot
    assert r.km[0] == pytest.approx(1.5, rel=1e-3) and np.isinf(r.km[1]) and r.connected.all()


def test_only_schools_within_the_distance_in_a_straight_line_are_asked_about():
    fake = FakeEsri()
    r = walk(service(fake), [0.5, 2.5, 10.0], limit=2.0)
    (solve,) = fake.solves()
    assert len(json.loads(solve["destinations"])["features"]) == 2  # the point itself + the school at 0.5 km
    assert np.isinf(r.km[1:]).all() and r.connected.all()  # far ones: not asked, not reported as cut off


def test_no_route_or_not_placed_is_not_connected():
    fake = FakeEsri(no_route={1}, unlocated={2})  # request positions: 0 = the point, 1 and 2 = the two schools
    r = walk(service(fake), [0.5, 0.7])
    assert np.isinf(r.km).all() and not r.connected.any()


def test_point_the_service_cannot_place_reaches_nothing():
    r = walk(service(FakeEsri(origin_status=1)), [0.5])
    assert np.isinf(r.km[0]) and r.on_main_network is False and r.area is None


def test_a_walk_to_the_network_longer_than_the_limit_reaches_nothing():
    fake = FakeEsri(origin_snap=2500)
    r = walk(service(fake), [0.1], limit=2.0)
    assert np.isinf(r.km[0]) and r.snap_km == pytest.approx(2.5) and r.area is None and not fake.solves("solveServiceArea")


def test_missing_coordinates_are_infinite_and_not_asked_about():
    fake = FakeEsri()
    r = service(fake).reach(LAT, LON, np.array([np.nan, LAT]), np.array([east(0.5), np.nan]), 2.0)
    assert np.isinf(r.km).all() and not r.connected.any()
    assert len(json.loads(fake.solves()[0]["destinations"])["features"]) == 1


def test_one_way_restriction_is_removed_and_units_read():
    mode, attr, per_unit = W.walking_mode(DESCRIPTION, "walking")
    assert mode["restrictionAttributeNames"] == [] and mode["attributeParameterValues"] == []
    assert (attr, per_unit) == ("Length", 1.0)
    km = {**DESCRIPTION, "networkDataset": {"networkAttributes": [{"name": "Length", "units": "esriNAUKilometers"}]}}
    assert W.walking_mode(km, "Walking")[2] == 1000.0


def test_no_walking_mode_is_unavailable():
    fake = FakeEsri()
    w = service(fake, travel_mode="Hover")
    with pytest.raises(W.WalkingUnavailable, match="no usable walking mode"):
        walk(w, [0.5])


def test_area_goes_to_the_limit_less_the_walk_to_the_network():
    fake = FakeEsri(origin_snap=300)
    r = walk(service(fake), [0.5], limit=2.0)
    (sa,) = fake.solves("solveServiceArea")
    assert float(sa["defaultBreaks"]) == pytest.approx(1700) and r.area["type"] == "Polygon"


def test_area_failure_keeps_the_walk_and_is_tried_again():
    fake = FakeEsri()
    fake.fail = "ServiceArea/solveServiceArea"
    w = service(fake)
    r = walk(w, [0.5])
    assert r.area is None and np.isfinite(r.km[0])
    fake.fail = None
    assert walk(w, [0.5]).area is not None  # not kept in the cache without its area


def test_walks_are_cached():
    fake = FakeEsri()
    w = service(fake)
    a, b = walk(w, [0.5, 1.0]), walk(w, [0.5, 1.0])
    assert len(fake.solves()) == 1 and np.array_equal(a.km, b.km)
    walk(w, [0.5, 1.0], limit=3.0)  # another distance: asked again
    assert len(fake.solves()) == 2


def test_cache_is_bounded():
    fake = FakeEsri()
    w = service(fake, cache_size=2)
    for limit in (1.0, 2.0, 3.0):
        walk(w, [0.5], limit=limit)
    walk(w, [0.5], limit=1.0)  # the oldest was dropped
    assert len(fake.solves()) == 4


def test_many_schools_are_sent_in_batches():
    fake = FakeEsri()
    targets = [0.001 * k for k in range(1, 1500)]  # up to 1.5 km in a line, 2.25 km on foot
    r = walk(service(fake), targets, limit=2.5)
    assert len(fake.solves()) == 2 and np.isfinite(r.km).sum() == len(targets)


def test_token_is_made_once_and_renewed_when_refused():
    fake = FakeEsri()
    w = service(fake)
    walk(w, [0.5])
    walk(w, [0.6])
    assert fake.tokens == 1
    fake.expire_next = 1
    walk(w, [0.7])
    assert fake.tokens == 2


def test_fixed_token_needs_no_account():
    fake = FakeEsri()
    w = W.EsriWalking(ROUTING, token="token-fixed", http=fake)
    walk(w, [0.5])
    assert fake.tokens == 0 and all(d["token"] == "token-fixed" for _, d in fake.calls)


def test_refused_account_is_unavailable():
    def refuse(url, data):
        return {"error": {"code": 400, "message": "Invalid username or password."}}

    with pytest.raises(W.WalkingUnavailable, match="refused"):
        walk(W.EsriWalking(ROUTING, portal_url=PORTAL, username="svc", password="wrong", http=refuse), [0.5])


def test_failed_solve_is_unavailable():
    fake = FakeEsri()
    fake.fail = "OriginDestinationCostMatrix/solveODCostMatrix"
    with pytest.raises(W.WalkingUnavailable, match="could not calculate"):
        walk(service(fake), [0.5])


def test_unreachable_service_is_unavailable(monkeypatch):
    def down(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(W.urllib.request, "urlopen", down)
    w = W.EsriWalking(ROUTING, token="t")
    with pytest.raises(W.WalkingUnavailable, match="could not be reached"):
        walk(w, [0.5])


def test_status_for_the_admin_portal():
    assert service(FakeEsri()).status()["ok"] is True
    bad = service(FakeEsri(), travel_mode="Hover").status()
    assert bad["ok"] is False and "Hover" in bad["message"]


def test_rings_to_geojson_keep_holes_and_parts():
    hole = [[30.02, -1.92], [30.02, -1.98], [30.08, -1.98], [30.08, -1.92], [30.02, -1.92]]  # counter-clockwise
    other = [[[31.0, -1.9], [31.1, -1.9], [31.1, -2.0], [31.0, -2.0], [31.0, -1.9]]]
    g = W.esri_rings_to_geojson(SQUARE + [hole])
    assert g["type"] == "Polygon" and len(g["coordinates"]) == 2
    outer, inner = g["coordinates"]
    assert W._ring_area(outer) > 0 > W._ring_area(inner)  # GeoJSON: outer counter-clockwise, holes clockwise
    assert W.esri_rings_to_geojson(SQUARE + other)["type"] == "MultiPolygon"
    assert W.esri_rings_to_geojson([]) is None


def settings(**k):
    base = {"esri_routing_url": ROUTING, "esri_portal_url": PORTAL, "esri_username": None, "esri_password": None,
            "esri_token": None, "esri_referer": "https://esri.test", "esri_travel_mode": "Walking", "esri_timeout": 5,
            "esri_verify_ssl": True, "walking_cache_size": 8}
    return SimpleNamespace(**{**base, **k})


def test_the_network_is_no_longer_uploaded():
    from fastapi import HTTPException

    from app.imports import service as S

    assert "walking_network" not in S.KINDS
    with pytest.raises(HTTPException) as e:
        S.create_upload(None, kind="walking_network", file_name="rwanda-latest.osm.pbf", content=b"x",
                        academic_year=None, user=None)
    assert e.value.status_code == 422


def test_from_settings_needs_an_account_or_a_token():
    assert W.from_settings(settings()) is None
    assert W.from_settings(settings(esri_username="svc")) is None
    assert isinstance(W.from_settings(settings(esri_username="svc", esri_password="x")), W.EsriWalking)
    assert isinstance(W.from_settings(settings(esri_token="t")), W.EsriWalking)
