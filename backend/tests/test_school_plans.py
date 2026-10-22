"""Saved new-school plans (needs the database)."""
import secrets

from sqlalchemy import select, update

from app import models as M
from app.db import SessionLocal

from .test_new_schools_api import body
from .test_roles import audit_rows


def plan(name: str | None = None, **school) -> dict:
    return {"name": name or f"pytest-schools-{secrets.token_hex(3)}", "schools": body(**school)["schools"]}


def test_admin_saves_and_reads_back(client):
    r = client.post("/api/school-plans", json=plan())
    assert r.status_code == 201, r.text
    p = client.get(f"/api/school-plans/{r.json()['id']}").json()
    assert p["plan_schools"][0]["levels"] == {"PRI": 12} and p["schools"] == 1 and p["archived"] is False
    years = p["summary"]["levels"]["Primary"]["Kicukiro"]
    assert set(years) == {"2027", "2028", "2029", "2030"}
    short_before, short_after = years["2028"]["short"]
    assert short_after <= short_before and years["2027"]["short"][0] == years["2027"]["short"][1]
    assert any(x["id"] == p["id"] for x in client.get("/api/school-plans").json())
    assert client.delete(f"/api/school-plans/{p['id']}").status_code == 204


def test_viewer_reads_but_cannot_save(viewer, client):
    pid = client.post("/api/school-plans", json=plan()).json()["id"]
    assert viewer.client.get(f"/api/school-plans/{pid}").status_code == 200
    assert viewer.client.post("/api/school-plans", json=plan()).status_code == 403
    assert viewer.client.put(f"/api/school-plans/{pid}", json=plan()).status_code == 403
    assert viewer.client.delete(f"/api/school-plans/{pid}").status_code == 403
    client.delete(f"/api/school-plans/{pid}")


def test_changes_are_audited_and_names_unique(client):
    p = plan()
    pid = client.post("/api/school-plans", json=p).json()["id"]
    assert client.post("/api/school-plans", json=p).status_code == 409
    assert client.put(f"/api/school-plans/{pid}", json={**p, "schools": body(opening_year=2029)["schools"]}).status_code == 200
    client.delete(f"/api/school-plans/{pid}")
    for action in ("school_plan.create", "school_plan.update", "school_plan.delete"):
        rows = audit_rows(action, p["name"])
        assert len(rows) == 1 and rows[0].user_id is not None


def test_bad_school_is_refused(client):
    assert client.post("/api/school-plans", json=plan(latitude=-2.2, longitude=29.2)).status_code == 422


def test_archived_plan_is_read_only_and_copies_forward(client):
    p = plan()
    pid = client.post("/api/school-plans", json=p).json()["id"]
    with SessionLocal() as s:  # pretend it was made for 2025: its years were 2026-2029
        y2025 = s.scalar(select(M.AcademicYear.id).where(M.AcademicYear.year == 2025))
        s.execute(update(M.SchoolPlan).where(M.SchoolPlan.id == pid).values(base_year_id=y2025))
        s.execute(update(M.PlannedSchoolRow).where(M.PlannedSchoolRow.school_plan_id == pid).values(opening_year=2026))
        s.commit()
    assert client.get(f"/api/school-plans/{pid}").json()["archived"] is True
    assert client.put(f"/api/school-plans/{pid}", json=p).status_code == 409
    r = client.post(f"/api/school-plans/{pid}/copy", json={"name": p["name"] + "-copy"})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["archived"] is False and c["plan_schools"][0]["opening_year"] == 2027   # the first projected year
    for i in (pid, c["id"]):
        client.delete(f"/api/school-plans/{i}")
