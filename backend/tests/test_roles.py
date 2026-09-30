"""Roles (admin / viewer), forced password change, admin user management, audit log."""
import secrets

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import models as M
from app import users as users_cli
from app.db import SessionLocal


def audit_rows(action: str, target: str) -> list[M.AuditLog]:
    with SessionLocal() as s:
        return list(s.scalars(select(M.AuditLog).where(M.AuditLog.action == action, M.AuditLog.target == target)
                              .order_by(M.AuditLog.id)))


def unique(prefix: str) -> str:
    return f"pytest-{prefix}-{secrets.token_hex(3)}"


# ---------------------------------------------------------------- Task 1: roles stored
def test_me_has_role(client):
    me = client.get("/api/auth/me").json()
    assert me["role"] == "admin" and me["must_change_password"] is False


def test_viewer_fixture_is_a_viewer(viewer):
    assert viewer.client.get("/api/auth/me").json()["role"] == "viewer"


def test_cli_sets_the_role(make_client):
    u = make_client("viewer")
    users_cli.main(["role", u.email, "admin"])
    with SessionLocal() as s:
        assert s.scalar(select(M.User.role).where(M.User.email == u.email)) == "admin"


# ---------------------------------------------------------------- Task 2: permissions
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


def test_forced_password_change_blocks_everything_else(make_client, app_):
    u = make_client("viewer", must_change=True)
    r = u.client.get("/api/meta")
    assert r.status_code == 403 and r.json()["detail"] == "password_change_required"
    assert u.client.post("/api/projection/run", json={"intake": {}}).status_code == 403
    me = u.client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    # signing out and in again does not lift it
    assert u.client.post("/api/auth/logout").status_code == 204
    again = TestClient(app_)
    assert again.post("/api/auth/login", json={"email": u.email, "password": u.password}).status_code == 200
    assert again.get("/api/meta").json()["detail"] == "password_change_required"


def test_reload_needs_an_admin(anonymous, viewer):
    assert anonymous.post("/api/admin/reload").status_code == 401
    assert viewer.client.post("/api/admin/reload").status_code == 403


def test_admin_can_reload(client):
    r = client.post("/api/admin/reload")
    assert r.status_code == 200, r.text
    assert r.json()["class_groups"] > 0


# ---------------------------------------------------------------- Task 3: change your own password
def test_change_own_password(make_client, app_):
    u = make_client("viewer", must_change=True)
    other = TestClient(app_)  # a second browser of the same person
    assert other.post("/api/auth/login", json={"email": u.email, "password": u.password}).status_code == 200
    post = lambda cur, new: u.client.post("/api/auth/password", json={"current_password": cur, "new_password": new})  # noqa: E731

    r = post("wrong-password-1", "brand-new-pass-1")
    assert r.status_code == 400 and r.json()["detail"] == "The current password is wrong."
    r = post(u.password, u.password)
    assert r.status_code == 400 and r.json()["detail"] == "The new password must differ from the current one."
    r = post(u.password, "short")
    assert r.status_code == 422 and r.json()["detail"] == "The password must have at least 8 characters."

    assert post(u.password, "brand-new-pass-1").status_code == 204
    assert u.client.get("/api/meta").status_code == 200           # this browser stays signed in, no longer forced
    assert other.get("/api/auth/me").status_code == 401            # the other one is signed out
    fresh = TestClient(app_)
    assert fresh.post("/api/auth/login", json={"email": u.email, "password": "brand-new-pass-1"}).status_code == 200
    assert len(audit_rows("user.password_change", u.email)) == 1


# ---------------------------------------------------------------- Task 4: admin users API
def test_admin_creates_a_user(client, anonymous):
    email = f"{unique('created')}@Example.TEST"
    r = client.post("/api/admin/users", json={"email": f"  {email} ", "full_name": "   ", "role": "viewer",
                                               "password": "temp-pass-123"})
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["email"] == email.lower() and u["full_name"] is None
    assert u["role"] == "viewer" and u["must_change_password"] is True and u["is_active"] is True
    dup = client.post("/api/admin/users", json={"email": email.upper(), "role": "viewer", "password": "temp-pass-123"})
    assert dup.status_code == 409 and dup.json()["detail"] == f"{email.lower()} already has an account."
    assert anonymous.post("/api/auth/login", json={"email": email, "password": "temp-pass-123"}).status_code == 200
    assert anonymous.get("/api/meta").json()["detail"] == "password_change_required"
    assert any(x["email"] == email.lower() for x in client.get("/api/admin/users").json())
    assert audit_rows("user.create", email.lower())[0].detail == {"role": "viewer"}


@pytest.mark.parametrize("body, message", [
    ({"email": "not-an-email", "role": "viewer", "password": "temp-pass-123"}, "That is not an email address."),
    ({"email": "pytest-short@example.test", "role": "viewer", "password": "short12"},
     "The password must have at least 8 characters."),
])
def test_create_user_is_validated(client, body, message):
    r = client.post("/api/admin/users", json=body)
    assert r.status_code == 422 and r.json()["detail"] == message


def test_disable_enable_and_reset(client, make_client, app_):
    u = make_client("viewer")
    login = lambda pw: TestClient(app_).post("/api/auth/login", json={"email": u.email, "password": pw})  # noqa: E731
    assert client.patch(f"/api/admin/users/{u.id}", json={"is_active": False}).json()["is_active"] is False
    assert u.client.get("/api/meta").status_code == 401            # signed out at once
    assert login(u.password).status_code == 401
    assert client.patch(f"/api/admin/users/{u.id}", json={"is_active": True}).status_code == 200
    assert login(u.password).status_code == 200                    # same password works again

    assert client.post(f"/api/admin/users/{u.id}/password", json={"password": "reset-pass-123"}).status_code == 204
    assert login(u.password).status_code == 401
    fresh = TestClient(app_)
    assert fresh.post("/api/auth/login", json={"email": u.email, "password": "reset-pass-123"}).status_code == 200
    assert fresh.get("/api/meta").json()["detail"] == "password_change_required"
    for action in ("user.disable", "user.enable", "user.password_reset"):
        assert len(audit_rows(action, u.email)) == 1


def test_change_name_and_role(client, make_client):
    u = make_client("viewer")
    r = client.patch(f"/api/admin/users/{u.id}", json={"role": "admin", "full_name": " Renamed "})
    assert r.status_code == 200 and r.json()["role"] == "admin" and r.json()["full_name"] == "Renamed"
    assert u.client.get("/api/admin/users").status_code == 200     # the new admin can use the admin API
    assert audit_rows("user.role", u.email)[0].detail == {"from": "viewer", "to": "admin"}
    assert audit_rows("user.update", u.email)[0].detail == {"full_name": "Renamed"}


def test_admin_cannot_remove_own_access(client):
    me = client.get("/api/auth/me").json()
    for body in ({"role": "viewer"}, {"is_active": False}):
        r = client.patch(f"/api/admin/users/{me['id']}", json=body)
        assert r.status_code == 409 and r.json()["detail"] == "You cannot remove your own admin access."
    assert client.patch(f"/api/admin/users/{me['id']}", json={"full_name": "Pytest User"}).status_code == 200


def test_admin_resets_own_password(make_client):
    a = make_client("admin")
    assert a.client.post(f"/api/admin/users/{a.id}/password", json={"password": "own-reset-123"}).status_code == 204
    assert a.client.get("/api/auth/me").status_code == 401          # every session ended, including this one


def test_last_active_admin_is_kept():
    """Two admins demoting each other at the same moment: the second one is refused (rows locked, then counted)."""
    from app.services.accounts import check_admin_removal

    with SessionLocal() as s:
        target = M.User(email=f"{unique('last')}@example.test", role="admin", password_hash="x", is_active=True)
        s.add(target)
        s.flush()
        s.execute(update(M.User).where(M.User.role == "admin", M.User.id != target.id).values(is_active=False))
        with pytest.raises(HTTPException) as e:
            check_admin_removal(s, actor_id=-1, target=target)
        assert e.value.status_code == 409 and e.value.detail == "At least one active administrator is needed."
        s.rollback()  # nothing of this is kept


def test_unknown_user(client):
    assert client.patch("/api/admin/users/999999", json={"full_name": "x"}).status_code == 404


# ---------------------------------------------------------------- Task 5: audit log API
def test_audit_log_newest_first_and_paged(client, make_client):
    u = make_client("viewer")
    for name in ("One", "Two", "Three"):
        assert client.patch(f"/api/admin/users/{u.id}", json={"full_name": name}).status_code == 200
    page = client.get("/api/admin/audit", params={"action": "user.update", "limit": 2}).json()
    assert len(page) == 2 and page[0]["id"] > page[1]["id"]
    assert page[0]["target"] == u.email and page[0]["detail"] == {"full_name": "Three"}
    assert page[0]["user_name"] == "Pytest User" and page[0]["user_email"] == "pytest-user@example.test"
    older = client.get("/api/admin/audit", params={"action": "user.update", "before": page[1]["id"]}).json()
    assert older and all(e["id"] < page[1]["id"] for e in older)
    assert older[0]["detail"] == {"full_name": "One"}


def test_audit_log_filters(client):
    me = client.get("/api/auth/me").json()
    mine = client.get("/api/admin/audit", params={"user_id": me["id"], "limit": 5}).json()
    assert mine and all(e["user_id"] == me["id"] for e in mine)
    users_only = client.get("/api/admin/audit", params={"action": "user.", "limit": 20}).json()
    assert all(e["action"].startswith("user.") for e in users_only)


def test_audit_log_is_admin_only(viewer):
    assert viewer.client.get("/api/admin/audit").status_code == 403
