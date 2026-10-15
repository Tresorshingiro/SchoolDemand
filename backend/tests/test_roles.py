"""Roles (admin / viewer), portal accounts added at first sign-in, admin user management, audit log."""
import secrets

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app import models as M
from app import users as users_cli
from app.db import SessionLocal

from .conftest import PORTAL_PASSWORD, browser


def audit_rows(action: str, target: str) -> list[M.AuditLog]:
    with SessionLocal() as s:
        return list(s.scalars(select(M.AuditLog).where(M.AuditLog.action == action, M.AuditLog.target == target)
                              .order_by(M.AuditLog.id)))


def unique(prefix: str) -> str:
    return f"pytest-{prefix}-{secrets.token_hex(3)}"


def sign_in(app_, username: str, password: str = PORTAL_PASSWORD):
    c = browser(app_)
    return c, c.post("/api/auth/login", json={"username": username, "password": password})


# ---------------------------------------------------------------- portal accounts
def test_first_sign_in_adds_an_administrator(app_):
    name = unique("new")
    c, r = sign_in(app_, name.upper())                              # the portal ignores case
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["username"] == name and me["role"] == "admin" and me["email"] == f"{name}@example.test"
    assert c.get("/api/admin/users").status_code == 200              # an administrator straight away
    assert audit_rows("user.first_sign_in", name)[0].detail == {"role": "admin"}
    _, again = sign_in(app_, name)                                   # the same account the next time
    assert again.json()["id"] == me["id"] and len(audit_rows("user.first_sign_in", name)) == 1


def test_role_set_here_is_kept_at_the_next_sign_in(viewer, app_):
    _, r = sign_in(app_, viewer.username)
    assert r.json()["role"] == "viewer"


def test_name_comes_from_the_portal(client):
    me = client.get("/api/auth/me").json()
    assert me["username"] == "pytest-user" and me["full_name"] == "Pytest User"


def test_portal_refuses(app_):
    _, r = sign_in(app_, unique("someone"), "not-the-password")
    assert r.status_code == 401 and r.json()["detail"] == "Wrong username or password."
    _, r = sign_in(app_, "not-a-portal-user")
    assert r.status_code == 401


def test_portal_unreachable(app_, monkeypatch):
    from app.services import portal

    def down(username, password):
        raise HTTPException(503, portal.UNREACHABLE)

    monkeypatch.setattr(portal, "sign_in", down)
    _, r = sign_in(app_, unique("down"))
    assert r.status_code == 503 and "could not be reached" in r.json()["detail"]


def test_me_has_role(client):
    assert client.get("/api/auth/me").json()["role"] == "admin"


def test_viewer_fixture_is_a_viewer(viewer):
    assert viewer.client.get("/api/auth/me").json()["role"] == "viewer"


def test_cli_sets_the_role(make_client):
    u = make_client("viewer")
    users_cli.main(["role", u.username.upper(), "admin"])
    with SessionLocal() as s:
        assert s.scalar(select(M.User.role).where(M.User.username == u.username)) == "admin"


# ---------------------------------------------------------------- permissions
def test_viewer_reads_and_tries_plans(viewer):
    c = viewer.client
    assert c.get("/api/meta").status_code == 200
    assert c.post("/api/projection/run", json={"intake": {}}).status_code == 200
    assert c.get("/api/scenarios").status_code == 200


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/scenarios"), ("PUT", "/api/scenarios/999999"), ("DELETE", "/api/scenarios/999999"),
])  # ids that cannot exist: a broken check must not touch real plans
def test_viewer_cannot_save_plans(viewer, method, path):
    r = viewer.client.request(method, path, json={"name": "pytest viewer plan", "intake": {}})
    assert r.status_code == 403 and r.json()["detail"] == "Only an administrator can do this."


def test_admin_plan_changes_are_audited(client):
    name = unique("plan")
    r = client.post("/api/scenarios", json={"name": name, "intake": {}})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.put(f"/api/scenarios/{sid}", json={"name": name, "intake": {}}).status_code == 200
    assert client.delete(f"/api/scenarios/{sid}").status_code == 204
    for action in ("scenario.create", "scenario.update", "scenario.delete"):
        rows = audit_rows(action, name)
        assert len(rows) == 1 and rows[0].user_id is not None


def test_reload_needs_an_admin(anonymous, viewer):
    assert anonymous.post("/api/admin/reload").status_code == 401
    assert viewer.client.post("/api/admin/reload").status_code == 403


def test_admin_can_reload(client):
    r = client.post("/api/admin/reload")
    assert r.status_code == 200, r.text
    assert r.json()["class_groups"] > 0


# ---------------------------------------------------------------- admin users API
def test_accounts_are_not_created_or_given_passwords_here(client, viewer):
    assert client.post("/api/admin/users", json={"username": "x"}).status_code == 405
    assert client.post(f"/api/admin/users/{viewer.id}/password", json={"password": "x" * 10}).status_code == 404


def test_disable_and_enable(client, make_client, app_):
    u = make_client("viewer")
    assert client.patch(f"/api/admin/users/{u.id}", json={"is_active": False}).json()["is_active"] is False
    assert u.client.get("/api/meta").status_code == 401            # signed out at once
    _, r = sign_in(app_, u.username)                                # the portal password no longer gets in
    assert r.status_code == 403 and "disabled" in r.json()["detail"]
    assert client.patch(f"/api/admin/users/{u.id}", json={"is_active": True}).status_code == 200
    _, r = sign_in(app_, u.username)
    assert r.status_code == 200
    for action in ("user.disable", "user.enable"):
        assert len(audit_rows(action, u.username)) == 1


def test_change_role(client, make_client):
    u = make_client("viewer")
    r = client.patch(f"/api/admin/users/{u.id}", json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert u.client.get("/api/admin/users").status_code == 200     # the new admin can use the admin API
    assert audit_rows("user.role", u.username)[0].detail == {"from": "viewer", "to": "admin"}


def test_admin_cannot_remove_own_access(client):
    me = client.get("/api/auth/me").json()
    for body in ({"role": "viewer"}, {"is_active": False}):
        r = client.patch(f"/api/admin/users/{me['id']}", json=body)
        assert r.status_code == 409 and r.json()["detail"] == "You cannot remove your own admin access."


def test_last_active_admin_is_kept():
    """Two admins demoting each other at the same moment: the second one is refused (rows locked, then counted)."""
    from app.services.accounts import check_admin_removal

    with SessionLocal() as s:
        target = M.User(username=unique("last"), role="admin", is_active=True)
        s.add(target)
        s.flush()
        s.execute(update(M.User).where(M.User.role == "admin", M.User.id != target.id).values(is_active=False))
        with pytest.raises(HTTPException) as e:
            check_admin_removal(s, actor_id=-1, target=target)
        assert e.value.status_code == 409 and e.value.detail == "At least one active administrator is needed."
        s.rollback()  # nothing of this is kept


def test_unknown_user(client):
    assert client.patch("/api/admin/users/999999", json={"role": "viewer"}).status_code == 404


# ---------------------------------------------------------------- audit log API
def test_audit_log_newest_first_and_paged(client, make_client):
    u = make_client("viewer")
    for role in ("admin", "viewer", "admin"):
        assert client.patch(f"/api/admin/users/{u.id}", json={"role": role}).status_code == 200
    page = client.get("/api/admin/audit", params={"action": "user.role", "limit": 2}).json()
    assert len(page) == 2 and page[0]["id"] > page[1]["id"]
    assert page[0]["target"] == u.username and page[0]["detail"] == {"from": "viewer", "to": "admin"}
    assert page[0]["user_name"] == "Pytest User" and page[0]["user_username"] == "pytest-user"
    older = client.get("/api/admin/audit", params={"action": "user.role", "before": page[1]["id"]}).json()
    assert older and all(e["id"] < page[1]["id"] for e in older)
    assert older[0]["detail"] == {"from": "viewer", "to": "admin"}


def test_audit_log_filters(client):
    me = client.get("/api/auth/me").json()
    mine = client.get("/api/admin/audit", params={"user_id": me["id"], "limit": 5}).json()
    assert mine and all(e["user_id"] == me["id"] for e in mine)
    users_only = client.get("/api/admin/audit", params={"action": "user.", "limit": 20}).json()
    assert all(e["action"].startswith("user.") for e in users_only)


def test_audit_log_is_admin_only(viewer):
    assert viewer.client.get("/api/admin/audit").status_code == 403
