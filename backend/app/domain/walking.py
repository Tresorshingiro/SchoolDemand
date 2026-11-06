"""
Walking distance on the Esri Rwanda road network: the network analysis services of Esri Rwanda's ArcGIS Enterprise
(settings.esri_routing_url, the Routing042026 network built from OpenStreetMap roads of July 2025, kept up to date by
Esri Rwanda). Nothing is uploaded or stored here: each planned school asks the service.

    walking distance(A, B) = A to the network + along the network + the network to B

* Along the network: an Origin Destination Cost Matrix solve from the planned school to the schools within its walking
  distance in a straight line (no school farther than that can be within it on foot), in the service's "Walking"
  travel mode, by length. The mode keeps the one-way restriction of the driving modes; it is removed, because a
  pedestrian walks a one-way street both ways.
* To and from the network: the service's DistanceToNetworkInMeters of each point (it places points up to 20 km away,
  so a point far from any road shows a long walk to the network, as before).
* The walking area on the map: a Service Area solve from the point, to its walking distance less its walk to the
  network. For the map only: a failure there never fails the run.
* A school is "connected" unless the service finds no route to it, or cannot place it on the network.

Results are kept per point, distance and schools asked about (EsriWalking.cache_size), since every run of a plan asks
again. The service's token comes from Esri Rwanda's portal (generateToken with a username and password, or a fixed
ESRI_TOKEN), is kept until shortly before it expires and is never sent to the browser.
"""
from __future__ import annotations

import json
import logging
import math
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

log = logging.getLogger("school_planning.walking")

INVALID_TOKEN = {498, 499}       # ArcGIS: invalid or expired token, token required
TOKEN_MINUTES = 60
TOKEN_MARGIN_S = 5 * 60          # a new token this long before the old one expires
BATCH = 1000                     # destinations per Origin Destination Cost Matrix request
STRAIGHT_MARGIN = 1.01           # schools asked about: within the walking distance in a straight line (+1%)
UNITS_M = {"esrinaumeters": 1.0, "esrinaukilometers": 1000.0, "esrinaumiles": 1609.344, "esrinaufeet": 0.3048}
ONEWAY = "oneway"


class WalkingUnavailable(Exception):
    """The walking-distance service could not answer (cannot be reached, refused the request or the account)."""


@dataclass(frozen=True)
class Reach:
    """What a walk from one point reaches, for the targets asked about."""
    km: np.ndarray               # walking distance to each target; inf beyond the limit, with no route or no coordinates
    snap_km: float               # from the point to the network
    on_main_network: bool        # the service placed the point on the network
    connected: np.ndarray        # False for a target the service has no route to (or no coordinates)
    area: dict | None = None     # GeoJSON outline of the walking area, for the map only


class Walking(Protocol):
    """Anything that tells how far a point reaches on foot (EsriWalking; a small graph in the tests)."""

    def reach(self, lat: float, lon: float, lats: np.ndarray, lons: np.ndarray, limit_km: float) -> Reach: ...


def distance_km(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Great-circle distance in km from one point to many (inf where a coordinate is missing)."""
    p1, p2 = math.radians(lat), np.radians(lats)
    a = (np.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * np.cos(p2) * np.sin(np.radians(lons - lon) / 2) ** 2)
    d = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return np.where(np.isfinite(d), d, np.inf)


# ---------------------------------------------------------------- Esri JSON helpers
def _features(points: list[tuple[float, float]]) -> str:
    """Points (lat, lon) as an Esri feature set, named by their position."""
    return json.dumps({"features": [{"geometry": {"x": float(lon), "y": float(lat)}, "attributes": {"Name": str(i)}}
                                    for i, (lat, lon) in enumerate(points)],
                       "spatialReference": {"wkid": 4326}})


def walking_mode(description: dict, name: str) -> tuple[dict, str, float]:
    """(travel mode, distance attribute, metres per unit) of a network analysis layer's description: the mode `name`
    with its one-way restriction removed. ValueError when the layer has no such mode."""
    modes = description.get("supportedTravelModes") or []
    mode = next((m for m in modes if str(m.get("name", "")).casefold() == name.casefold()), None)
    if mode is None:
        found = ", ".join(str(m.get("name")) for m in modes) or "none"
        raise ValueError(f"The routing service has no {name!r} travel mode (it has: {found}).")
    mode = {**mode,
            "restrictionAttributeNames": [r for r in mode.get("restrictionAttributeNames") or []
                                          if r.casefold() != ONEWAY],
            "attributeParameterValues": [p for p in mode.get("attributeParameterValues") or []
                                         if str(p.get("attributeName", "")).casefold() != ONEWAY]}
    attr = mode.get("distanceAttributeName") or mode.get("impedanceAttributeName")
    units = next((a.get("units") for a in (description.get("networkDataset") or {}).get("networkAttributes") or []
                  if a.get("name") == attr), "esriNAUMeters")
    return mode, attr, UNITS_M.get(str(units).casefold(), 1.0)


def _ring_area(ring: list[list[float]]) -> float:
    """Shoelace sum: negative for a clockwise ring (an Esri outer ring)."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def _inside(point: list[float], ring: list[list[float]]) -> bool:
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def esri_rings_to_geojson(rings: list[list[list[float]]]) -> dict | None:
    """An Esri polygon's rings (outer rings clockwise, holes counter-clockwise) as a GeoJSON Polygon or MultiPolygon
    (outer rings counter-clockwise, holes clockwise; coordinates to 5 decimals)."""
    def clean(ring):
        r = [[round(float(x), 5), round(float(y), 5)] for x, y, *_ in ring]
        return r if len(r) >= 4 else None

    outers, holes = [], []
    for ring in rings:
        r = clean(ring)
        if r is None:
            continue
        (outers if _ring_area(r) <= 0 else holes).append(r)
    if not outers:
        return None
    polygons = [[o[::-1]] for o in outers]  # counter-clockwise
    for h in holes:  # clockwise, in the outer ring that holds it
        k = next((i for i, o in enumerate(outers) if _inside(h[0], o)), None)
        if k is not None:
            polygons[k].append(h[::-1])
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


# ---------------------------------------------------------------- the service
Http = Callable[[str, dict], dict]  # POST form data to a URL -> the parsed JSON answer


class EsriWalking:
    """The Esri Rwanda network analysis services (Origin Destination Cost Matrix, Service Area)."""

    def __init__(self, routing_url: str, *, portal_url: str | None = None, username: str | None = None,
                 password: str | None = None, token: str | None = None, referer: str = "",
                 travel_mode: str = "Walking", timeout: float = 60, verify_ssl: bool = True, cache_size: int = 256,
                 http: Http | None = None) -> None:
        self.routing_url = routing_url.rstrip("/")
        self.portal_url = (portal_url or "").rstrip("/")
        self.username, self.password, self.fixed_token = username, password, token
        self.referer = referer or _origin(self.routing_url)
        self.travel_mode, self.timeout, self.verify_ssl = travel_mode, timeout, verify_ssl
        self.cache_size = cache_size
        self._http = http or self._urllib_post
        self._lock = threading.RLock()
        self._token: str | None = None
        self._expires = 0.0
        self._mode: tuple[dict, str, float] | None = None
        self._cache: OrderedDict[tuple, Reach] = OrderedDict()

    # ------------------------------------------------------------ HTTP and the token
    def _urllib_post(self, url: str, data: dict) -> dict:
        request = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                         headers={"Referer": self.referer, "Accept": "application/json"})
        context = None if self.verify_ssl else ssl._create_unverified_context()  # noqa: S323 — opt-in setting
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=context) as response:  # noqa: S310
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            log.warning("walking service %s unreachable: %r", url, e)
            raise WalkingUnavailable("The Esri Rwanda routing service could not be reached. Try again in a moment.") from e

    def _new_token(self) -> str:
        if self.fixed_token:
            return self.fixed_token
        if not (self.portal_url and self.username and self.password):
            raise WalkingUnavailable("Walking distance is not set up: ESRI_USERNAME and ESRI_PASSWORD are missing.")
        got = self._http(f"{self.portal_url}/sharing/rest/generateToken", {
            "username": self.username, "password": self.password, "client": "referer", "referer": self.referer,
            "expiration": TOKEN_MINUTES, "f": "json"})
        token = got.get("token")
        if not token:
            log.warning("Esri Rwanda portal refused the walking service account: %s", got.get("error"))
            raise WalkingUnavailable("The Esri Rwanda portal refused the walking-distance account (ESRI_USERNAME / "
                                     "ESRI_PASSWORD).")
        expires = float(got.get("expires") or 0) / 1000  # milliseconds since 1970
        self._expires = expires if expires else time.time() + TOKEN_MINUTES * 60
        return token

    def _get_token(self, fresh: bool = False) -> str:
        with self._lock:
            if fresh or self._token is None or (not self.fixed_token and time.time() > self._expires - TOKEN_MARGIN_S):
                self._token = self._new_token()
            return self._token

    def _call(self, path: str, data: dict) -> dict:
        """POST to a layer of the routing service with the token (a new one once when it was refused)."""
        url = f"{self.routing_url}/{path}"
        for attempt in range(2):
            answer = self._http(url, {**data, "f": "json", "token": self._get_token(fresh=attempt > 0)})
            error = answer.get("error") if isinstance(answer, dict) else None
            if not error:
                return answer
            if error.get("code") in INVALID_TOKEN and attempt == 0 and not self.fixed_token:
                continue
            detail = "; ".join(error.get("details") or []) or error.get("message") or "error"
            raise _SolveError(f"{path}: {detail}", error)
        raise AssertionError("unreachable")

    def _walking_mode(self) -> tuple[dict, str, float]:
        with self._lock:
            if self._mode is None:
                try:
                    description = self._call("OriginDestinationCostMatrix", {})
                    self._mode = walking_mode(description, self.travel_mode)
                except (_SolveError, ValueError) as e:
                    log.warning("walking travel mode unavailable: %s", e)
                    raise WalkingUnavailable(f"The Esri Rwanda routing service has no usable walking mode: {e}") from e
            return self._mode

    # ------------------------------------------------------------ solves
    def _matrix(self, lat: float, lon: float, targets: list[tuple[float, float]]) -> tuple[float, int, list]:
        """(origin metres to the network, origin status, per target (metres along or None, metres to the network,
        status)). The origin itself is asked about too, so the answer always says where the origin is."""
        mode, attr, per_unit = self._walking_mode()
        points = [(lat, lon), *targets]
        out: list = []
        origin_snap, origin_status = math.inf, 1
        for start in range(0, len(points), BATCH):
            chunk = points[start:start + BATCH]
            try:
                answer = self._call("OriginDestinationCostMatrix/solveODCostMatrix", {
                    "origins": _features([(lat, lon)]), "destinations": _features(chunk),
                    "travelMode": json.dumps(mode), "outputType": "esriNAODOutputSparseMatrix",
                    "returnOrigins": "true", "returnDestinations": "true", "outSR": 4326})
            except _SolveError as e:
                if e.no_solution:  # nothing reachable (the point is not on the network): no routes, not a failure
                    answer = {}
                else:
                    log.warning("walking distance solve failed: %s", e)
                    raise WalkingUnavailable("The Esri Rwanda routing service could not calculate walking "
                                             f"distances ({e}).") from e
            origins = (answer.get("origins") or {}).get("features") or []
            if origins:
                a = origins[0].get("attributes") or {}
                origin_snap, origin_status = float(a.get("DistanceToNetworkInMeters") or 0), int(a.get("Status") or 0)
            matrix = answer.get("odCostMatrix") or {}
            names = matrix.get("costAttributeNames") or [attr]
            col = names.index(attr) if attr in names else 0
            row = next((v for k, v in matrix.items() if k != "costAttributeNames"), {})
            by_name = {}
            for f in (answer.get("destinations") or {}).get("features") or []:
                a = f.get("attributes") or {}
                cost = row.get(str(a.get("ObjectID")))
                by_name[int(a.get("Name"))] = (None if cost is None or cost[col] is None else float(cost[col]) * per_unit,
                                               float(a.get("DistanceToNetworkInMeters") or 0), int(a.get("Status") or 0))
            out += [by_name.get(i, (None, math.inf, 1)) for i in range(len(chunk))]
        return origin_snap, origin_status, out[1:]

    def _area(self, lat: float, lon: float, metres: float) -> dict | None:
        """The walking area's outline, for the map (None when it fails: logged, never fails the run)."""
        if metres <= 0:
            return None
        mode, _, per_unit = self._walking_mode()
        try:
            answer = self._call("ServiceArea/solveServiceArea", {
                "facilities": _features([(lat, lon)]), "travelMode": json.dumps(mode),
                "defaultBreaks": f"{metres / per_unit:.1f}", "travelDirection": "esriNATravelDirectionFromFacility",
                "outputPolygons": "esriNAOutputPolygonSimplified", "returnFacilities": "false", "outSR": 4326})
            polygons = (answer.get("saPolygons") or {}).get("features") or []
            rings = [r for p in polygons for r in (p.get("geometry") or {}).get("rings") or []]
            return esri_rings_to_geojson(rings)
        except Exception as e:  # noqa: BLE001
            log.warning("walking area outline failed: %s", e)
            raise _AreaFailed() from e

    def reach(self, lat: float, lon: float, lats: np.ndarray, lons: np.ndarray, limit_km: float) -> Reach:
        """Walk from (lat, lon) up to limit_km; the walking distance to each of the targets (lats, lons).
        WalkingUnavailable when the service cannot answer."""
        lats, lons = np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)
        ok = np.isfinite(lats) & np.isfinite(lons)
        asked = ok & (distance_km(lat, lon, lats, lons) <= limit_km * STRAIGHT_MARGIN)
        idx = np.nonzero(asked)[0]
        targets = [(round(float(lats[i]), 6), round(float(lons[i]), 6)) for i in idx]
        key = (round(float(lat), 6), round(float(lon), 6), round(float(limit_km), 3), tuple(targets))
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                cached = self._cache[key]
                return _expand(cached, len(lats), ok, idx)

        origin_snap, status, results = self._matrix(lat, lon, targets)
        limit_m = limit_km * 1000
        located = status == 0
        km = np.full(len(idx), np.inf)
        routed = np.zeros(len(idx), dtype=bool)
        for k, (along, snap, dest_status) in enumerate(results):
            if not located or along is None or dest_status != 0:
                continue
            routed[k] = True
            total = origin_snap + along + snap
            if total <= limit_m:
                km[k] = total / 1000
        keep = True
        try:
            area = self._area(lat, lon, limit_m - origin_snap) if located else None
        except _AreaFailed:
            area, keep = None, False  # not kept: the next run tries the outline again
        compact = Reach(km, origin_snap / 1000, located, routed, area)
        if keep:
            with self._lock:
                self._cache[key] = compact
                while len(self._cache) > max(self.cache_size, 1):
                    self._cache.popitem(last=False)
        return _expand(compact, len(lats), ok, idx)

    # ------------------------------------------------------------ the admin portal's status
    def status(self) -> dict:
        """Can the service be used now? For the admin portal (token, travel mode)."""
        out = {"configured": True, "service": self.routing_url, "travel_mode": self.travel_mode, "ok": False,
               "message": None}
        try:
            with self._lock:
                self._mode = None  # read the service's description again
            mode, attr, _ = self._walking_mode()
            out.update(ok=True, travel_mode=mode.get("name", self.travel_mode), distance=attr)
        except WalkingUnavailable as e:
            out["message"] = str(e)
        return out


class _SolveError(Exception):
    def __init__(self, message: str, error: dict) -> None:
        super().__init__(message)
        text = " ".join([str(error.get("message") or ""), *map(str, error.get("details") or [])]).casefold()
        self.no_solution = "no solution found" in text


class _AreaFailed(Exception):
    pass


def _expand(compact: Reach, n: int, ok: np.ndarray, idx: np.ndarray) -> Reach:
    """A Reach over the targets asked about -> over every target (not asked: beyond reach, not cut off)."""
    km = np.full(n, np.inf)
    km[idx] = compact.km
    connected = ok.copy()
    connected[idx] = compact.connected
    return Reach(km, compact.snap_km, compact.on_main_network, connected, compact.area)


def _origin(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme else url


def from_settings(settings) -> EsriWalking | None:
    """The walking service of the settings; None when it is not set up (no account and no token)."""
    if not settings.esri_routing_url or not (settings.esri_token or (settings.esri_username and settings.esri_password)):
        return None
    return EsriWalking(settings.esri_routing_url, portal_url=settings.esri_portal_url, username=settings.esri_username,
                       password=settings.esri_password, token=settings.esri_token, referer=settings.esri_referer,
                       travel_mode=settings.esri_travel_mode, timeout=settings.esri_timeout,
                       verify_ssl=settings.esri_verify_ssl, cache_size=settings.walking_cache_size)
