"""Administrative boundaries from Education Mapping's feature service (services/boundaries.py), against a fake
service (no network access), and the school data matched to them ignoring case."""
import pytest

from app.domain import analysis as A
from app.imports.checks import check_school_data
from app.services import boundaries as B
from tests.test_import_checks import context, school_file

URL = "https://portal.test/server/rest/services/Admin/FeatureServer"
SQUARE = {"type": "Polygon", "coordinates": [[[30.0, -1.9], [30.1, -1.9], [30.1, -2.0], [30.0, -2.0], [30.0, -1.9]]]}
DISTRICTS = [(d, p) for p, ds in A.PROVINCES.items() for d in ds]  # the 30 districts


def sectors(n: int = 416) -> list[tuple[str, str]]:
    return [(DISTRICTS[k % 30][0], f"Sector {k}") for k in range(n)]


class FakeService:
    """Answers layer queries in pages of `page` features; `geometry` None makes shapeless features."""

    def __init__(self, districts=DISTRICTS, sector_rows=None, page=1000, geometry=SQUARE):
        self.rows = {1: [{"district": d, "province": p} for d, p in districts],
                     2: [{"district": d, "sector": s} for d, s in (sector_rows if sector_rows is not None else sectors())]}
        self.page, self.geometry, self.calls = page, geometry, []

    def __call__(self, url: str, params: dict) -> dict:
        self.calls.append((url, params))
        layer = int(url.removeprefix(URL + "/").split("/")[0])
        start, count = params["resultOffset"], min(params["resultRecordCount"], self.page)
        chunk = self.rows[layer][start:start + count]
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": self.geometry, "properties": r}
                                                          for r in chunk],
                "properties": {"exceededTransferLimit": start + count < len(self.rows[layer])}}


def test_fetch_reads_districts_and_sectors():
    b = B.fetch(URL, 0.0002, get=FakeService())
    assert len(b.districts) == 30 and len(b.sectors) == 416
    assert b.districts[0]["properties"] == {"d": DISTRICTS[0][0], "p": DISTRICTS[0][1]}
    assert b.sectors[0]["properties"] == {"d": DISTRICTS[0][0], "s": "Sector 0"}


def test_fetch_pages_through_a_layer():
    fake = FakeService(page=100)
    assert len(B.fetch(URL, 0, get=fake).sectors) == 416
    sector_calls = [p for u, p in fake.calls if u.endswith("/2/query")]
    assert [p["resultOffset"] for p in sector_calls] == [0, 100, 200, 300, 400]


def test_fetch_asks_for_simplified_shapes_in_wgs84():
    fake = FakeService()
    B.fetch(URL, 0.0002, get=fake)
    params = fake.calls[0][1]
    assert params["outSR"] == 4326 and params["maxAllowableOffset"] == 0.0002 and params["f"] == "geojson"
    fake = FakeService()
    B.fetch(URL, 0, get=fake)
    assert "maxAllowableOffset" not in fake.calls[0][1]


def test_names_are_tidied():
    rows = sectors()
    rows[0] = (rows[0][0], "  Gitega \t ")
    assert B.fetch(URL, 0, get=FakeService(sector_rows=rows)).sectors[0]["properties"]["s"] == "Gitega"


@pytest.mark.parametrize("change, message", [
    (dict(sector_rows=sectors(400)), "400 sectors"),
    (dict(districts=DISTRICTS[:29]), "29 districts"),
    (dict(geometry=None), "without a shape"),
    (dict(districts=[("Kigali", "Kigali Province")] + DISTRICTS[1:]), "unknown provinces"),
    (dict(sector_rows=[sectors()[0], (sectors()[0][0], "SECTOR 0")] + sectors()[2:]), "listed twice"),
])
def test_unexpected_boundaries_are_refused(change, message):
    with pytest.raises(B.BoundariesUnavailable, match=message):
        B.fetch(URL, 0, get=FakeService(**change))


def test_refused_query_is_unavailable():
    def refuse(url, params):
        return {"error": {"code": 400, "message": "Invalid query"}}

    with pytest.raises(B.BoundariesUnavailable, match="refused"):
        B.fetch(URL, 0, get=refuse)


def test_place_key_ignores_case_and_spacing():
    assert B.place_key("Ngororero", "BWIRA") == B.place_key(" Ngororero ", "Bwira")


def test_school_data_sector_in_capitals_is_known():
    df = school_file()
    df["sector"] = "GITEGA"  # the boundaries say Gitega
    _, rep = check_school_data(df, 2027, context())
    assert "unknown_sector" not in {w["code"] for w in rep.warnings}
