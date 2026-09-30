"""Data imports: upload, check, publish, history (sub-project 2)."""
from io import BytesIO

import pandas as pd
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import models as M
from app.db import SessionLocal
from tests import samples


# ---------------------------------------------------------------- Task 2: database
def test_existing_data_is_live():
    with SessionLocal() as s:
        live = s.scalars(select(M.ImportRun).where(M.ImportRun.is_live)).all()
        assert sorted((r.kind, r.academic_year or 0) for r in live) == [("catchment", 0), ("school_data", 2026)]
        assert all(r.status == "published" for r in live)
        assert s.scalar(select(func.count()).select_from(M.Classroom).where(M.Classroom.academic_year_id.is_(None))) == 0
        assert s.scalar(select(func.count()).select_from(M.DistrictPopulation)) == 0


# ---------------------------------------------------------------- Task 5: several school years in the API
def test_meta_lists_the_school_years(client):
    meta = client.get("/api/meta").json()
    assert meta["actualYears"] == [2026] and meta["baseYear"] == 2026
    assert meta["projectionYears"] == [2027, 2028, 2029, 2030]
    assert {s["kind"] for s in meta["sources"]} == {"school_data", "catchment"}


def test_year_parameter(client):
    assert client.get("/api/school-levels", params={"year": 2026}).json() == client.get("/api/school-levels").json()
    assert client.get("/api/meta", params={"year": 2026}).json()["baseYear"] == 2026
    r = client.get("/api/grades", params={"year": 2019})
    assert r.status_code == 404 and "2026" in r.json()["detail"]


def test_estimated_years_come_from_the_data(client):
    assert client.get("/api/projection/config").json()["estimated"] == {"N1": [2030]}


# ---------------------------------------------------------------- Task 6: the service
from app.imports import service as S  # noqa: E402


def _cleanup(run_id: int) -> None:
    with SessionLocal() as s:
        run = s.get(M.ImportRun, run_id)
        if run is not None and not run.is_live:
            s.delete(run)
        s.commit()


def test_upload_rules():
    with SessionLocal() as s:
        for kwargs, code, message in [
            (dict(kind="catchment", file_name="pytest.txt", content=b"x"), 422, "Upload an .xlsx or .csv file."),
            (dict(kind="catchment", file_name="pytest.csv", content=b""), 422, "The file is empty."),
            (dict(kind="school_data", file_name="pytest.csv", content=b"a"), 422, "Choose the school year of this file."),
            (dict(kind="catchment", file_name="pytest.csv", content=b"a" * (S.MAX_BYTES + 1)), 413,
             "The file is larger than 50 MB."),
        ]:
            with pytest.raises(HTTPException) as e:
                S.create_upload(s, academic_year=None, user=None, **kwargs)
            assert (e.value.status_code, e.value.detail) == (code, message)


def test_check_a_nisr_file_then_discard():
    content = samples.csv(pd.DataFrame({"district_name": ["Gasabo", "Atlantis"], "pop3_2027": [5, 6]}))
    with SessionLocal() as s:
        run = S.create_upload(s, kind="nisr_population", file_name="pytest-nisr.csv", content=content,
                              academic_year=None, user=None)
        run_id = run.id
    try:
        S.run_check(run_id)
        with SessionLocal() as s:
            run = s.get(M.ImportRun, run_id)
            assert run.status == "ready" and not S.can_publish(run)
            assert run.report["errors"][0]["code"] == "unknown_districts"
            assert S.issues_path(run).exists()
    finally:
        _cleanup(run_id)


def test_consequences():
    with SessionLocal() as s:
        assert S.consequence(s, M.ImportRun(kind="school_data", academic_year=2026)) == "Replaces the live 2026 data."
        assert S.consequence(s, M.ImportRun(kind="school_data", academic_year=2025)) == \
            "Adds 2025 as a past school year; the projection stays on 2026."
        assert S.consequence(s, M.ImportRun(kind="school_data", academic_year=2027)).startswith(
            "2027 becomes the base year. The projection moves to 2028-2031")


def test_interrupted_imports_are_marked_failed():
    with SessionLocal() as s:
        run = M.ImportRun(source_id=s.scalar(select(M.DataSource.id).where(M.DataSource.code == "NISR_POPULATION")),
                          kind="nisr_population", file_name="pytest-interrupted.csv", status="checking")
        s.add(run)
        s.commit()
        run_id = run.id
    try:
        assert S.mark_interrupted() >= 1
        with SessionLocal() as s:
            run = s.get(M.ImportRun, run_id)
            assert run.status == "failed" and "Interrupted" in run.error
    finally:
        _cleanup(run_id)


def test_publishing_the_same_file_again_is_refused():
    with SessionLocal() as s:
        live = S.live(s, "catchment")
        path = S.file_path(live)
        with pytest.raises(HTTPException) as e:
            S.create_upload(s, kind="catchment", file_name="again.xlsx", content=path.read_bytes(),
                            academic_year=None, user=None)
    assert e.value.status_code == 409 and e.value.detail.startswith("This file is already live (published ")


# ---------------------------------------------------------------- Task 7: the admin data API
from app.imports import worker  # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DATA = "/api/admin/data"


def upload(client, kind, name, content, year=None):
    data = {"kind": kind, **({"academic_year": str(year)} if year else {})}
    r = client.post(f"{DATA}/uploads", data=data,
                    files={"file": (name, content, XLSX if name.endswith("xlsx") else "text/csv")})
    assert r.status_code == 202, r.text
    worker.wait_idle()
    return client.get(f"{DATA}/imports/{r.json()['id']}").json()


def act(client, run_id, action):
    r = client.post(f"{DATA}/imports/{run_id}/{action}")
    assert r.status_code in (200, 202), r.text
    worker.wait_idle()
    return client.get(f"{DATA}/imports/{run_id}").json()


def test_data_routes_are_admin_only(viewer):
    for method, path in [("GET", "/sources"), ("GET", "/imports"), ("POST", "/uploads"), ("GET", "/templates/catchment")]:
        assert viewer.client.request(method, DATA + path).status_code == 403


def test_sources_and_templates(client):
    kinds = {k["kind"]: k for k in client.get(f"{DATA}/sources").json()}
    assert set(kinds) == {"school_data", "catchment", "nisr_population"}
    assert [r["academic_year"] for r in kinds["school_data"]["live"]] == [2026] and kinds["nisr_population"]["live"] == []
    assert kinds["school_data"]["connector"] == "not set up"
    r = client.get(f"{DATA}/templates/catchment")
    assert r.status_code == 200 and list(pd.read_excel(BytesIO(r.content)).columns) == [
        "school_code", "Pop2027", "Pop2028", "Pop2029", "Pop2030"]


def test_a_file_with_errors_cannot_be_published(client):
    run = upload(client, "school_data", "pytest-bad.csv", b"school_code,grade\n1,P1\n", 2027)
    assert run["status"] == "ready" and run["can_publish"] is False
    assert run["report"]["errors"][0]["code"] == "missing_columns"
    r = client.post(f"{DATA}/imports/{run['id']}/publish")
    assert r.status_code == 409 and r.json()["detail"].startswith("This import cannot be published: ")
    assert act(client, run["id"], "discard")["status"] == "discarded"


def test_nisr_publish_and_withdraw(client):
    before = client.get("/api/projection/config").json()["population"]["N1"]
    content = samples.csv(pd.DataFrame({"district_name": ["Gasabo", "Kicukiro"], "pop3_2027": [1000, 1100],
                                        "pop3_2028": [1200, 1300]}))
    run = upload(client, "nisr_population", "pytest-nisr.csv", content)
    assert run["can_publish"], run["report"]["errors"]
    first = client.post(f"{DATA}/imports/{run['id']}/publish")
    assert first.status_code == 202
    assert client.post(f"{DATA}/imports/{run['id']}/publish").status_code == 409   # a double click
    worker.wait_idle()
    try:
        cfg = client.get("/api/projection/config").json()
        assert cfg["population"]["N1"]["Gasabo"] == [1000, 1200, 1200, 1200]
        assert cfg["population"]["N1"]["Nyarugenge"] == before["Nyarugenge"]
        assert client.get(f"{DATA}/imports/{run['id']}").json()["is_live"] is True
    finally:
        assert act(client, run["id"], "withdraw")["status"] == "withdrawn"
    assert client.get("/api/projection/config").json()["population"]["N1"] == before


def test_catchment_publish_and_republish_the_previous(client):
    original = client.get(f"{DATA}/sources").json()
    previous = next(k for k in original if k["kind"] == "catchment")["live"][0]
    before = client.get("/api/projection/config").json()["catchment"]
    code = before["rows"][0][0]  # a pre-primary school of the projection
    df = samples.live_catchment()
    df.loc[df["school_code"] == code, "Pop2027"] = 9999
    run = upload(client, "catchment", "pytest-catchment.xlsx", samples.xlsx(df))
    assert run["consequence"].startswith("Replaces the live catchment figures")
    try:
        assert act(client, run["id"], "publish")["status"] == "published"
        rows = {r[0]: r[1:] for r in client.get("/api/projection/config").json()["catchment"]["rows"]}
        assert rows[code][0] == 9999
        assert client.get(f"{DATA}/imports/{previous['id']}").json()["status"] == "superseded"
    finally:
        assert act(client, previous["id"], "publish")["status"] == "published"   # the way back
    assert client.get("/api/projection/config").json()["catchment"] == before
    r = client.post(f"{DATA}/imports/{previous['id']}/withdraw")
    assert r.status_code == 409 and "catchment" in r.json()["detail"]


def test_a_new_school_year(client):
    before_2026 = client.get("/api/school-levels").json()
    run = upload(client, "school_data", "pytest-2027.xlsx", samples.xlsx(samples.school_file()), 2027)
    assert run["can_publish"], run["report"]["errors"]
    assert run["report"]["changes"]["against"] == 2026
    assert run["consequence"].startswith("2027 becomes the base year. The projection moves to 2028-2031")
    try:
        assert act(client, run["id"], "publish")["status"] == "published"
        meta = client.get("/api/meta").json()
        assert meta["actualYears"] == [2026, 2027] and meta["baseYear"] == 2027
        assert meta["projectionYears"] == [2028, 2029, 2030, 2031]
        assert client.get("/api/projection/config").json()["years"] == [2027, 2028, 2029, 2030, 2031]
        assert client.get("/api/school-levels", params={"year": 2026}).json() == before_2026
        assert {r["d"] for r in client.get("/api/school-levels").json()} == {"Nyarugenge"}
    finally:
        assert act(client, run["id"], "withdraw")["status"] == "withdrawn"
    meta = client.get("/api/meta").json()
    assert meta["actualYears"] == [2026] and meta["baseYear"] == 2026
    assert client.get("/api/school-levels").json() == before_2026


def test_history_lists_the_imports(client):
    rows = client.get(f"{DATA}/imports", params={"kind": "catchment"}).json()
    assert rows and all(r["kind"] == "catchment" for r in rows)
    assert rows == sorted(rows, key=lambda r: r["id"], reverse=True)
    live = next(r for r in rows if r["is_live"])
    r = client.get(f"{DATA}/imports/{live['id']}/file")
    assert r.status_code == 200 and len(r.content) == live["file_size"]


# ---------------------------------------------------------------- Task 8: plans of an older base year
def test_archived_plan_and_copy(client):
    r = client.post("/api/scenarios", json={"name": "pytest archived", "intake": {"N1": {"Gasabo": [1, 2, 3, 4]}}})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["base_year"] == 2026 and r.json()["archived"] is False
    with SessionLocal() as s:  # as if it had been saved when 2025 was the base year (years 2026-2029)
        s.execute(pg_insert(M.AcademicYear.__table__).values(year=2025).on_conflict_do_nothing())
        y2025 = s.scalar(select(M.AcademicYear.id).where(M.AcademicYear.year == 2025))
        s.execute(update(M.ProjectionScenario).where(M.ProjectionScenario.id == sid).values(base_year_id=y2025))
        g = s.scalar(select(M.Grade.id).where(M.Grade.code == "N1"))
        s.execute(update(M.ScenarioIntake).where(M.ScenarioIntake.scenario_id == sid, M.ScenarioIntake.grade_id == g)
                  .values(year=M.ScenarioIntake.year - 1))
        s.commit()
    copy_id = None
    try:
        got = client.get(f"/api/scenarios/{sid}").json()
        assert got["archived"] is True and got["base_year"] == 2025 and got["intake"]["N1"]["Gasabo"] == [1, 2, 3, 4]
        r = client.put(f"/api/scenarios/{sid}", json={"name": "pytest archived", "intake": {}})
        assert r.status_code == 409 and r.json()["detail"] == \
            "This plan was made for 2026-2029; copy it to the current years first."
        r = client.post(f"/api/scenarios/{sid}/copy", json={"name": "pytest archived copy"})
        assert r.status_code == 201, r.text
        copy_id = r.json()["id"]
        default = client.get("/api/projection/config").json()["population"]["N1"]["Gasabo"]
        # 2027-2029 keep the plan's values (2, 3, 4); 2030 takes the default plan
        assert r.json()["intake"]["N1"]["Gasabo"] == [2, 3, 4, default[3]] and r.json()["archived"] is False
    finally:
        client.delete(f"/api/scenarios/{sid}")
        if copy_id:
            client.delete(f"/api/scenarios/{copy_id}")
