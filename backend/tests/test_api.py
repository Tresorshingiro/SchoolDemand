"""API tests against the loaded development data (Version 2.xlsx)."""
import pytest

from app.domain import analysis as A
from app.domain import dashboard as D
from app.domain import projection as P


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert body["data"]["class_groups"] > 0


def test_dataset_shapes(client):
    meta = client.get("/api/meta").json()
    assert [lvl["label"] for lvl in meta["levels"]] == A.LEVEL_ORDER
    levels = client.get("/api/school-levels").json()
    assert {"c", "n", "d", "s", "l", "st", "g", "ds", "a", "r", "gap", "y", "x"} <= set(levels[0])
    assert sum(r["st"] for r in levels) == meta["roster"]["students"]
    assert len(client.get("/api/grades").json()[0]) == len(meta["gradeColumns"])


def test_gzip(client):
    r = client.get("/api/school-levels", headers={"Accept-Encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"


@pytest.mark.parametrize("layer, count", [("country", 1), ("districts", 30), ("sectors", 416)])
def test_boundaries(client, layer, count):
    fc = client.get(f"/api/boundaries/{layer}").json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == count


def test_default_projection_matches_the_files(client):
    """The database-backed projection gives exactly what the source files give."""
    if not A.SOURCE_XLSX.exists():
        pytest.skip("source files not present")
    _, s, g, c = P.project(A.load_roster())
    expected = D.encode_projection(s, g, c)
    got = client.get("/api/projection/default").json()
    assert got["schools"] == expected["schools"]
    assert got["grades"] == expected["grades"]
    assert got["combos"] == expected["combos"]


def test_catchment_per_school_adds_up_to_the_default_plan(client):
    cfg = client.get("/api/projection/config").json()
    cat = cfg["catchment"]
    assert cat["years"] == P.YEARS[1:] and len(cat["rows"]) > 1000
    district = {r["c"]: r["d"] for r in client.get("/api/school-levels").json()}
    totals: dict[str, list[int]] = {}
    for code, *values in cat["rows"]:
        t = totals.setdefault(district[code], [0] * len(values))
        for k, v in enumerate(values):
            t[k] += v
    assert totals == cfg["population"]["N1"]  # the default plan is the district totals of the catchments


def test_custom_plan_changes_n1(client):
    cfg = client.get("/api/projection/config").json()
    gasabo = cfg["population"]["N1"]["Gasabo"]
    base = client.get("/api/projection/default").json()
    run = client.post("/api/projection/run", json={"intake": {"N1": {"Gasabo": [v + 1000 for v in gasabo]}}}).json()
    n1 = A.GRADE_ORDER.index("N1")
    total = lambda res, y: sum(r[3] for r in res["grades"] if r[0] == y and r[2] == n1)  # noqa: E731
    assert total(run, 2027) - total(base, 2027) == pytest.approx(1000, abs=40)  # shared to schools, rounded per school


@pytest.mark.parametrize("intake, message", [
    ({"N1": {"Atlantis": [1, 2, 3, 4]}}, "Unknown district"),
    ({"N1": {"Gasabo": [1, -2, 3, 4]}}, "whole numbers"),
    ({"N1": {"Gasabo": [1, 2]}}, "whole numbers"),
    ({"P1": {"Gasabo": [1, 2, 3, 4]}}, "Unknown entry grade"),
])
def test_bad_plans_are_rejected(client, intake, message):
    r = client.post("/api/projection/run", json={"intake": intake})
    assert r.status_code == 422 and message in r.json()["detail"]


def test_scenario_lifecycle(client):
    plan = {"N1": {"Gasabo": [111, 222, 333, 444]}}
    r = client.post("/api/scenarios", json={"name": "pytest scenario", "intake": plan})
    assert r.status_code == 201, r.text
    sc = r.json()
    try:
        assert len(sc["intake"]["N1"]) == 30  # districts left out take the default plan
        assert client.post("/api/scenarios", json={"name": "pytest scenario", "intake": plan}).status_code == 409
        got = client.get(f"/api/scenarios/{sc['id']}").json()
        assert got["intake"]["N1"]["Gasabo"] == [111, 222, 333, 444]
        up = client.put(f"/api/scenarios/{sc['id']}", json={"name": "pytest scenario 2", "intake": {"N1": {}}}).json()
        cfg = client.get("/api/projection/config").json()
        assert up["name"] == "pytest scenario 2" and up["intake"]["N1"]["Gasabo"] == cfg["population"]["N1"]["Gasabo"]
        assert any(s["id"] == sc["id"] for s in client.get("/api/scenarios").json())
    finally:
        assert client.delete(f"/api/scenarios/{sc['id']}").status_code == 204
    assert client.get(f"/api/scenarios/{sc['id']}").status_code == 404


# ---------------------------------------------------------------- sign-in
@pytest.mark.parametrize("method, path", [
    ("GET", "/api/meta"), ("GET", "/api/school-levels"), ("GET", "/api/boundaries/districts"),
    ("GET", "/api/projection/default"), ("POST", "/api/projection/run"), ("GET", "/api/scenarios"),
    ("POST", "/api/scenarios"), ("DELETE", "/api/scenarios/1"), ("GET", "/api/auth/me"),
])
def test_data_needs_sign_in(anonymous, method, path):
    assert anonymous.request(method, path, json={}).status_code == 401


def test_health_is_public(anonymous):
    assert anonymous.get("/api/health").status_code == 200


def test_me(client, test_user):
    me = client.get("/api/auth/me").json()
    assert me["email"] == test_user["email"] and me["full_name"] == "Pytest User"


def test_wrong_password(anonymous, test_user):
    r = anonymous.post("/api/auth/login", json={**test_user, "password": "not-the-password"})
    assert r.status_code == 401 and "Wrong email or password" in r.json()["detail"]
    r = anonymous.post("/api/auth/login", json={"email": "nobody@example.test", "password": "whatever-123"})
    assert r.status_code == 401


def test_email_is_case_insensitive_and_cookie_is_httponly(anonymous, test_user):
    r = anonymous.post("/api/auth/login", json={**test_user, "email": test_user["email"].upper()})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age" not in cookie  # ends with the browser
    remembered = anonymous.post("/api/auth/login", json={**test_user, "remember": True})
    assert "max-age=" in remembered.headers["set-cookie"].lower()


def test_logout_ends_the_session(anonymous, test_user):
    assert anonymous.post("/api/auth/login", json=test_user).status_code == 200
    assert anonymous.get("/api/auth/me").status_code == 200
    token = anonymous.cookies.get("sp_session")
    assert anonymous.post("/api/auth/logout").status_code == 204
    assert token and anonymous.get("/api/auth/me").status_code == 401
    # a copy of the old cookie no longer works either
    assert anonymous.get("/api/auth/me", headers={"Cookie": f"sp_session={token}"}).status_code == 401


def test_too_many_wrong_passwords(anonymous):
    body = {"email": "throttle@example.test", "password": "wrong-password"}
    codes = [anonymous.post("/api/auth/login", json=body).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_scenario_records_its_author(client):
    r = client.post("/api/scenarios", json={"name": "pytest author", "intake": {}})
    assert r.status_code == 201, r.text
    try:
        assert r.json()["created_by"] == "Pytest User"
    finally:
        client.delete(f"/api/scenarios/{r.json()['id']}")
