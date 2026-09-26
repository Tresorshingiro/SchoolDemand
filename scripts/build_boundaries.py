"""
Download Rwanda's district and sector boundaries and save them for the dashboard map.

Source: geoBoundaries gbOpen RWA (Open Data Rwanda, 2012; country outline from Sentinel-2), CC BY 4.0 —
https://www.geoboundaries.org. Sector names are matched to the roster's spelling, and each sector gets its
district (sector names repeat across districts), so the map can outline the district / sector picked in the
dashboard filters.

  dashboard/public/data/rwanda.geojson      country outline (the map masks everything outside it)
  dashboard/public/data/districts.geojson   30 districts, property d
  dashboard/public/data/sectors.geojson     416 sectors, properties d (district) and s (sector)

Run:  python scripts/build_boundaries.py
"""
from __future__ import annotations

import json
import unicodedata
import urllib.request

import analysis as A

API = "https://www.geoboundaries.org/api/current/gbOpen/RWA/{level}/"
OUT = A.ROOT / "dashboard" / "public" / "data"
DIGITS = 5  # ~1 m; keeps the files small
ALIASES = {"shyrongi": "shyorongi"}  # boundary spelling -> roster spelling (Rulindo)


def fetch(level: str) -> dict:
    with urllib.request.urlopen(API.format(level=level), timeout=120) as r:
        url = json.load(r)["simplifiedGeometryGeoJSON"]
    with urllib.request.urlopen(url, timeout=300) as r:
        return json.load(r)


def key(name: str) -> str:
    """Case-, accent- and spacing-insensitive name for matching."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    k = "".join(ch for ch in s.lower() if ch.isalnum())
    return ALIASES.get(k, k)


def rings(geom: dict) -> list[list[list[float]]]:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [ring for poly in polys for ring in poly[:1]]  # outer rings


def inside(x: float, y: float, ring: list[list[float]]) -> bool:
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def centroid(ring: list[list[float]]) -> tuple[float, float]:
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        c = x1 * y2 - x2 * y1
        a, cx, cy = a + c, cx + (x1 + x2) * c, cy + (y1 + y2) * c
    return (cx / (3 * a), cy / (3 * a)) if a else tuple(map(lambda v: sum(v) / len(ring), zip(*ring)))


def rounded(geom: dict) -> dict:
    def r(c):
        return [round(c[0], DIGITS), round(c[1], DIGITS)] if isinstance(c[0], (int, float)) else [r(x) for x in c]
    return {"type": geom["type"], "coordinates": r(geom["coordinates"])}


def save(name: str, features: list[dict]) -> None:
    path = OUT / name
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"{path.relative_to(A.ROOT)}  {len(features)} features  {path.stat().st_size / 1024:,.0f} KB")


def main() -> None:
    roster = A.load_roster()
    info = A._school_info(roster)
    districts = {key(d): d for d in info["district"].unique()}
    sectors = {(key(d), key(s)): (d, s) for d, s in info[["district", "sector"]].drop_duplicates().itertuples(index=False)}

    adm0, adm2, adm3 = fetch("ADM0"), fetch("ADM2"), fetch("ADM3")

    dist_features, dist_rings = [], []
    for f in adm2["features"]:
        d = districts.get(key(f["properties"]["shapeName"]))
        if d is None:
            raise SystemExit(f"District not in the roster: {f['properties']['shapeName']}")
        dist_features.append({"type": "Feature", "properties": {"d": d}, "geometry": rounded(f["geometry"])})
        dist_rings.append((d, rings(f["geometry"])))

    sect_features, unmatched = [], []
    for f in adm3["features"]:
        ring = max(rings(f["geometry"]), key=len)
        x, y = centroid(ring)
        votes = [d for d, rs in dist_rings if any(inside(x, y, r) for r in rs)]
        if not votes:  # centroid outside every district (odd shape): vote with the vertices
            counts = {d: sum(any(inside(px, py, r) for r in rs) for px, py in ring[::5]) for d, rs in dist_rings}
            votes = [max(counts, key=counts.get)]
        d = votes[0]
        match = sectors.get((key(d), key(f["properties"]["shapeName"])))
        if match is None:
            unmatched.append(f"{d} / {f['properties']['shapeName']}")
            match = (d, f["properties"]["shapeName"])
        sect_features.append({"type": "Feature", "properties": {"d": match[0], "s": match[1]}, "geometry": rounded(f["geometry"])})

    save("rwanda.geojson", [{"type": "Feature", "properties": {}, "geometry": rounded(adm0["features"][0]["geometry"])}])
    save("districts.geojson", dist_features)
    save("sectors.geojson", sect_features)
    matched = {(p["properties"]["d"], p["properties"]["s"]) for p in sect_features}
    missing = sorted(f"{d} / {s}" for d, s in sectors.values() if (d, s) not in matched and s != A.UNKNOWN)
    print(f"sectors matched to the roster: {len(sect_features) - len(unmatched)} of {len(sect_features)}")
    if unmatched:
        print("  boundary sectors with no roster match (kept with the boundary name):", "; ".join(unmatched))
    if missing:
        print("  roster sectors with no boundary:", "; ".join(missing))


if __name__ == "__main__":
    main()
