"""Small street graphs that stand in for the Esri Rwanda walking service in the tests (no network access needed).

GraphWalking answers reach() as the service does: walking distance = the point to its nearest graph point + along the
graph + the target's nearest graph point to the target; a target on another part of the graph is not connected; the
area is a rough outline of the graph points reached.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from app.domain.walking import Reach

KM_LAT, KM_LON = 110.57, 111.32
_KX, _KY = KM_LON * math.cos(math.radians(-1.95)), KM_LAT


def _xy(lats, lons) -> np.ndarray:
    return np.column_stack([np.asarray(lons, dtype=float) * _KX, np.asarray(lats, dtype=float) * _KY])


def outline(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray, sectors: int = 36) -> dict | None:
    """A GeoJSON polygon through the farthest point reached in each direction (None under 3 points)."""
    if len(lats) < 3:
        return None
    dx, dy = (np.asarray(lons) - lon) * _KX, (np.asarray(lats) - lat) * _KY
    sector = ((np.arctan2(dy, dx) + math.pi) / (2 * math.pi) * sectors).astype(int) % sectors
    best = {}
    for i in np.lexsort((np.hypot(dx, dy), sector)):
        best[int(sector[i])] = i
    if len(best) < 3:
        return None
    ring = [[round(float(lons[i]), 5), round(float(lats[i]), 5)] for i in (best[k] for k in sorted(best))]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


class GraphWalking:
    def __init__(self, lat: np.ndarray, lon: np.ndarray, a: np.ndarray, b: np.ndarray) -> None:
        self.lat, self.lon = lat, lon
        kx = KM_LON * np.cos(np.radians((lat[a] + lat[b]) / 2))
        w = np.hypot((lon[a] - lon[b]) * kx, (lat[a] - lat[b]) * KM_LAT)
        n = len(lat)
        self.graph = coo_matrix((np.r_[w, w], (np.r_[a, b], np.r_[b, a])), shape=(n, n)).tocsr()
        _, self.label = connected_components(self.graph, directed=False)
        self.tree = cKDTree(_xy(lat, lon))

    @classmethod
    def from_edges(cls, lats, lons, edges) -> GraphWalking:
        pairs = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
        return cls(np.asarray(lats, dtype=float), np.asarray(lons, dtype=float), pairs[:, 0], pairs[:, 1])

    def reach(self, lat: float, lon: float, lats: np.ndarray, lons: np.ndarray, limit_km: float) -> Reach:
        lats, lons = np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)
        ok = np.isfinite(lats) & np.isfinite(lons)
        snap_t, node_t = np.full(len(lats), np.inf), np.zeros(len(lats), dtype=np.int64)
        if ok.any():
            snap_t[ok], node_t[ok] = self.tree.query(_xy(lats[ok], lons[ok]))
        snap, node = self.tree.query(_xy([lat], [lon]))
        snap, node = float(snap[0]), int(node[0])
        connected = ok & (self.label[node_t] == self.label[node])
        km = np.full(len(lats), np.inf)
        if snap > limit_km:
            return Reach(km, snap, True, connected, None)
        along = dijkstra(self.graph, directed=False, indices=node, limit=limit_km - snap)
        km[ok] = snap + along[node_t[ok]] + snap_t[ok]
        km[km > limit_km] = np.inf
        reached = np.isfinite(along)
        return Reach(km, snap, True, connected, outline(lat, lon, self.lat[reached], self.lon[reached]))


def grid(lat0: float = -2.05, lat1: float = -1.85, lon0: float = 30.0, lon1: float = 30.3,
         step: float = 0.002) -> GraphWalking:
    """Streets in a square grid, about 220 m apart, around the places the tests use."""
    lats, lons = np.arange(lat0, lat1 + step / 2, step), np.arange(lon0, lon1 + step / 2, step)
    n, m = len(lats), len(lons)
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    at = lambda i, j: i * m + j  # noqa: E731
    edges = [(at(i, j), at(i, j + 1)) for i in range(n) for j in range(m - 1)]
    edges += [(at(i, j), at(i + 1, j)) for i in range(n - 1) for j in range(m)]
    return GraphWalking.from_edges(la.ravel(), lo.ravel(), edges)


def line(points: list[tuple[float, float]], start: int = 0) -> tuple[list[float], list[float], list[tuple[int, int]]]:
    """(lats, lons, edges) of a path through `points`, node numbers from `start`."""
    return ([p[0] for p in points], [p[1] for p in points],
            [(start + k, start + k + 1) for k in range(len(points) - 1)])
