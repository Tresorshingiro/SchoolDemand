"""Small walking networks for tests (no OSM download needed)."""
from pathlib import Path

import numpy as np
import osmium

from app.domain.walking import WalkingNetwork


def grid(lat0: float = -2.05, lat1: float = -1.85, lon0: float = 30.0, lon1: float = 30.3,
         step: float = 0.002) -> WalkingNetwork:
    """Streets in a square grid, about 220 m apart, around the places the tests use."""
    lats, lons = np.arange(lat0, lat1 + step / 2, step), np.arange(lon0, lon1 + step / 2, step)
    n, m = len(lats), len(lons)
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    at = lambda i, j: i * m + j  # noqa: E731
    edges = [(at(i, j), at(i, j + 1)) for i in range(n) for j in range(m - 1)]
    edges += [(at(i, j), at(i + 1, j)) for i in range(n - 1) for j in range(m)]
    return WalkingNetwork.from_edges(la.ravel(), lo.ravel(), edges)


def line(points: list[tuple[float, float]], start: int = 0) -> tuple[list[float], list[float], list[tuple[int, int]]]:
    """(lats, lons, edges) of a path through `points`, node numbers from `start`."""
    return ([p[0] for p in points], [p[1] for p in points],
            [(start + k, start + k + 1) for k in range(len(points) - 1)])


def write_pbf(path: Path, ways: list[dict]) -> Path:
    """A tiny .osm.pbf: ways = [{"points": [(lat, lon), ...], "tags": {...}}, ...]; nodes are not shared between ways."""
    with osmium.SimpleWriter(str(path)) as w:
        node = 0
        nodes = []
        for way in ways:
            refs = []
            for lat, lon in way["points"]:
                node += 1
                nodes.append(osmium.osm.mutable.Node(id=node, location=(lon, lat)))
                refs.append(node)
            way["refs"] = refs
        for n in nodes:
            w.add_node(n)
        for k, way in enumerate(ways, start=1):
            w.add_way(osmium.osm.mutable.Way(id=k, nodes=way["refs"], tags=way["tags"]))
    return path
