"""
Load Rwanda's provinces, districts and sectors (names and outlines) from Education Mapping's boundary service
(app/services/boundaries.py) into the database, and the country outline as the union of the districts.

Rows are matched by their code (PROVINCE, DISTRICT, DISTRICT/SECTOR in capitals), so the schools keep their sector when
a name changes; names follow the service's spelling (the school data is matched to them ignoring case). Only the
boundaries change: no school data, plan or upload is touched.

Run (from backend/):  python -m etl.boundaries         (the API picks the new outlines up on restart or reload)
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models as M
from app.db import SessionLocal
from app.domain import analysis as A
from app.imports.sql import upsert
from app.services import boundaries as B

SOURCE = {"code": "ADMIN_BOUNDARIES", "name": "Administrative boundaries corrected (Education Mapping, MINEDUC GIS portal)"}
# Simplified on the server, a shape can cross itself: repaired, keeping its polygons only (the repair can leave lines)
GEOM = "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)), 3))"
# Country = the districts merged; the simplified shared borders leave hairline gaps, closed by a 0.0005 degree (~50 m)
# buffer out and back in, then simplified as much again (it only masks what is outside Rwanda on the map)
COUNTRY = ("UPDATE countries SET geom = (SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SimplifyPreserveTopology("
           "ST_Buffer(ST_Buffer(ST_Union(geom), 0.0005), -0.0005), 0.0005)), 3)) FROM districts WHERE geom IS NOT NULL) "
           "WHERE code = 'RWA'")


def slug(*parts: str) -> str:
    return "/".join(str(p).strip().upper() for p in parts)


def load(session: Session, b: B.Boundaries) -> dict:
    """Upsert provinces, districts and sectors with their outlines (inside the caller's transaction)."""
    upsert(session, M.DataSource.__table__, [{**SOURCE, "base_url": B.settings.boundaries_url}], "code")
    province_of = {d: p for p, ds in A.PROVINCES.items() for d in ds}
    provinces = upsert(session, M.Province.__table__, [{"code": slug(p), "name": p} for p in A.PROVINCES], "code")
    districts = upsert(session, M.District.__table__, [
        {"code": slug(f["properties"]["d"]),
         "province_id": provinces[slug(province_of.get(f["properties"]["d"], f["properties"]["p"]))],
         "name": f["properties"]["d"]}
        for f in b.districts], "code")
    upsert(session, M.Sector.__table__, [
        {"code": slug(f["properties"]["d"], f["properties"]["s"]), "district_id": districts[slug(f["properties"]["d"])],
         "name": f["properties"]["s"]}
        for f in b.sectors], "code")
    upsert(session, M.Country.__table__, [{"code": "RWA", "name": "Rwanda"}], "code")
    session.execute(text(f"UPDATE districts SET geom = {GEOM} WHERE code = :code"),
                    [{"g": json.dumps(f["geometry"]), "code": slug(f["properties"]["d"])} for f in b.districts])
    session.execute(text(f"UPDATE sectors SET geom = {GEOM} WHERE code = :code"),
                    [{"g": json.dumps(f["geometry"]), "code": slug(f["properties"]["d"], f["properties"]["s"])}
                     for f in b.sectors])
    session.execute(text(COUNTRY))
    return {"districts": len(b.districts), "sectors": len(b.sectors)}


def main() -> None:
    b = B.fetch()
    with SessionLocal() as session, session.begin():
        counts = load(session, b)
    print(f"boundaries from {B.settings.boundaries_url}: {counts['districts']} districts, {counts['sectors']} sectors "
          "(restart the API or POST /api/admin/reload to show them)")


if __name__ == "__main__":
    main()
