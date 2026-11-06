"""
Rwanda's administrative boundaries from the MINEDUC GIS portal: the "Administrative boundaries corrected" feature
service of Education Mapping (settings.boundaries_url, public, no token; boundaries as of 2022, with cells and villages
too). The import job (etl/boundaries.py) loads the provinces, districts and sectors into the database; the map, the
place of a planned school and the checks of uploaded files read them from there.

Layers used: 0 Province boundaries, 1 District boundaries (district, province), 2 Sector boundaries (district,
sector). Shapes are simplified on the server (settings.boundaries_simplify degrees, about 20 m) to keep the map light.
"""
from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from ..config import settings
from ..domain import analysis as A

log = logging.getLogger("school_planning.boundaries")

LAYERS = {"districts": (1, ["district", "province"]), "sectors": (2, ["district", "sector"])}
PAGE = 1000
EXPECTED = {"districts": 30, "sectors": 416}

Get = Callable[[str, dict], dict]  # GET a URL with query parameters -> the parsed JSON answer


class BoundariesUnavailable(Exception):
    """The boundary service could not be read, or did not give what is expected."""


@dataclass(frozen=True)
class Boundaries:
    districts: list[dict]  # GeoJSON features, properties {"d": district, "p": province}
    sectors: list[dict]    # GeoJSON features, properties {"d": district, "s": sector}


def _get(url: str, params: dict) -> dict:
    request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"Accept": "application/json"})
    context = None if settings.portal_verify_ssl else ssl._create_unverified_context()  # noqa: S323 — opt-in setting
    try:
        with urllib.request.urlopen(request, timeout=300, context=context) as response:  # noqa: S310
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise BoundariesUnavailable(f"The boundary service could not be read ({url}): {e}") from e


def _layer(get: Get, url: str, layer: int, fields: list[str], simplify: float) -> list[dict]:
    """Every feature of a layer as GeoJSON (in pages: the service gives at most maxRecordCount at once)."""
    features: list[dict] = []
    while True:
        params = {"f": "geojson", "where": "1=1", "outFields": ",".join(fields), "outSR": 4326, "geometryPrecision": 5,
                  "orderByFields": "objectid", "resultOffset": len(features), "resultRecordCount": PAGE}
        if simplify:
            params["maxAllowableOffset"] = simplify
        page = get(f"{url}/{layer}/query", params)
        if "error" in page:
            raise BoundariesUnavailable(f"The boundary service refused the query of layer {layer}: "
                                        f"{page['error'].get('message')}")
        got = page.get("features") or []
        features += got
        more = page.get("exceededTransferLimit") or (page.get("properties") or {}).get("exceededTransferLimit")
        if not got or not more:
            return features


def clean(name) -> str:
    return " ".join(str(name or "").split())


def place_key(district, sector) -> tuple[str, str]:
    """A district and sector as the files and the boundaries are matched: ignoring case and spacing (the school data
    writes some districts' sectors in capitals, the boundaries do not)."""
    return clean(district).casefold(), clean(sector).casefold()


def fetch(url: str | None = None, simplify: float | None = None, get: Get = _get) -> Boundaries:
    """The districts and sectors of the service, checked: 30 districts in the five provinces, 416 sectors, each with
    a district of the list and a shape. BoundariesUnavailable otherwise."""
    url = (url or settings.boundaries_url).rstrip("/")
    simplify = settings.boundaries_simplify if simplify is None else simplify
    raw = {k: _layer(get, url, layer, fields, simplify) for k, (layer, fields) in LAYERS.items()}
    districts = [{"type": "Feature", "geometry": f.get("geometry"),
                  "properties": {"d": clean(f["properties"].get("district")), "p": clean(f["properties"].get("province"))}}
                 for f in raw["districts"]]
    sectors = [{"type": "Feature", "geometry": f.get("geometry"),
                "properties": {"d": clean(f["properties"].get("district")), "s": clean(f["properties"].get("sector"))}}
               for f in raw["sectors"]]
    problems = []
    for kind, rows in (("districts", districts), ("sectors", sectors)):
        if len(rows) != EXPECTED[kind]:
            problems.append(f"{len(rows)} {kind} (expected {EXPECTED[kind]})")
        if any(not f["geometry"] for f in rows):
            problems.append(f"{kind} without a shape")
    names = {f["properties"]["d"] for f in districts}
    if unknown := sorted({f["properties"]["p"] for f in districts} - set(A.PROVINCES)):
        problems.append(f"unknown provinces {unknown}")
    if missing := sorted({f["properties"]["d"] for f in sectors} - names):
        problems.append(f"sectors in districts not in the list {missing}")
    keys = [(f["properties"]["d"].casefold(), f["properties"]["s"].casefold()) for f in sectors]
    if len(set(keys)) != len(keys):
        problems.append("sectors listed twice")
    if problems:
        raise BoundariesUnavailable(f"The boundary service did not give the expected boundaries: {'; '.join(problems)}.")
    return Boundaries(districts, sectors)
