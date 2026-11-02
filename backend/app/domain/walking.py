"""
The walking network: how far apart two places are on foot, along OpenStreetMap roads and paths.

    walking distance(A, B) = A to its nearest network point + along the network + B's nearest network point to B

Built from a Rwanda .osm.pbf extract (published as the data kind "walking_network"). Every way with a highway tag can be
walked in both directions, except SKIP_HIGHWAYS and ways marked foot / access = no or private. To keep it small, a stretch
between junctions keeps a point about every SPACING_KM; the kept edges carry the full length of what they replace.
Distance only: no slope and no walking time.
"""
from __future__ import annotations

import math
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

SKIP_HIGHWAYS = frozenset({"motorway", "motorway_link", "construction", "proposed", "raceway", "bus_guideway", "abandoned",
                           "platform", "elevator"})
NO_FOOT = frozenset({"no", "private"})
SPACING_KM = 0.025
KM_PER_DEG_LAT = 110.57
KM_PER_DEG_LON = 111.32  # at the equator
_MIDDLE_LAT = -1.95      # Rwanda: the nearest-point search uses one projection, good to a fraction of a percent here
_KX, _KY = KM_PER_DEG_LON * math.cos(math.radians(_MIDDLE_LAT)), KM_PER_DEG_LAT


def _xy(lats, lons) -> np.ndarray:
    return np.column_stack([np.asarray(lons, dtype=float) * _KX, np.asarray(lats, dtype=float) * _KY])


def _lengths(lat: np.ndarray, lon: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    kx = KM_PER_DEG_LON * np.cos(np.radians((lat[a] + lat[b]) / 2))
    return np.hypot((lon[a] - lon[b]) * kx, (lat[a] - lat[b]) * KM_PER_DEG_LAT)


def _shortest_edges(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One edge per pair of points (the shorter of parallel ones), no edge from a point to itself."""
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    keep = lo != hi
    lo, hi, w = lo[keep], hi[keep], w[keep]
    order = np.lexsort((w, hi, lo))
    lo, hi, w = lo[order], hi[order], w[order]
    first = np.r_[True, (lo[1:] != lo[:-1]) | (hi[1:] != hi[:-1])] if len(lo) else np.zeros(0, dtype=bool)
    return lo[first], hi[first], w[first]


def _thin(n: int, a: np.ndarray, b: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Edges with the points inside each stretch between junctions thinned to about every SPACING_KM."""
    a, b, w = _shortest_edges(a, b, w)
    g = coo_matrix((np.r_[w, w], (np.r_[a, b], np.r_[b, a])), shape=(n, n)).tocsr()
    ptr, nbr, dist = g.indptr.tolist(), g.indices.tolist(), g.data.tolist()
    junction = bytearray(1 if ptr[i + 1] - ptr[i] != 2 else 0 for i in range(n))
    walked, seen = bytearray(len(nbr)), bytearray(n)
    out_a, out_b, out_w = [], [], []

    def walk_from(start: int) -> None:
        for k in range(ptr[start], ptr[start + 1]):
            if walked[k]:
                continue
            walked[k] = 1
            prev, cur, acc, last = start, nbr[k], dist[k], start
            while not junction[cur]:
                seen[cur] = 1
                if acc >= SPACING_KM:
                    out_a.append(last); out_b.append(cur); out_w.append(acc)
                    last, acc = cur, 0.0
                s = ptr[cur]
                j = s if nbr[s] != prev else s + 1
                acc += dist[j]
                prev, cur = cur, nbr[j]
            for j in range(ptr[cur], ptr[cur + 1]):  # do not walk this stretch again from its other end
                if nbr[j] == prev:
                    walked[j] = 1
            if last != cur:
                out_a.append(last); out_b.append(cur); out_w.append(acc)

    for i in range(n):
        if junction[i] and ptr[i + 1] > ptr[i]:
            seen[i] = 1
            walk_from(i)
    for i in range(n):  # closed loops with no junction: start anywhere on them
        if not seen[i] and ptr[i + 1] - ptr[i] == 2:
            junction[i] = 1
            seen[i] = 1
            walk_from(i)
    return _shortest_edges(np.array(out_a, dtype=np.int64), np.array(out_b, dtype=np.int64), np.array(out_w, dtype=float))


@dataclass(frozen=True)
class Reach:
    """What a walk from one point reaches, for the targets asked about."""
    km: np.ndarray               # walking distance to each target; inf beyond the limit, with no route or no coordinates
    snap_km: float               # from the point to its nearest network point
    on_main_network: bool        # that network point is on the largest connected part
    connected: np.ndarray        # each target's nearest network point is on the same connected part
    reached_lat: np.ndarray      # the network points within the limit
    reached_lon: np.ndarray


class WalkingNetwork:
    def __init__(self, lat: np.ndarray, lon: np.ndarray, graph: csr_matrix) -> None:
        self.lat, self.lon, self.graph = lat, lon, graph
        _, self.label = connected_components(graph, directed=False)
        self.main = int(np.argmax(np.bincount(self.label)))
        self.tree = cKDTree(_xy(lat, lon))

    @property
    def nodes(self) -> int:
        return len(self.lat)

    @property
    def total_km(self) -> float:
        return float(self.graph.data.sum() / 2)

    @classmethod
    def from_edges(cls, lats: Sequence[float], lons: Sequence[float], edges: Sequence[tuple[int, int]]) -> WalkingNetwork:
        lat, lon = np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)
        pairs = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
        a, b = pairs[:, 0], pairs[:, 1]
        a, b, w = _thin(len(lat), a, b, _lengths(lat, lon, a, b))
        if not len(a):
            raise ValueError("no walkable ways")
        used, inverse = np.unique(np.r_[a, b], return_inverse=True)
        a, b = inverse[: len(a)], inverse[len(a):]
        m = len(used)
        graph = coo_matrix((np.r_[w, w], (np.r_[a, b], np.r_[b, a])), shape=(m, m)).tocsr()
        return cls(lat[used].astype(np.float32), lon[used].astype(np.float32), _compact(graph))

    @classmethod
    def from_pbf(cls, path: Path) -> WalkingNetwork:
        """The walkable ways of an .osm.pbf. ValueError when it has none; osmium's error when it cannot be read."""
        import osmium  # noqa: PLC0415 — only the check of a new file needs it

        index: dict[int, int] = {}
        lats: list[float] = []
        lons: list[float] = []
        edges: list[tuple[int, int]] = []

        class Ways(osmium.SimpleHandler):
            def way(self, w) -> None:
                tags = w.tags
                kind = tags.get("highway")
                if (kind is None or kind in SKIP_HIGHWAYS or tags.get("foot") in NO_FOOT
                        or tags.get("access") in NO_FOOT):
                    return
                prev = None
                for n in w.nodes:
                    if not n.location.valid():
                        prev = None
                        continue
                    i = index.get(n.ref)
                    if i is None:
                        i = index[n.ref] = len(lats)
                        lats.append(n.location.lat)
                        lons.append(n.location.lon)
                    if prev is not None:
                        edges.append((prev, i))
                    prev = i

        Ways().apply_file(str(path), locations=True)
        if not edges:
            raise ValueError("no walkable ways")
        return cls.from_edges(lats, lons, edges)

    def save(self, path: Path) -> None:
        g = self.graph
        np.savez_compressed(path, lat=self.lat, lon=self.lon, data=g.data, indices=g.indices, indptr=g.indptr)

    @classmethod
    def load(cls, path: Path) -> WalkingNetwork:
        with np.load(path) as f:
            n = len(f["lat"])
            graph = csr_matrix((f["data"], f["indices"], f["indptr"]), shape=(n, n))
            return cls(f["lat"], f["lon"], graph)

    def _snap(self, lats: np.ndarray, lons: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """For each point: has coordinates, km to the nearest network point (inf without), which one (0 without)."""
        ok = np.isfinite(lats) & np.isfinite(lons)
        km, node = np.full(len(lats), np.inf), np.zeros(len(lats), dtype=np.int64)
        if ok.any():
            km[ok], node[ok] = self.tree.query(_xy(lats[ok], lons[ok]))
        return ok, km, node

    def reach(self, lat: float, lon: float, lats: np.ndarray, lons: np.ndarray, limit_km: float) -> Reach:
        """Walk from (lat, lon) up to limit_km; the walking distance to each of the targets (lats, lons)."""
        lats, lons = np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)
        ok, snap_t, node_t = self._snap(lats, lons)
        snap, node = self.tree.query(_xy([lat], [lon]))
        snap, node = float(snap[0]), int(node[0])
        same_part = ok & (self.label[node_t] == self.label[node])
        on_main = bool(self.label[node] == self.main)
        km = np.full(len(lats), np.inf)
        if snap > limit_km:
            empty = np.zeros(0)
            return Reach(km, snap, on_main, same_part, empty, empty)
        along = dijkstra(self.graph, directed=True, indices=node, limit=limit_km - snap)
        km[ok] = snap + along[node_t[ok]] + snap_t[ok]
        km[km > limit_km] = np.inf
        reached = np.isfinite(along)
        return Reach(km, snap, on_main, same_part, self.lat[reached].astype(float), self.lon[reached].astype(float))

    def coverage(self, lats: np.ndarray, lons: np.ndarray) -> dict:
        """How well the network serves the points: total km and shares within 100 m, 500 m, on the largest part."""
        lats, lons = np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)
        ok, snap, node = self._snap(lats, lons)
        return {"km": self.total_km, "within_100m": float((snap <= 0.1).mean()), "within_500m": float((snap <= 0.5).mean()),
                "on_main": float((ok & (self.label[node] == self.main)).mean())}

    def far(self, lats: np.ndarray, lons: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Per point: km to the nearest network point, and whether that point is off the largest connected part."""
        lats, lons = np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)
        ok, snap, node = self._snap(lats, lons)
        return snap, ~(ok & (self.label[node] == self.main))


def usable(path: Path) -> bool:
    """Can this routing file be read? False when it is missing, cut short or damaged."""
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None
    except (OSError, zipfile.BadZipFile, EOFError):
        return False


OUTLINE_SECTORS = 72


def outline(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> dict | None:
    """GeoJSON polygon around the points reached from (lat, lon), for the map only: the farthest point in each 5-degree
    sector. None under 3 points or sectors. (PostGIS ST_ConcaveHull took over 20 seconds on 1,800 points.)"""
    if len(lats) < 3:
        return None
    dx, dy = (np.asarray(lons, dtype=float) - lon) * _KX, (np.asarray(lats, dtype=float) - lat) * _KY
    angle = np.arctan2(dy, dx)
    sector = ((angle + math.pi) / (2 * math.pi) * OUTLINE_SECTORS).astype(int) % OUTLINE_SECTORS
    far = np.hypot(dx, dy)
    best = {}
    for i in np.lexsort((far, sector)):  # the last of each sector is its farthest
        best[int(sector[i])] = i
    picks = [best[k] for k in sorted(best)]
    if len(picks) < 3:
        return None
    ring = [[round(float(lons[i]), 5), round(float(lats[i]), 5)] for i in picks]
    turns = angle[picks]
    gaps = np.diff(np.r_[turns, turns[0] + 2 * math.pi])
    if gaps.max() >= math.pi:  # the walk goes one way only: the outline still starts from the point
        ring.insert(int(np.argmax(gaps)) + 1, [round(float(lon), 5), round(float(lat), 5)])
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


def extract_date(path: Path) -> str | None:
    """The date in an .osm.pbf's header ("2026-11-02"), None when it has none."""
    import osmium  # noqa: PLC0415

    with osmium.io.Reader(str(path), osmium.osm.osm_entity_bits.NOTHING) as reader:
        stamp = reader.header().get("osmosis_replication_timestamp", "")
    return stamp[:10] or None


def _compact(graph: csr_matrix) -> csr_matrix:
    """float64 lengths (what dijkstra works in, so it does not copy them on every search), 32-bit indices."""
    graph.indices = graph.indices.astype(np.int32)
    graph.indptr = graph.indptr.astype(np.int32)
    return graph
