# Roles and Admin Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two roles (admin, viewer), forced password change for accounts an admin creates, an admin users API with an audit log, and an `/admin` portal (Users, Activity) in the React app; viewers can try plans but not save them.

**Architecture:** A `role` column and `must_change_password` flag on `users`, an `audit_log` table (migration `0003`). FastAPI dependencies layer the checks: `signed_in_user` (any session) → `current_user` (blocks users who must change their password) → `require_admin`. A new `routers/admin.py` serves user management and the audit log. The React app gets `role` in the auth context, a change-password page, a user menu, read-only saved-plan controls for viewers, and a lazy-loaded `src/admin/` area with its own sidebar layout.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17 + PostGIS (Docker, localhost:5433), pytest + TestClient; React 18, TypeScript, React Router 7, Tailwind 3, lucide-react. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-29-roles-admin-portal-design.md`

## Global Constraints

- Roles are exactly `admin` and `viewer`; the migration makes every existing account a `viewer`.
- Passwords: at least 8 characters (existing `MIN_PASSWORD = 8`); emails trimmed and lower-cased (existing `normalize_email`).
- API error messages are plain sentences in `detail` (a string), shown as-is by the dashboard. Exact texts:
  - `"Only an administrator can do this."` (403)
  - `"password_change_required"` (403, a code the frontend recognises)
  - `"You cannot remove your own admin access."` (409)
  - `"At least one active administrator is needed."` (409)
  - `"<email> already has an account."` (409)
  - `"That is not an email address."` (422)
  - `"The password must have at least 8 characters."` (422)
  - `"The current password is wrong."` (400)
  - `"The new password must differ from the current one."` (400)
- Viewer note in the planner, verbatim: *"You can try plans; only an administrator can save them."*
- Show-once password text, verbatim: *"Give this password to <name>; they will choose their own at first sign-in."*
- One uvicorn worker (unchanged). Commands run from `backend/` with `.venv\Scripts\python`; the dev database must be up (`docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d db`).
- File edits with the Edit tool (or Python with asserts) — never PowerShell bulk find/replace (it corrupted files in this repo before).
- Every task keeps the whole backend suite green: `.venv\Scripts\python -m pytest -q` (≈3 min) at the end of each backend task.

## Review Focus

- An admin types an email with spaces / capitals when adding a user → stored trimmed and lower-case, and the person signs in with any casing (test in Task 4).
- A 7-character password in the admin form → a one-sentence 422 message, not Pydantic's error list, so the page can show it (test in Task 4).
- A user who must change their password signs out and in again → still forced; the flag survives new sessions (test in Task 2).
- An admin resets their **own** password → all their sessions end and they must choose a new one; nothing else breaks (test in Task 4).
- A disabled user is re-enabled → can sign in again with the same password (test in Task 4).

---

## File Structure

Backend (`backend/`):

| File | Responsibility |
|---|---|
| `alembic/versions/0003_roles.py` (new) | `users.role`, `users.must_change_password`, `users.created_by_id`, table `audit_log` |
| `app/models.py` (modify) | `User` columns, new `AuditLog` model |
| `app/schemas.py` (modify) | `UserOut` + role fields; admin request / response models |
| `app/services/auth.py` (modify) | `session_user`, `signed_in_user`, `current_user` gate, `require_admin`, `end_user_sessions` |
| `app/services/audit.py` (new) | `audit(...)` — add one `audit_log` row |
| `app/services/accounts.py` (new) | `check_admin_removal(...)`, `hash_or_422(...)`, `valid_email(...)` |
| `app/routers/auth.py` (modify) | `/auth/me` on `signed_in_user`, new `POST /auth/password` |
| `app/routers/admin.py` (new) | `/admin/users…`, `/admin/audit` |
| `app/routers/scenarios.py` (modify) | writes need `require_admin`, audited |
| `app/routers/system.py` (modify) | `/admin/reload`: admin token **or** signed-in admin |
| `app/main.py` (modify) | include `admin.router` |
| `app/users.py` (modify) | `create --admin`, `role EMAIL admin|viewer`, role in `list` |
| `tests/conftest.py` (modify) | admin test user, `make_client` factory, `viewer` fixture, cleanup |
| `tests/test_roles.py` (new) | all tests of this plan |
| `tests/test_api.py` (modify) | replace `test_reload_is_protected` |

Frontend (`dashboard/src/`):

| File | Responsibility |
|---|---|
| `api.ts` (modify) | `PATCH`; `PASSWORD_REQUIRED` event on `password_change_required` |
| `auth.tsx` (modify) | `role`, `must_change_password`, `refresh`, `isAdmin`, redirect to `/account/password`, `RequireAdmin` |
| `site/ChangePasswordPage.tsx` (new) | change-password form (forced or voluntary) |
| `UserMenu.tsx` (new) | header menu: Change password, Admin portal, Sign out |
| `App.tsx` (modify) | use `UserMenu` |
| `main.tsx` (modify) | routes `/account/password`, `/admin/*` |
| `components/IntakePlanner.tsx`, `components/ProjectionPage.tsx` (modify) | read-only plan bar for viewers |
| `admin/api.ts` (new) | typed admin API calls |
| `admin/AdminApp.tsx` (new) | admin routes |
| `admin/AdminLayout.tsx` (new) | sidebar / mobile top bar shell |
| `admin/ActivityPage.tsx` (new) | audit log page |
| `admin/password.ts` (new) | temporary password generator |
| `admin/UserPanel.tsx` (new) | add / edit / reset-password side panel |
| `admin/UsersPage.tsx` (new) | users table, filters, row menu, show-once password |

---

### Task 1: Roles in the database, CLI and test fixtures

**Files:**
- Create: `backend/alembic/versions/0003_roles.py`, `backend/tests/test_roles.py`
- Modify: `backend/app/models.py` (User class, add AuditLog), `backend/app/schemas.py:21-25` (UserOut), `backend/app/users.py`, `backend/tests/conftest.py`

**Interfaces:**
- Produces: `M.User.role: str` (`"admin"|"viewer"`), `M.User.must_change_password: bool`, `M.User.created_by_id: int|None`; `M.AuditLog(id, at, user_id, action, target, detail)`; `UserOut` adds `role`, `must_change_password`; conftest fixtures `make_client(role="viewer", must_change=False) -> SimpleNamespace(client, email, password, id)`, `viewer` (session-scoped `make_client("viewer")`), `test_user` is now an **admin**; CLI `python -m app.users role EMAIL admin|viewer`, `create EMAIL --name N --admin`.

- [ ] **Step 1: Write the failing tests** — create `backend/tests/test_roles.py`:

```python
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
```

- [ ] **Step 2: Update `backend/tests/conftest.py`** — replace the file with:

```python
"""Integration tests: they need the database with an import loaded (python -m etl.load_version2)."""
import secrets
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app import models as M
from app.db import SessionLocal, engine
from app.services.auth import hash_password

TEST_EMAIL, TEST_PASSWORD = "pytest-user@example.test", "pytest-password-123"
PYTEST_EMAILS = "pytest-%@example.test"  # every account the tests create matches this


def _database_ready() -> bool:
    try:
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT count(*) FROM import_runs WHERE status = 'success'")).scalar())
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session", autouse=True)
def _remove_test_accounts():
    """Accounts made by the tests (fixtures or the admin API) are removed at the end."""
    yield
    if _database_ready():
        with SessionLocal() as s:
            s.execute(delete(M.User).where(M.User.email.like(PYTEST_EMAILS)))
            s.commit()


@pytest.fixture(scope="session")
def test_user():
    """A throw-away administrator account."""
    with SessionLocal() as s:
        s.execute(delete(M.User).where(M.User.email == TEST_EMAIL))
        s.add(M.User(email=TEST_EMAIL, full_name="Pytest User", password_hash=hash_password(TEST_PASSWORD),
                     is_active=True, role="admin"))
        s.commit()
    return {"email": TEST_EMAIL, "password": TEST_PASSWORD}


@pytest.fixture(scope="session")
def app_():
    if not _database_ready():
        pytest.skip("database not reachable or not loaded — start it and run python -m etl.load_version2")
    from app.main import app

    with TestClient(app):  # runs the startup once: loads the data into memory
        yield app


@pytest.fixture(scope="session")
def client(app_, test_user):
    """Signed in as the test administrator (the session cookie stays in the client)."""
    c = TestClient(app_)  # no `with`: the data is already loaded by app_
    r = c.post("/api/auth/login", json=test_user)
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="session")
def make_client(app_):
    """Factory: a new throw-away account, signed in. make_client("admin" | "viewer", must_change=False)."""
    def make(role: str = "viewer", must_change: bool = False, password: str = "pytest-password-123") -> SimpleNamespace:
        email = f"pytest-{role}-{secrets.token_hex(4)}@example.test"
        with SessionLocal() as s:
            s.add(M.User(email=email, full_name=f"Pytest {role}", role=role, must_change_password=must_change,
                         password_hash=hash_password(password), is_active=True))
            s.commit()
            user_id = s.scalar(select(M.User.id).where(M.User.email == email))
        c = TestClient(app_)
        r = c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return SimpleNamespace(client=c, email=email, password=password, id=user_id)

    return make


@pytest.fixture(scope="session")
def viewer(make_client):
    """A signed-in viewer shared by the tests that only read."""
    return make_client("viewer")


@pytest.fixture
def anonymous(app_):
    """Not signed in."""
    return TestClient(app_)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py -q`
Expected: errors — `TypeError: 'role' is an invalid keyword argument for User` (and `AttributeError: ... AuditLog`).

- [ ] **Step 4: Add the migration** — create `backend/alembic/versions/0003_roles.py`:

```python
"""roles (admin / viewer), forced password change, audit log

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # every existing account becomes a viewer; promote with: python -m app.users role EMAIL admin
    op.add_column('users', sa.Column('role', sa.String(length=10), server_default='viewer', nullable=False,
                                     comment='admin or viewer'))
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('users', sa.Column('created_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_created_by_id', 'users', 'users', ['created_by_id'], ['id'], ondelete='SET NULL')
    op.create_check_constraint('ck_users_role', 'users', "role IN ('admin', 'viewer')")
    op.create_table('audit_log',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('target', sa.String(length=200), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_at', 'audit_log', [sa.text('at DESC')])


def downgrade() -> None:
    op.drop_index('ix_audit_log_at', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.drop_constraint('fk_users_created_by_id', 'users', type_='foreignkey')
    op.drop_column('users', 'created_by_id')
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'role')
```

- [ ] **Step 5: Update the models** — in `backend/app/models.py`: add `CheckConstraint` and `false` to the `sqlalchemy` import (`from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, false, func,)`), extend the docstring's additions line with `` `audit_log` (who changed what) ``, and replace the `User` class with:

```python
class User(Base):
    """A person who can sign in to the dashboard. Admins manage accounts and saved plans; viewers only read."""
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'viewer')", name="ck_users_role"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, comment="stored in lower case")
    full_name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255), comment="argon2id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(10), default="viewer", server_default="viewer", comment="admin or viewer")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

and add after `UserSession`:

```python
class AuditLog(Base):
    """Who changed what: accounts, saved plans (and, later, the data)."""
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_at", text("at DESC")),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40), comment="user.create, user.role, scenario.delete ...")
    target: Mapped[str] = mapped_column(String(200), comment="e.g. the user's email or the plan name")
    detail = mapped_column(JSONB, nullable=True)
```

(also add `text` to the `sqlalchemy` import).

- [ ] **Step 6: Add the role to `UserOut`** — in `backend/app/schemas.py` replace `UserOut` with:

```python
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str | None
    role: str
    must_change_password: bool
```

- [ ] **Step 7: Extend the CLI** — in `backend/app/users.py`: add to the docstring
  `python -m app.users create jane@mineduc.gov.rw --name "Jane Doe" --admin   an administrator` and
  `python -m app.users role jane@mineduc.gov.rw admin                        admin or viewer`; then

  after `create.add_argument("--name", …)` add:
  ```python
    create.add_argument("--admin", action="store_true", help="make the account an administrator (default: viewer)")
    role = sub.add_parser("role", help="make an account an administrator or a viewer")
    role.add_argument("email")
    role.add_argument("role", choices=["admin", "viewer"])
  ```
  in `create`, build the user with the role:
  ```python
            session.add(M.User(email=email, full_name=args.name, password_hash=_ask_password(), is_active=True,
                               role="admin" if args.admin else "viewer"))
            print(f"Created {email} ({'admin' if args.admin else 'viewer'}).")
  ```
  add a branch before the final `else:`:
  ```python
        elif args.command == "role":
            user = _user(session, args.email)
            user.role = args.role
            print(f"{user.email} is now {'an administrator' if args.role == 'admin' else 'a viewer'}.")
  ```
  and in `list` print the role: replace the `print(f"{u.email:40} …")` line with
  ```python
                print(f"{u.email:40} {u.full_name or '':30} {u.role:7} {'active' if u.is_active else 'disabled':9} last sign-in {last}")
  ```

- [ ] **Step 8: Apply the migration and run the tests**

Run: `.venv\Scripts\python -m alembic upgrade head` → `Running upgrade 0002 -> 0003`.
Run: `.venv\Scripts\python -m pytest tests/test_roles.py -q` → `3 passed`.
Run: `.venv\Scripts\python -m pytest -q` → all pass (the scenario tests still pass: the test user is an admin and nothing checks roles yet).

- [ ] **Step 9: Commit**

```powershell
git add backend/alembic/versions/0003_roles.py backend/app/models.py backend/app/schemas.py backend/app/users.py backend/tests/conftest.py backend/tests/test_roles.py
git commit -m "Roles: users.role, must_change_password, audit_log table; CLI role command; test fixtures"
```

---

### Task 2: Permission checks — admin-only writes, forced password change, audit helper, reload

**Files:**
- Create: `backend/app/services/audit.py`
- Modify: `backend/app/services/auth.py` (from `def current_user` to the end), `backend/app/routers/auth.py` (`/me`), `backend/app/routers/scenarios.py` (create / update / delete), `backend/app/routers/system.py` (reload), `backend/tests/test_api.py:100-101`, `backend/tests/test_roles.py`

**Interfaces:**
- Consumes: Task 1 models and fixtures.
- Produces: `auth.session_user(request, session) -> M.User | None`; `auth.signed_in_user` (dependency, 401); `auth.current_user` (dependency, + 403 `password_change_required`); `auth.require_admin` (dependency, + 403); `auth.PASSWORD_CHANGE_REQUIRED = "password_change_required"`; `auth.end_user_sessions(session, user_id: int, keep_token: str | None = None) -> None`; `audit.audit(session, user: M.User | None, action: str, target: str, detail: dict | None = None) -> None` (adds, does not commit).

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_roles.py`:

```python
# ---------------------------------------------------------------- Task 2: permissions
def test_viewer_reads_and_tries_plans(viewer):
    c = viewer.client
    assert c.get("/api/meta").status_code == 200
    assert c.post("/api/projection/run", json={"intake": {}}).status_code == 200
    assert c.get("/api/scenarios").status_code == 200


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/scenarios"), ("PUT", "/api/scenarios/1"), ("DELETE", "/api/scenarios/1"),
])
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
```

and in `backend/tests/test_api.py` delete `test_reload_is_protected` (lines 100-101; replaced by the two reload tests above).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py -q`
Expected: FAIL — viewers get 201 / 404 instead of 403, no `password_change_required`, no audit rows, reload with a session answers 403 "Reload is disabled…".

- [ ] **Step 3: Create `backend/app/services/audit.py`:**

```python
"""The audit log: one row per change an administrator (or a user to their own account) makes."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models as M


def audit(session: Session, user: M.User | None, action: str, target: str, detail: dict | None = None) -> None:
    """Add an entry in the caller's transaction (committed with the change it describes)."""
    session.add(M.AuditLog(user_id=user.id if user else None, action=action, target=target[:200], detail=detail))
```

- [ ] **Step 4: Layer the checks in `backend/app/services/auth.py`** — replace `def current_user(...)` (the whole function, to the end of the file) with:

```python
def end_user_sessions(session: Session, user_id: int, keep_token: str | None = None) -> None:
    """Sign a user out everywhere (except the browser holding `keep_token`)."""
    q = delete(M.UserSession).where(M.UserSession.user_id == user_id)
    if keep_token:
        q = q.where(M.UserSession.token_hash != _token_hash(keep_token))
    session.execute(q)


def session_user(request: Request, session: Session) -> M.User | None:
    """The active user of the request's session cookie, or None."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    return session.scalar(
        select(M.User).join(M.UserSession, M.UserSession.user_id == M.User.id)
        .where(M.UserSession.token_hash == _token_hash(token), M.UserSession.expires_at > func.now(), M.User.is_active)
    )


def signed_in_user(request: Request, session: Session = Depends(get_session)) -> M.User:
    """FastAPI dependency: the signed-in user, or 401 — even one who must still change their password."""
    user = session_user(request, session)
    if user is None:
        raise HTTPException(401, "Please sign in.")
    return user


PASSWORD_CHANGE_REQUIRED = "password_change_required"  # the dashboard recognises this detail


def current_user(user: M.User = Depends(signed_in_user)) -> M.User:
    """FastAPI dependency: the signed-in user; 403 until a temporary password has been changed."""
    if user.must_change_password:
        raise HTTPException(403, PASSWORD_CHANGE_REQUIRED)
    return user


def require_admin(user: M.User = Depends(current_user)) -> M.User:
    """FastAPI dependency: the signed-in administrator; 403 for viewers."""
    if user.role != "admin":
        raise HTTPException(403, "Only an administrator can do this.")
    return user
```

- [ ] **Step 5: `/auth/me` answers users who must change their password** — in `backend/app/routers/auth.py` change the `me` route to:

```python
@router.get("/me", response_model=UserOut, summary="The signed-in user (401 when not signed in)")
def me(user: M.User = Depends(auth.signed_in_user)):
    return user
```

- [ ] **Step 6: Admin-only plan changes** — in `backend/app/routers/scenarios.py`:
  - imports: `from ..services.auth import current_user, require_admin` and `from ..services.audit import audit`;
  - `create_scenario`: change the parameter `user: M.User = Depends(current_user)` to `user: M.User = Depends(require_admin)` and add `audit(session, user, "scenario.create", s.name)` right before `session.commit()`;
  - `update_scenario`: add the parameter `user: M.User = Depends(require_admin)` and `audit(session, user, "scenario.update", s.name)` right before `session.commit()`;
  - `delete_scenario`: replace with

```python
@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, session: Session = Depends(get_session),
                    user: M.User = Depends(require_admin)) -> Response:
    s = _get(session, scenario_id)
    audit(session, user, "scenario.delete", s.name)
    session.delete(s)
    session.commit()
    return Response(status_code=204)
```

- [ ] **Step 7: Reload by token or signed-in admin** — replace `backend/app/routers/system.py`'s `reload` with (add imports `import secrets`, `from fastapi import Depends, Request`, `from sqlalchemy.orm import Session`, `from ..db import engine, get_session`, `from ..services import auth`):

```python
@router.post("/admin/reload", summary="Re-read the database after an import (signed-in admin, or X-Admin-Token header)")
async def reload(request: Request, x_admin_token: str = Header(""), session: Session = Depends(get_session)) -> dict:
    token_ok = bool(settings.admin_token) and secrets.compare_digest(x_admin_token, settings.admin_token)
    if not token_ok:
        user = auth.session_user(request, session)
        if user is None:
            raise HTTPException(401, "Sign in as an administrator, or send the X-Admin-Token header.")
        if user.role != "admin" or user.must_change_password:
            raise HTTPException(403, "Only an administrator can do this.")
    return await run_in_threadpool(store.load)
```

- [ ] **Step 8: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py -q` → all pass.
Run: `.venv\Scripts\python -m pytest -q` → all pass.

- [ ] **Step 9: Commit**

```powershell
git add backend/app/services/audit.py backend/app/services/auth.py backend/app/routers/auth.py backend/app/routers/scenarios.py backend/app/routers/system.py backend/tests/test_roles.py backend/tests/test_api.py
git commit -m "Roles: admin-only plan changes (audited), forced password change, reload by signed-in admin"
```

---

### Task 3: Change your own password — `POST /api/auth/password`

**Files:**
- Modify: `backend/app/schemas.py` (add `PasswordChangeIn`), `backend/app/routers/auth.py`, `backend/tests/test_roles.py`

**Interfaces:**
- Consumes: `auth.signed_in_user`, `auth.end_user_sessions`, `auth.verify_password`, `auth.hash_password`, `audit.audit`.
- Produces: `POST /api/auth/password {current_password, new_password}` → 204 / 400 / 422; audit action `user.password_change`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_roles.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py::test_change_own_password -q`
Expected: FAIL — 404 (no such route) / 405.

- [ ] **Step 3: Add the request model** — in `backend/app/schemas.py` after `LoginIn`:

```python
class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(max_length=1024, description="at least 8 characters (checked by the route)")
```

- [ ] **Step 4: Add the route** — in `backend/app/routers/auth.py`: import `HTTPException`, `PasswordChangeIn` and `from ..services.audit import audit`; add:

```python
@router.post("/password", status_code=204, summary="Change your own password (signs your other browsers out)")
def change_password(body: PasswordChangeIn, request: Request, session: Session = Depends(get_session),
                    user: M.User = Depends(auth.signed_in_user)) -> Response:
    if not auth.verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "The current password is wrong.")
    if body.new_password == body.current_password:
        raise HTTPException(400, "The new password must differ from the current one.")
    try:
        user.password_hash = auth.hash_password(body.new_password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    user.must_change_password = False
    auth.end_user_sessions(session, user.id, keep_token=request.cookies.get(auth.COOKIE))
    audit(session, user, "user.password_change", user.email)
    session.commit()
    return Response(status_code=204)
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py -q` → all pass. Then `.venv\Scripts\python -m pytest -q` → all pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/schemas.py backend/app/routers/auth.py backend/tests/test_roles.py
git commit -m "Roles: POST /api/auth/password (change your own password)"
```

---

### Task 4: Admin users API — list, create, edit, disable / enable, reset password

**Files:**
- Create: `backend/app/services/accounts.py`, `backend/app/routers/admin.py`
- Modify: `backend/app/schemas.py`, `backend/app/main.py:17,47`, `backend/tests/test_roles.py`

**Interfaces:**
- Consumes: `require_admin`, `end_user_sessions`, `hash_password`, `normalize_email`, `audit`.
- Produces: `accounts.check_admin_removal(session, actor_id: int, target: M.User) -> None` (raises 409); `accounts.hash_or_422(password: str) -> str`; `accounts.valid_email(email: str) -> str` (normalised, or 422). Routes `GET/POST /api/admin/users`, `PATCH /api/admin/users/{id}`, `POST /api/admin/users/{id}/password`. Schemas `AdminUserOut`, `UserCreateIn`, `UserPatchIn`, `PasswordSetIn`, `Role = Literal["admin", "viewer"]`. Audit actions `user.create` (detail `{"role"}`), `user.update` (detail `{"full_name"}`), `user.role` (detail `{"from","to"}`), `user.disable`, `user.enable`, `user.password_reset`.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_roles.py`:

```python
# ---------------------------------------------------------------- Task 4: admin users API
from app.services.accounts import check_admin_removal  # noqa: E402


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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'app.services.accounts'`.

- [ ] **Step 3: Create `backend/app/services/accounts.py`:**

```python
"""Rules for managing accounts from the admin portal."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from .auth import hash_password, normalize_email


def valid_email(email: str) -> str:
    """Trimmed, lower-case email; 422 when it is not one."""
    email = normalize_email(email)
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email:
        raise HTTPException(422, "That is not an email address.")
    return email


def hash_or_422(password: str) -> str:
    try:
        return hash_password(password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


def check_admin_removal(session: Session, actor_id: int, target: M.User) -> None:
    """Before `target` stops being an active admin: never yourself, never the last one.

    The active admins are locked (SELECT ... FOR UPDATE) so two admins demoting each other at the same moment are
    counted one after the other."""
    if target.id == actor_id:
        raise HTTPException(409, "You cannot remove your own admin access.")
    admins = session.scalars(
        select(M.User.id).where(M.User.role == "admin", M.User.is_active).with_for_update()
    ).all()
    if not set(admins) - {target.id}:
        raise HTTPException(409, "At least one active administrator is needed.")
```

- [ ] **Step 4: Add the schemas** — in `backend/app/schemas.py` change the pydantic import to `from typing import Literal` + existing, and add:

```python
Role = Literal["admin", "viewer"]


class AdminUserOut(UserOut):
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    full_name: str | None = Field(None, max_length=100)
    role: Role = "viewer"
    password: str = Field(max_length=1024, description="temporary: the person chooses their own at first sign-in")


class UserPatchIn(BaseModel):
    full_name: str | None = Field(None, max_length=100)
    role: Role | None = None
    is_active: bool | None = None


class PasswordSetIn(BaseModel):
    password: str = Field(max_length=1024)
```

(`from typing import Literal` goes at the top with the other imports.)

- [ ] **Step 5: Create `backend/app/routers/admin.py`:**

```python
"""The admin portal's API: user accounts (and the audit log, see below). Administrators only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..schemas import AdminUserOut, PasswordSetIn, UserCreateIn, UserPatchIn
from ..services.accounts import check_admin_removal, hash_or_422, valid_email
from ..services.audit import audit
from ..services.auth import end_user_sessions, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


def _user(session: Session, user_id: int) -> M.User:
    user = session.get(M.User, user_id)
    if user is None:
        raise HTTPException(404, f"No user {user_id}.")
    return user


def _name(value: str | None) -> str | None:
    return (value or "").strip() or None


@router.get("/users", response_model=list[AdminUserOut], summary="Every account")
def list_users(session: Session = Depends(get_session), _: M.User = Depends(require_admin)):
    return session.scalars(select(M.User).order_by(M.User.email)).all()


@router.post("/users", response_model=AdminUserOut, status_code=201,
             summary="Add an account with a temporary password (changed at first sign-in)")
def create_user(body: UserCreateIn, session: Session = Depends(get_session), admin: M.User = Depends(require_admin)):
    email = valid_email(body.email)
    if session.scalar(select(M.User.id).where(M.User.email == email)):
        raise HTTPException(409, f"{email} already has an account.")
    user = M.User(email=email, full_name=_name(body.full_name), role=body.role, password_hash=hash_or_422(body.password),
                  is_active=True, must_change_password=True, created_by_id=admin.id)
    session.add(user)
    audit(session, admin, "user.create", email, {"role": body.role})
    session.commit()
    session.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=AdminUserOut, summary="Change name, role, or disable / enable")
def update_user(user_id: int, body: UserPatchIn, session: Session = Depends(get_session),
                admin: M.User = Depends(require_admin)):
    user = _user(session, user_id)
    fields = body.model_fields_set
    loses_admin = user.role == "admin" and user.is_active and (
        ("role" in fields and body.role != "admin") or ("is_active" in fields and body.is_active is False))
    if loses_admin:
        check_admin_removal(session, admin.id, user)
    if "full_name" in fields and _name(body.full_name) != user.full_name:
        user.full_name = _name(body.full_name)
        audit(session, admin, "user.update", user.email, {"full_name": user.full_name})
    if body.role is not None and body.role != user.role:
        audit(session, admin, "user.role", user.email, {"from": user.role, "to": body.role})
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        audit(session, admin, "user.enable" if body.is_active else "user.disable", user.email)
        if not body.is_active:
            end_user_sessions(session, user.id)
    session.commit()
    session.refresh(user)
    return user


@router.post("/users/{user_id}/password", status_code=204,
             summary="Set a temporary password (signs the user out; they choose their own at next sign-in)")
def reset_password(user_id: int, body: PasswordSetIn, session: Session = Depends(get_session),
                   admin: M.User = Depends(require_admin)) -> Response:
    user = _user(session, user_id)
    user.password_hash = hash_or_422(body.password)
    user.must_change_password = True
    end_user_sessions(session, user.id)
    audit(session, admin, "user.password_reset", user.email)
    session.commit()
    return Response(status_code=204)
```

- [ ] **Step 6: Register the router** — in `backend/app/main.py`: `from .routers import admin, auth, data, projection, scenarios, system` and add `admin.router` to the `for router in (...)` tuple; update the comment above it to "Everything except health, reload (admin token) and sign-in needs a signed-in user; /admin/* an administrator (services/auth.py)".

- [ ] **Step 7: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py -q` → all pass. Then `.venv\Scripts\python -m pytest -q` → all pass.

- [ ] **Step 8: Commit**

```powershell
git add backend/app/services/accounts.py backend/app/routers/admin.py backend/app/schemas.py backend/app/main.py backend/tests/test_roles.py
git commit -m "Admin API: list, create, edit, disable / enable users, reset passwords (audited, last admin kept)"
```

---

### Task 5: Audit log API and backend documentation

**Files:**
- Modify: `backend/app/routers/admin.py`, `backend/app/schemas.py`, `backend/tests/test_roles.py`, `backend/README.md` (Users and sign-in, API table), `database/schema.dbml` (users, audit_log)

**Interfaces:**
- Consumes: `M.AuditLog`, `require_admin`.
- Produces: `GET /api/admin/audit?limit=50&before=<id>&user_id=<id>&action=<prefix>` → `list[AuditOut]` newest first; `AuditOut {id, at, user_id, user_email, user_name, action, target, detail}`. `action` matches as a prefix (`user.` = every user action).

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_roles.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py -k audit_log -q` → FAIL (404).

- [ ] **Step 3: Add `AuditOut`** to `backend/app/schemas.py`:

```python
class AuditOut(BaseModel):
    id: int
    at: datetime
    user_id: int | None
    user_email: str | None
    user_name: str | None
    action: str
    target: str
    detail: dict | None
```

- [ ] **Step 4: Add the route** to `backend/app/routers/admin.py` (imports: `from fastapi import Query`, `AuditOut`):

```python
@router.get("/audit", response_model=list[AuditOut], summary="Who changed what, newest first")
def audit_log(limit: int = Query(50, ge=1, le=200), before: int | None = None, user_id: int | None = None,
              action: str | None = Query(None, max_length=40, description="prefix, e.g. user. or scenario.delete"),
              session: Session = Depends(get_session), _: M.User = Depends(require_admin)):
    q = (select(M.AuditLog, M.User.email, M.User.full_name)
         .outerjoin(M.User, M.User.id == M.AuditLog.user_id)
         .order_by(M.AuditLog.id.desc()).limit(limit))
    if before is not None:
        q = q.where(M.AuditLog.id < before)
    if user_id is not None:
        q = q.where(M.AuditLog.user_id == user_id)
    if action:
        q = q.where(M.AuditLog.action.startswith(action, autoescape=True))
    return [AuditOut(id=a.id, at=a.at, user_id=a.user_id, user_email=email, user_name=name, action=a.action,
                     target=a.target, detail=a.detail) for a, email, name in session.execute(q).all()]
```

Update the module docstring: "The admin portal's API: user accounts and the audit log. Administrators only."

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_roles.py -q` → all pass. Then `.venv\Scripts\python -m pytest -q` → all pass.

- [ ] **Step 6: Document** —
  - `backend/README.md`, section "Users and sign-in": replace the first paragraph and command block with:

    ```markdown
    Everyone signs in with email and password; there is no sign-up page. There are two roles: **admins** manage
    accounts (admin portal, `/admin`) and saved plans; **viewers** see all the data and can try plans but not save
    them. An admin adds people in the portal with a temporary password, which the person must change at first
    sign-in. The first admin is created on the command line:

    ```powershell
    .venv\Scripts\python -m app.users create jane@mineduc.gov.rw --name "Jane Doe" --admin   # asks for the password
    .venv\Scripts\python -m app.users role jane@mineduc.gov.rw admin                        # or viewer
    .venv\Scripts\python -m app.users password jane@mineduc.gov.rw                          # new password, signs out everywhere
    .venv\Scripts\python -m app.users disable jane@mineduc.gov.rw                           # blocks sign-in (enable to undo)
    .venv\Scripts\python -m app.users list
    ```
    ```

    and in the paragraph after it replace "Every route except `/api/health`, `/api/auth/login` and `/api/admin/reload` (admin token) answers 401 without a session." with "Every route except `/api/health` and `/api/auth/login` answers 401 without a session; changing saved plans and `/api/admin/*` answer 403 for viewers; until a temporary password is changed every route except `/api/auth/me`, `/api/auth/password` and `/api/auth/logout` answers 403 `password_change_required`. Admin actions are recorded in `audit_log`."
  - `backend/README.md`, API table: change the scenarios rows' last column to "saved intake plans (any user reads; admins create / change / delete)", change the reload row to "re-read the database after an import (signed-in admin, or header `X-Admin-Token`)", and add rows:

    ```markdown
    | POST | `/api/auth/password` | change your own password `{"current_password", "new_password"}` |
    | GET / POST | `/api/admin/users` | admin: list accounts / add one `{"email", "full_name", "role", "password"}` (temporary password) |
    | PATCH | `/api/admin/users/{id}` | admin: `{"full_name", "role", "is_active"}` |
    | POST | `/api/admin/users/{id}/password` | admin: set a temporary password (signs the user out) |
    | GET | `/api/admin/audit` | admin: who changed what, newest first (`limit`, `before`, `user_id`, `action`) |
    ```
    and change the test count line `# 30 tests` to `# the whole suite`.
  - `database/schema.dbml`: add to the file (after `import_runs` / before the projections section):

    ```dbml
    // =====================================================================
    // Users and sign-in (built: backend/app/models.py)
    // =====================================================================
    Table users {
      id int [pk, increment]
      email varchar(254) [unique, not null, note: 'lower case']
      full_name varchar(100)
      password_hash varchar(255) [not null, note: 'argon2id']
      is_active boolean [not null, default: true]
      role varchar(10) [not null, default: 'viewer', note: 'admin or viewer']
      must_change_password boolean [not null, default: false, note: 'temporary password set by an admin']
      created_by_id int [ref: > users.id]
      created_at timestamptz [not null, default: `now()`]
      last_login_at timestamptz
    }

    Table user_sessions {
      id bigint [pk, increment]
      user_id int [not null, ref: > users.id]
      token_hash varchar(64) [unique, not null, note: 'SHA-256 of the cookie token']
      created_at timestamptz [not null, default: `now()`]
      expires_at timestamptz [not null]
    }

    Table audit_log {
      id bigint [pk, increment]
      at timestamptz [not null, default: `now()`]
      user_id int [ref: > users.id, note: 'who did it']
      action varchar(40) [not null, note: 'user.create, user.role, scenario.delete ...']
      target varchar(200) [not null]
      detail jsonb
    }
    ```

    and a `TableGroup access { users  user_sessions  audit_log }` at the end.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/routers/admin.py backend/app/schemas.py backend/tests/test_roles.py backend/README.md database/schema.dbml
git commit -m "Admin API: audit log (paged, filters); docs for roles and the admin routes"
```

---

### Task 6: Frontend — role in the session, change-password page, user menu

**Files:**
- Create: `dashboard/src/site/ChangePasswordPage.tsx`, `dashboard/src/UserMenu.tsx`
- Modify: `dashboard/src/api.ts`, `dashboard/src/auth.tsx`, `dashboard/src/App.tsx:1-8,120-160`, `dashboard/src/main.tsx`

**Interfaces:**
- Consumes: `/api/auth/me` (now with `role`, `must_change_password`), `POST /api/auth/password`.
- Produces: `api.ts`: `sendJson(method: 'POST'|'PUT'|'PATCH'|'DELETE', …)`, `PASSWORD_REQUIRED = 'auth:password-required'`. `auth.tsx`: `User.role: 'admin'|'viewer'`, `User.must_change_password: boolean`, `AuthState.refresh(): Promise<void>`, `isAdmin(u: User|null): boolean`, `RequireAdmin` component. Route `/account/password`.

- [ ] **Step 1: `api.ts`** — change the `sendJson` method type to `'POST' | 'PUT' | 'PATCH' | 'DELETE'`, add under `AUTH_EXPIRED`:

```ts
/** A temporary password must be changed first (403 password_change_required): auth.tsx sends the user to the form. */
export const PASSWORD_REQUIRED = 'auth:password-required';
```

and in `request`, replace the line `if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event(AUTH_EXPIRED));` with:

```ts
    if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event(AUTH_EXPIRED));
    if (res.status === 403 && detail === 'password_change_required') {
      window.dispatchEvent(new Event(PASSWORD_REQUIRED));
      detail = 'Please choose a new password first.';
    }
```

- [ ] **Step 2: `auth.tsx`** — apply these changes:
  - import: `import { AUTH_EXPIRED, ApiError, PASSWORD_REQUIRED, getJson, sendJson } from './api';`
  - `User`:
    ```ts
    export interface User {
      id: number;
      email: string;
      full_name: string | null;
      role: 'admin' | 'viewer';
      must_change_password: boolean; // a temporary password set by an admin: the user must choose their own first
    }
    ```
  - `AuthState` gets `refresh: () => Promise<void>; // re-read /auth/me (after a password change)`
  - in `AuthProvider`'s effect, next to the `expired` listener:
    ```ts
        const mustChange = () => setUser((u) => (u ? { ...u, must_change_password: true } : u));
        window.addEventListener(PASSWORD_REQUIRED, mustChange);
    ```
    and remove it in the cleanup (`window.removeEventListener(PASSWORD_REQUIRED, mustChange);`).
  - add before `signOut`:
    ```ts
      const refresh = useCallback(async () => {
        setUser(await getJson<User>('/auth/me'));
      }, []);
    ```
    and include `refresh` in the `useMemo` value and its dependency list.
  - add after `displayName`:
    ```ts
    /** Admins manage accounts and saved plans; viewers read and try plans. */
    export const isAdmin = (u: User | null) => u?.role === 'admin';

    export const PASSWORD_PAGE = '/account/password';
    ```
  - in `RequireAuth`, after the `if (!user) {…}` block:
    ```ts
      if (user.must_change_password && location.pathname !== PASSWORD_PAGE) return <Navigate to={PASSWORD_PAGE} replace />;
    ```
  - add:
    ```tsx
    /** Only for administrators (inside RequireAuth); viewers go to the dashboard. */
    export function RequireAdmin({ children }: { children: ReactNode }) {
      const { user } = useAuth();
      if (!isAdmin(user)) return <Navigate to="/dashboard" replace />;
      return <>{children}</>;
    }
    ```
  - `safeNext` stays as it is: after sign-in the user goes to `next`, and `RequireAuth` sends them on to the password page when they must change it.

- [ ] **Step 3: Create `dashboard/src/site/ChangePasswordPage.tsx`:**

```tsx
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { sendJson } from '../api';
import { useAuth } from '../auth';
import { ThemeToggle } from '../theme';
import { LogoMark } from './SiteChrome';

const MIN_PASSWORD = 8; // backend/app/services/auth.py

/** Change your own password. Forced after an administrator created the account or reset its password. */
export default function ChangePasswordPage() {
  const { user, refresh, signOut } = useAuth();
  const navigate = useNavigate();
  const forced = !!user?.must_change_password;
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (next.length < MIN_PASSWORD) return setError(`The new password must have at least ${MIN_PASSWORD} characters.`);
    if (next !== repeat) return setError('The two new passwords differ.');
    setLoading(true);
    try {
      await sendJson<void>('POST', '/auth/password', { current_password: current, new_password: next });
      await refresh();
      navigate('/dashboard', { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
    }
  }

  const onSignOut = () => {
    navigate('/', { replace: true });
    void signOut();
  };

  return (
    <div className="auth-page">
      <ThemeToggle className="lp-theme-btn auth-theme-btn" />
      <form className="login-card" onSubmit={onSubmit} noValidate>
        <LogoMark size={56} />
        <h2>{forced ? 'Choose your password' : 'Change password'}</h2>
        <p className="auth-subtitle">
          {forced
            ? 'You signed in with a temporary password from your administrator. Choose your own to continue.'
            : `Signed in as ${user?.email ?? ''}.`}
        </p>
        <label>
          {forced ? 'Temporary password' : 'Current password'}
          <input type="password" autoComplete="current-password" value={current} autoFocus disabled={loading}
            onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label>
          New password (at least {MIN_PASSWORD} characters)
          <input type="password" autoComplete="new-password" value={next} disabled={loading}
            onChange={(e) => setNext(e.target.value)} />
        </label>
        <label>
          Repeat the new password
          <input type="password" autoComplete="new-password" value={repeat} disabled={loading}
            onChange={(e) => setRepeat(e.target.value)} />
        </label>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-cosmic login-btn" disabled={loading}>
          {loading ? 'Saving...' : 'Save password'}
        </button>
        <p className="auth-back">
          {forced
            ? <button type="button" className="auth-link-btn" onClick={onSignOut}>Sign out</button>
            : <Link to="/dashboard">Back to the dashboard</Link>}
        </p>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Create `dashboard/src/UserMenu.tsx`:**

```tsx
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { PASSWORD_PAGE, displayName, isAdmin, useAuth } from './auth';

/** The signed-in user's menu in the dashboard header: change password, admin portal (admins), sign out. */
export default function UserMenu({ onSignOut }: { onSignOut: () => void }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const click = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', click);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('mousedown', click);
      document.removeEventListener('keydown', key);
    };
  }, [open]);

  if (!user) return null;
  const item = 'block w-full px-3 py-2 text-left text-sm text-ink2 hover:bg-[var(--line)] hover:text-ink';
  return (
    <div ref={ref} className="relative print:hidden">
      <button type="button" aria-haspopup="menu" aria-expanded={open} title={user.email} onClick={() => setOpen((o) => !o)}
        className="flex h-8 max-w-[260px] items-center gap-1.5 rounded-md border border-line px-2.5 text-xs text-ink2 hover:text-ink">
        <span className="truncate">{displayName(user)}</span>
        {isAdmin(user) && (
          <span className="rounded bg-[var(--accent-soft)] px-1 text-[10px] font-semibold uppercase text-accent">Admin</span>
        )}
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-50 mt-1 w-48 overflow-hidden rounded-md border border-line bg-surface py-1 shadow-lg">
          <Link role="menuitem" to={PASSWORD_PAGE} className={item} onClick={() => setOpen(false)}>Change password</Link>
          {isAdmin(user) && (
            <Link role="menuitem" to="/admin" className={item} onClick={() => setOpen(false)}>Admin portal</Link>
          )}
          <button role="menuitem" type="button" className={item}
            onClick={() => {
              setOpen(false);
              onSignOut();
            }}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Use it in `App.tsx`** — import `UserMenu from './UserMenu'`, change the auth import to `import { useAuth } from './auth';` (drop `displayName`), and replace the whole `{user && ( <div className="flex items-center gap-3 print:hidden"> … </div> )}` block with `<UserMenu onSignOut={onSignOut} />`. `user` is then unused in `App` — change `const { user, signOut } = useAuth();` to `const { signOut } = useAuth();`.

- [ ] **Step 6: Route** — in `main.tsx`: `import ChangePasswordPage from './site/ChangePasswordPage';` and inside the `<Route element={<SitePages />}>` group add:

```tsx
              <Route path="/account/password" element={<RequireAuth><ChangePasswordPage /></RequireAuth>} />
```

- [ ] **Step 7: Type-check**

Run (from `dashboard/`): `npx tsc -b --noEmit` → exit 0.

- [ ] **Step 8: Check in the browser** — API (`uvicorn app.main:app --reload`) and `npm run dev` running. Create a forced user: `python -m app.users create pytest-ui@example.test --name "UI Test"` then in pgAdmin / psql `UPDATE users SET must_change_password = true WHERE email = 'pytest-ui@example.test';`. Sign in at http://localhost:5173/login as that user → lands on "Choose your password"; `/dashboard` redirects back there; wrong temporary password shows "The current password is wrong."; a valid change opens the dashboard. The header shows the name with a menu: Change password, Sign out (no "Admin portal" for this viewer). Remove the account afterwards (`DELETE FROM users WHERE email = 'pytest-ui@example.test';`).

- [ ] **Step 9: Commit**

```powershell
git add dashboard/src/api.ts dashboard/src/auth.tsx dashboard/src/site/ChangePasswordPage.tsx dashboard/src/UserMenu.tsx dashboard/src/App.tsx dashboard/src/main.tsx
git commit -m "Dashboard: roles in the session, change-password page (forced after a temporary password), user menu"
```

---

### Task 7: Frontend — viewers try plans but cannot save them

**Files:**
- Modify: `dashboard/src/components/IntakePlanner.tsx:40-107,188`, `dashboard/src/components/ProjectionPage.tsx:1-10,229-235`

**Interfaces:**
- Consumes: `isAdmin`, `useAuth` (Task 6).
- Produces: `ScenarioControls.canEdit: boolean`.

- [ ] **Step 1: Controls know who may save** — in `IntakePlanner.tsx` add to `ScenarioControls` (after `defaultLabel`):

```ts
  /** Admins save, rename and delete shared plans; viewers only open them and try their own numbers. */
  canEdit: boolean;
```

- [ ] **Step 2: Read-only bar** — in `ScenarioBar`, keep the `<label>` with the plan `<select>` and the `unsaved changes` badge for everyone; wrap the Save button, the naming / "Save as new plan…" block and the Delete button in `{s.canEdit && (<> … </>)}`; and replace the right-hand note with:

```tsx
        <span className="ml-auto text-xs text-muted">
          {s.canEdit
            ? 'Saved plans are shared with everyone who uses the dashboard.'
            : 'You can try plans; only an administrator can save them.'}
        </span>
```

For viewers the badge reads better as "changed (not saved)": replace `{s.dirty && <span …>unsaved changes</span>}` with

```tsx
        {s.dirty && <span className="text-xs font-medium text-accent">{s.canEdit ? 'unsaved changes' : 'changed (not saved)'}</span>}
```

- [ ] **Step 3: The hint under the planner** — at the line `<span className="ml-auto text-xs text-muted">Press Enter or leave a cell to recalculate. Save the plan to share it.</span>` use:

```tsx
        <span className="ml-auto text-xs text-muted">
          Press Enter or leave a cell to recalculate.{scenarios?.canEdit ? ' Save the plan to share it.' : ''}
        </span>
```

- [ ] **Step 4: Pass `canEdit`** — in `ProjectionPage.tsx` add `import { isAdmin, useAuth } from '../auth';`, in `ProjectionPage` add `const { user } = useAuth();` at the top, and in `scenarioControls` add `canEdit: isAdmin(user),` after `defaultLabel`.

- [ ] **Step 5: Type-check** — `npx tsc -b --noEmit` → exit 0.

- [ ] **Step 6: Check in the browser** — as a viewer (make one with `python -m app.users create … ` without `--admin`): the plan bar shows the plan list and the note "You can try plans; only an administrator can save them."; editing a number recalculates the projection and shows "changed (not saved)"; no Save / Save as / Delete. As the admin (`python -m app.users role <you> admin`, sign out and in): the buttons are back.

- [ ] **Step 7: Commit**

```powershell
git add dashboard/src/components/IntakePlanner.tsx dashboard/src/components/ProjectionPage.tsx
git commit -m "Dashboard: viewers try intake plans without saving; saving stays with admins"
```

---

### Task 8: Admin portal shell and Activity page

**Files:**
- Create: `dashboard/src/admin/api.ts`, `dashboard/src/admin/AdminApp.tsx`, `dashboard/src/admin/AdminLayout.tsx`, `dashboard/src/admin/ActivityPage.tsx`, `dashboard/src/admin/UsersPage.tsx` (temporary one-line page, replaced in Task 9)
- Modify: `dashboard/src/main.tsx`

**Interfaces:**
- Consumes: `/api/admin/users`, `/api/admin/audit`, `RequireAdmin`, `LogoMark`, `ThemeToggle`, `displayName`.
- Produces: `admin/api.ts` exports `Role`, `AdminUser`, `AuditEntry`, `listUsers()`, `createUser(body)`, `updateUser(id, body)`, `resetPassword(id, password)`, `listAudit(params)`; route `/admin/*` (index → `users`, `users`, `activity`); `AdminLayout({ children })`.

- [ ] **Step 1: Create `dashboard/src/admin/api.ts`:**

```ts
/** The admin portal's API calls (backend/app/routers/admin.py). */
import { getJson, sendJson } from '../api';

export type Role = 'admin' | 'viewer';

export interface AdminUser {
  id: number;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuditEntry {
  id: number;
  at: string;
  user_id: number | null;
  user_email: string | null;
  user_name: string | null;
  action: string;
  target: string;
  detail: Record<string, unknown> | null;
}

export const listUsers = () => getJson<AdminUser[]>('/admin/users');

export const createUser = (body: { email: string; full_name: string | null; role: Role; password: string }) =>
  sendJson<AdminUser>('POST', '/admin/users', body);

export const updateUser = (id: number, body: { full_name?: string | null; role?: Role; is_active?: boolean }) =>
  sendJson<AdminUser>('PATCH', `/admin/users/${id}`, body);

export const resetPassword = (id: number, password: string) =>
  sendJson<void>('POST', `/admin/users/${id}/password`, { password });

export function listAudit(p: { before?: number; userId?: number; action?: string; limit?: number } = {}) {
  const q = new URLSearchParams({ limit: String(p.limit ?? 50) });
  if (p.before !== undefined) q.set('before', String(p.before));
  if (p.userId !== undefined) q.set('user_id', String(p.userId));
  if (p.action) q.set('action', p.action);
  return getJson<AuditEntry[]>(`/admin/audit?${q}`);
}
```

- [ ] **Step 2: Create `dashboard/src/admin/AdminLayout.tsx`:**

```tsx
import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Activity, ArrowLeft, Database, LogOut, Menu, Users, X } from 'lucide-react';
import { displayName, useAuth } from '../auth';
import { ThemeToggle } from '../theme';
import { LogoMark } from '../site/SiteChrome';

const NAV = [
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/activity', label: 'Activity', icon: Activity },
];
const iconBtn = 'grid h-8 w-8 place-items-center rounded-md border border-line text-ink2 hover:text-ink';

/** The admin portal's frame: a sidebar on wide screens, a top bar with a menu on phones. */
export default function AdminLayout({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);

  const onSignOut = () => {
    navigate('/', { replace: true });
    void signOut();
  };
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
      isActive ? 'bg-[var(--accent-soft)] font-medium text-accent' : 'text-ink2 hover:bg-[var(--line)] hover:text-ink'}`;

  const nav = (
    <nav className="flex flex-1 flex-col gap-1" aria-label="Admin">
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} className={linkClass}>
          <Icon size={16} aria-hidden />
          {label}
        </NavLink>
      ))}
      <div className="my-2 border-t border-line" />
      <span className="flex cursor-not-allowed items-center gap-2 px-3 py-2 text-sm text-muted"
        title="Uploading and publishing data comes next">
        <Database size={16} aria-hidden />
        Data
        <span className="ml-auto text-[10px] uppercase tracking-wide">soon</span>
      </span>
    </nav>
  );
  const footer = (
    <div className="space-y-2 border-t border-line pt-3">
      <Link to="/dashboard" className="flex items-center gap-2 px-3 py-1 text-sm text-ink2 hover:text-ink">
        <ArrowLeft size={16} aria-hidden />
        Dashboard
      </Link>
      <div className="flex items-center gap-2 px-3">
        <span className="min-w-0 flex-1 truncate text-xs text-ink2" title={user?.email}>{user ? displayName(user) : ''}</span>
        <ThemeToggle className={iconBtn} />
        <button type="button" onClick={onSignOut} title="Sign out" aria-label="Sign out" className={iconBtn}>
          <LogOut size={16} aria-hidden />
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-page md:flex">
      <aside className="hidden w-60 shrink-0 flex-col gap-4 border-r border-line bg-surface p-4 md:sticky md:top-0 md:flex md:h-screen">
        <Link to="/admin" className="flex items-center gap-2">
          <LogoMark size={28} />
          <span className="text-sm font-semibold text-ink">Admin</span>
        </Link>
        {nav}
        {footer}
      </aside>
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-2 md:hidden">
        <LogoMark size={28} />
        <span className="flex-1 text-sm font-semibold text-ink">Admin</span>
        <button type="button" aria-expanded={menuOpen} aria-label="Menu" onClick={() => setMenuOpen((o) => !o)} className={iconBtn}>
          {menuOpen ? <X size={16} aria-hidden /> : <Menu size={16} aria-hidden />}
        </button>
      </header>
      {menuOpen && <div className="flex flex-col gap-3 border-b border-line bg-surface p-4 md:hidden">{nav}{footer}</div>}
      <main className="min-w-0 flex-1 p-4 sm:p-6">{children}</main>
    </div>
  );
}
```

- [ ] **Step 3: Create `dashboard/src/admin/ActivityPage.tsx`:**

```tsx
import { useCallback, useEffect, useState } from 'react';
import { listAudit, listUsers, type AdminUser, type AuditEntry } from './api';

const ACTIONS = [
  { value: '', label: 'All actions' },
  { value: 'user.', label: 'Accounts' },
  { value: 'scenario.', label: 'Saved plans' },
];
const PAGE = 50;
const when = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });

/** One audit entry as a sentence. */
export function sentence(e: AuditEntry): string {
  const who = e.user_name || e.user_email || 'A deleted account';
  const d = e.detail ?? {};
  switch (e.action) {
    case 'user.create': return `${who} added ${e.target} as ${String(d.role ?? 'viewer')}`;
    case 'user.update': return `${who} renamed ${e.target} to "${String(d.full_name ?? '')}"`;
    case 'user.role': return `${who} changed ${e.target} from ${String(d.from)} to ${String(d.to)}`;
    case 'user.disable': return `${who} disabled ${e.target}`;
    case 'user.enable': return `${who} enabled ${e.target}`;
    case 'user.password_reset': return `${who} reset the password of ${e.target}`;
    case 'user.password_change': return `${who} changed their password`;
    case 'scenario.create': return `${who} saved the plan "${e.target}"`;
    case 'scenario.update': return `${who} updated the plan "${e.target}"`;
    case 'scenario.delete': return `${who} deleted the plan "${e.target}"`;
    default: return `${who}: ${e.action} ${e.target}`;
  }
}

/** The audit log: who changed what, newest first. */
export default function ActivityPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userId, setUserId] = useState<number | undefined>(undefined);
  const [action, setAction] = useState('');
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listUsers().then(setUsers).catch(() => undefined); // the filter still works without names
  }, []);

  const load = useCallback(async (before?: number) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAudit({ before, userId, action, limit: PAGE });
      setEntries((prev) => (before === undefined ? page : [...prev, ...page]));
      setMore(page.length === PAGE);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [userId, action]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-lg font-semibold text-ink">Activity</h1>
      <p className="mb-4 text-sm text-muted">Changes to accounts and saved plans, newest first.</p>
      <div className="mb-3 flex flex-wrap gap-2 text-sm">
        <select aria-label="Who" className="h-8 px-2" value={userId ?? ''}
          onChange={(e) => setUserId(e.target.value === '' ? undefined : Number(e.target.value))}>
          <option value="">Everyone</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.email}</option>)}
        </select>
        <select aria-label="Action" className="h-8 px-2" value={action} onChange={(e) => setAction(e.target.value)}>
          {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
      </div>
      {error && <p className="mb-3 text-sm text-[var(--deficit)]" role="alert">{error}</p>}
      <ul className="divide-y divide-[var(--line)] rounded-lg border border-line bg-surface">
        {entries.map((e) => (
          <li key={e.id} className="flex flex-wrap items-baseline justify-between gap-x-4 px-4 py-2.5 text-sm">
            <span className="text-ink">{sentence(e)}</span>
            <time className="text-xs text-muted" dateTime={e.at}>{when.format(new Date(e.at))}</time>
          </li>
        ))}
        {!entries.length && !loading && <li className="px-4 py-6 text-center text-sm text-muted">Nothing recorded yet.</li>}
      </ul>
      {more && (
        <button type="button" disabled={loading} onClick={() => void load(entries[entries.length - 1]?.id)}
          className="mt-3 h-8 rounded-md border border-line px-3 text-sm text-ink2 hover:text-ink disabled:opacity-50">
          {loading ? 'Loading…' : 'Load more'}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Temporary users page** — create `dashboard/src/admin/UsersPage.tsx` (replaced in Task 9):

```tsx
export default function UsersPage() {
  return <h1 className="text-lg font-semibold text-ink">Users</h1>;
}
```

- [ ] **Step 5: Create `dashboard/src/admin/AdminApp.tsx`:**

```tsx
import { useEffect } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AdminLayout from './AdminLayout';
import ActivityPage from './ActivityPage';
import UsersPage from './UsersPage';

/** The admin portal (administrators only, see RequireAdmin in main.tsx). */
export default function AdminApp() {
  useEffect(() => {
    const previous = document.title;
    document.title = 'Admin — School Demand & Demographics';
    return () => {
      document.title = previous;
    };
  }, []);
  return (
    <AdminLayout>
      <Routes>
        <Route index element={<Navigate to="users" replace />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="*" element={<Navigate to="users" replace />} />
      </Routes>
    </AdminLayout>
  );
}
```

- [ ] **Step 6: Route** — in `main.tsx`: `import { AuthProvider, RequireAdmin, RequireAuth } from './auth';`, `const Admin = lazy(() => import('./admin/AdminApp'));` next to `Dashboard`, and after the `/dashboard` route:

```tsx
            <Route path="/admin/*" element={
              <RequireAuth>
                <RequireAdmin>
                  <DashboardBoundary>
                    <Suspense fallback={loading}>
                      <Admin />
                    </Suspense>
                  </DashboardBoundary>
                </RequireAdmin>
              </RequireAuth>
            } />
```

- [ ] **Step 7: Type-check** — `npx tsc -b --noEmit` → exit 0.

- [ ] **Step 8: Check in the browser** — as admin: header menu → Admin portal opens `/admin/users` with the sidebar (Users, Activity, Data "soon", ← Dashboard, name, theme, sign out); Activity lists the entries made by the backend tests / your changes as sentences, both filters work, "Load more" appears after 50. Narrow the window below 768 px: the top bar with the menu button replaces the sidebar. As a viewer, `/admin` sends you to `/dashboard`.

- [ ] **Step 9: Commit**

```powershell
git add dashboard/src/admin dashboard/src/main.tsx
git commit -m "Admin portal: layout (sidebar / mobile menu), routes for admins, Activity page"
```

---

### Task 9: Admin portal — Users page

**Files:**
- Create: `dashboard/src/admin/password.ts`, `dashboard/src/admin/UserPanel.tsx`
- Replace: `dashboard/src/admin/UsersPage.tsx`

**Interfaces:**
- Consumes: `listUsers`, `createUser`, `updateUser`, `resetPassword`, `AdminUser`, `Role` (Task 8); `useAuth`.
- Produces: `generatePassword(length = 12): string`; `UserPanel` props `{ mode: PanelMode; roleLock: string | null; onClose(): void; onDone(result: PanelResult): void }` with `PanelMode = { kind: 'add' } | { kind: 'edit'; user: AdminUser } | { kind: 'reset'; user: AdminUser }` and `PanelResult = { message: string; password?: { name: string; value: string } }`.

- [ ] **Step 1: Create `dashboard/src/admin/password.ts`:**

```ts
// No look-alike characters (0/O, 1/l/I), so a password read aloud or copied by hand works
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';

/** A random temporary password (crypto.getRandomValues, no modulo bias). */
export function generatePassword(length = 12): string {
  const limit = Math.floor(2 ** 32 / ALPHABET.length) * ALPHABET.length;
  const buf = new Uint32Array(1);
  let out = '';
  while (out.length < length) {
    crypto.getRandomValues(buf);
    if (buf[0] < limit) out += ALPHABET[buf[0] % ALPHABET.length];
  }
  return out;
}
```

- [ ] **Step 2: Create `dashboard/src/admin/UserPanel.tsx`:**

```tsx
import { useState, type FormEvent } from 'react';
import { X } from 'lucide-react';
import { createUser, resetPassword, updateUser, type AdminUser, type Role } from './api';
import { generatePassword } from './password';

export type PanelMode = { kind: 'add' } | { kind: 'edit'; user: AdminUser } | { kind: 'reset'; user: AdminUser };
export interface PanelResult {
  message: string;
  password?: { name: string; value: string }; // shown once on the page
}

const MIN_PASSWORD = 8;
const field = 'mt-1 h-9 w-full rounded-md border border-line bg-page px-2 text-sm text-ink';
const btn = 'h-9 rounded-md border border-line px-3 text-sm text-ink2 hover:text-ink disabled:opacity-50';

/** Side panel: add a user, edit name / role, or set a temporary password. */
export default function UserPanel({ mode, roleLock, onClose, onDone }: {
  mode: PanelMode;
  roleLock: string | null; // why the role cannot change (own account, last admin), or null
  onClose: () => void;
  onDone: (result: PanelResult) => void;
}) {
  const user = mode.kind === 'add' ? null : mode.user;
  const [email, setEmail] = useState('');
  const [name, setName] = useState(user?.full_name ?? '');
  const [role, setRole] = useState<Role>(user?.role ?? 'viewer');
  const [password, setPassword] = useState(mode.kind === 'edit' ? '' : generatePassword());
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const title = mode.kind === 'add' ? 'Add user' : mode.kind === 'edit' ? 'Edit user' : 'Reset password';
  const who = (u: { full_name: string | null; email: string }) => u.full_name || u.email;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (mode.kind !== 'edit' && password.length < MIN_PASSWORD) {
      setError(`The password must have at least ${MIN_PASSWORD} characters.`);
      return;
    }
    setBusy(true);
    try {
      if (mode.kind === 'add') {
        const u = await createUser({ email: email.trim(), full_name: name.trim() || null, role, password });
        onDone({ message: `Added ${u.email}.`, password: { name: who(u), value: password } });
      } else if (mode.kind === 'edit') {
        const body: { full_name?: string | null; role?: Role } = {};
        if ((name.trim() || null) !== mode.user.full_name) body.full_name = name.trim() || null;
        if (role !== mode.user.role) body.role = role;
        const u = Object.keys(body).length ? await updateUser(mode.user.id, body) : mode.user;
        onDone({ message: `Saved ${u.email}.` });
      } else {
        await resetPassword(mode.user.id, password);
        onDone({ message: `${mode.user.email} is signed out and must choose a new password.`,
          password: { name: who(mode.user), value: password } });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form onSubmit={submit} noValidate role="dialog" aria-label={title}
        className="flex h-full w-full max-w-md flex-col gap-4 overflow-y-auto border-l border-line bg-surface p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-md text-ink2 hover:text-ink">
            <X size={16} aria-hidden />
          </button>
        </div>
        {user && <p className="text-sm text-ink2">{user.email}</p>}

        {mode.kind === 'add' && (
          <label className="text-sm text-ink2">Email
            <input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className={field} />
          </label>
        )}
        {mode.kind !== 'reset' && (
          <>
            <label className="text-sm text-ink2">Name
              <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} className={field} />
            </label>
            <label className="text-sm text-ink2">Role
              <select value={role} disabled={!!roleLock} title={roleLock ?? undefined}
                onChange={(e) => setRole(e.target.value as Role)} className={field}>
                <option value="viewer">Viewer — sees everything, can try plans</option>
                <option value="admin">Admin — manages users and saved plans</option>
              </select>
              {roleLock && <span className="mt-1 block text-xs text-muted">{roleLock}</span>}
            </label>
          </>
        )}
        {mode.kind !== 'edit' && (
          <label className="text-sm text-ink2">Temporary password
            <span className="mt-1 flex gap-2">
              <input value={password} onChange={(e) => setPassword(e.target.value)} spellCheck={false} autoComplete="off"
                className={`${field} mt-0 font-mono`} />
              <button type="button" className={btn} onClick={() => setPassword(generatePassword())}>Generate</button>
            </span>
            <span className="mt-1 block text-xs text-muted">
              They will choose their own password the first time they sign in.
            </span>
          </label>
        )}

        {error && <p className="text-sm text-[var(--deficit)]" role="alert">{error}</p>}
        <div className="mt-auto flex justify-end gap-2">
          <button type="button" className={btn} onClick={onClose}>Cancel</button>
          <button type="submit" disabled={busy}
            className="h-9 rounded-md bg-accent px-4 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
            {busy ? 'Saving…' : mode.kind === 'add' ? 'Add user' : mode.kind === 'edit' ? 'Save' : 'Set password'}
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Replace `dashboard/src/admin/UsersPage.tsx`:**

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Copy, MoreHorizontal, Plus } from 'lucide-react';
import { useAuth } from '../auth';
import { listUsers, updateUser, type AdminUser } from './api';
import UserPanel, { type PanelMode, type PanelResult } from './UserPanel';

type Status = 'Active' | 'Disabled' | 'Must change password';
const statusOf = (u: AdminUser): Status => (!u.is_active ? 'Disabled' : u.must_change_password ? 'Must change password' : 'Active');
const STATUS_CLASS: Record<Status, string> = {
  Active: 'text-ink2',
  Disabled: 'text-muted line-through',
  'Must change password': 'text-accent',
};
const lastIn = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
const OWN = 'You cannot remove your own admin access.';
const LAST = 'At least one active administrator is needed.';

/** Row menu: edit, reset password, disable / enable. */
function RowMenu({ user, lock, onPick }: {
  user: AdminUser;
  lock: string | null;
  onPick: (action: 'edit' | 'reset' | 'toggle') => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);
  const item = 'block w-full px-3 py-2 text-left text-sm text-ink2 hover:bg-[var(--line)] hover:text-ink disabled:cursor-not-allowed disabled:opacity-50';
  const pick = (a: 'edit' | 'reset' | 'toggle') => {
    setOpen(false);
    onPick(a);
  };
  const toggleLocked = user.is_active && !!lock;
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-label={`Actions for ${user.email}`} aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen((o) => !o)} className="grid h-8 w-8 place-items-center rounded-md text-ink2 hover:bg-[var(--line)] hover:text-ink">
        <MoreHorizontal size={16} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-1 w-44 overflow-hidden rounded-md border border-line bg-surface py-1 shadow-lg">
          <button role="menuitem" type="button" className={item} onClick={() => pick('edit')}>Edit</button>
          <button role="menuitem" type="button" className={item} onClick={() => pick('reset')}>Reset password</button>
          <button role="menuitem" type="button" className={item} disabled={toggleLocked} title={toggleLocked ? lock! : undefined}
            onClick={() => pick('toggle')}>
            {user.is_active ? 'Disable' : 'Enable'}
          </button>
        </div>
      )}
    </div>
  );
}

/** Accounts: add, edit, reset passwords, disable / enable. */
export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [shown, setShown] = useState<{ name: string; value: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const [panel, setPanel] = useState<PanelMode | null>(null);

  const refresh = useCallback(() => {
    listUsers().then(setUsers).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  useEffect(refresh, [refresh]);

  const activeAdmins = users.filter((u) => u.role === 'admin' && u.is_active).length;
  /** Why this user cannot lose admin access right now, or null. */
  const lockOf = (u: AdminUser): string | null => {
    if (u.role !== 'admin' || !u.is_active) return null;
    if (u.id === me?.id) return OWN;
    return activeAdmins <= 1 ? LAST : null;
  };

  const shownUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return users.filter((u) =>
      (!q || u.email.includes(q) || (u.full_name ?? '').toLowerCase().includes(q)) &&
      (!role || u.role === role) && (!status || statusOf(u) === status));
  }, [users, search, role, status]);

  const done = (r: PanelResult) => {
    setPanel(null);
    setNotice(r.message);
    setShown(r.password ?? null);
    setCopied(false);
    refresh();
  };

  const toggle = async (u: AdminUser) => {
    if (u.is_active && !window.confirm(`Disable ${u.email}? They are signed out at once and can no longer sign in.`)) return;
    setError(null);
    try {
      await updateUser(u.id, { is_active: !u.is_active });
      setNotice(`${u.email} ${u.is_active ? 'disabled' : 'enabled'}.`);
      setShown(null);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const copy = async () => {
    if (!shown) return;
    try {
      await navigator.clipboard.writeText(shown.value);
      setCopied(true);
    } catch {
      setCopied(false); // no clipboard (plain http): the password stays visible to copy by hand
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-ink">Users</h1>
          <p className="text-sm text-muted">Admins manage users and saved plans; viewers see everything and can try plans.</p>
        </div>
        <button type="button" onClick={() => setPanel({ kind: 'add' })}
          className="flex h-9 items-center gap-1.5 rounded-md bg-accent px-3 text-sm font-medium text-white hover:opacity-90">
          <Plus size={16} aria-hidden /> Add user
        </button>
      </div>

      {shown && (
        <div className="mb-3 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] p-3 text-sm text-ink" role="status">
          <p>Give this password to {shown.name}; they will choose their own at first sign-in.</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className="rounded bg-surface px-2 py-1 font-mono text-base">{shown.value}</code>
            <button type="button" onClick={() => void copy()}
              className="flex h-8 items-center gap-1 rounded-md border border-line px-2 text-xs text-ink2 hover:text-ink">
              <Copy size={14} aria-hidden /> {copied ? 'Copied' : 'Copy'}
            </button>
            <button type="button" onClick={() => setShown(null)} className="ml-auto text-xs text-muted hover:text-ink">
              Done — hide it
            </button>
          </div>
        </div>
      )}
      {notice && !shown && <p className="mb-3 text-sm text-ink2" role="status">{notice}</p>}
      {error && <p className="mb-3 text-sm text-[var(--deficit)]" role="alert">{error}</p>}

      <div className="rounded-lg border border-line bg-surface">
        <div className="flex flex-wrap gap-2 border-b border-line p-3 text-sm">
          <input type="search" placeholder="Search name or email" aria-label="Search users" value={search}
            onChange={(e) => setSearch(e.target.value)} className="h-8 min-w-[200px] flex-1 px-2" />
          <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)} className="h-8 px-2">
            <option value="">All roles</option>
            <option value="admin">Admins</option>
            <option value="viewer">Viewers</option>
          </select>
          <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 px-2">
            <option value="">All statuses</option>
            <option>Active</option>
            <option>Must change password</option>
            <option>Disabled</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Name / email</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Last sign-in</th>
                <th className="w-12 px-2 py-2"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--line)]">
              {shownUsers.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-ink">{u.full_name || '—'}{u.id === me?.id && <span className="ml-1 text-xs text-muted">(you)</span>}</div>
                    <div className="text-xs text-muted">{u.email}</div>
                  </td>
                  <td className="px-4 py-2.5 text-ink2">{u.role === 'admin' ? 'Admin' : 'Viewer'}</td>
                  <td className={`px-4 py-2.5 ${STATUS_CLASS[statusOf(u)]}`}>{statusOf(u)}</td>
                  <td className="px-4 py-2.5 text-ink2">{u.last_login_at ? lastIn.format(new Date(u.last_login_at)) : 'never'}</td>
                  <td className="px-2 py-2.5">
                    <RowMenu user={u} lock={lockOf(u)}
                      onPick={(a) => (a === 'toggle' ? void toggle(u) : setPanel({ kind: a, user: u }))} />
                  </td>
                </tr>
              ))}
              {!shownUsers.length && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-muted">No user matches.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {panel && (
        <UserPanel mode={panel} roleLock={panel.kind === 'edit' ? lockOf(panel.user) : null}
          onClose={() => setPanel(null)} onDone={done} />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Type-check** — `npx tsc -b --noEmit` → exit 0.

- [ ] **Step 5: Check in the browser** (as admin, `/admin/users`):
  - Add user `pytest-ui@example.test`, name "UI Test", Viewer, generated password → the show-once box with "Give this password to UI Test; …", Copy works; the row shows "Must change password".
  - A 7-character password shows "The password must have at least 8 characters."; an existing email shows "… already has an account.".
  - Your own row: Disable is greyed with "You cannot remove your own admin access."; Edit shows the role locked with the same reason.
  - Edit the new user's role to Admin and back; Disable (confirm) → "Disabled", Enable → "Must change password".
  - Reset password → show-once box again. In a private window sign in as that user → forced to choose a password → dashboard.
  - Activity lists every one of these actions.
  - Delete the test account afterwards: `DELETE FROM users WHERE email = 'pytest-ui@example.test';`.

- [ ] **Step 6: Commit**

```powershell
git add dashboard/src/admin
git commit -m "Admin portal: Users page (add with temporary password, edit, reset, disable / enable)"
```

---

### Task 10: Full verification, deployment docs, Docker rebuild

**Files:**
- Modify: `README.md` (root), `deploy/README.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Root README** — in `README.md`, replace "the dashboard needs a sign-in (email and password, accounts created by an administrator — see [backend/README.md](backend/README.md#users-and-sign-in))." with "the dashboard needs a sign-in. Admins manage accounts and saved plans in the admin portal (`/admin`); viewers see everything and try plans — see [backend/README.md](backend/README.md#users-and-sign-in).", and in "Run it on this PC" change the `app.users create` line to
  `.venv\Scripts\python -m app.users create you@example.org --name "Your Name" --admin  # the first administrator`.

- [ ] **Step 2: Deploy README** — read `deploy/README.md` and, where it describes creating the first account (search for `app.users`), add `--admin` to the create command and this note after it: "Existing installations: after updating, every account is a viewer — promote the administrator with `docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api python -m app.users role you@example.org admin` (Windows service: `python -m app.users role …` from the backend folder)."

- [ ] **Step 3: Whole backend suite**

Run (from `backend/`): `.venv\Scripts\python -m pytest -q` → all pass (the previous 31 minus the removed reload test, plus the new role tests).

- [ ] **Step 4: Frontend production build**

Run (from `dashboard/`): `npm run build` → exits 0 (runs `tsc -b` and `vite build`).

- [ ] **Step 5: Promote your account and rebuild the Docker stack** (the running API image predates migration 0002 and is crash-looping)

```powershell
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml --env-file deploy/.env ps
```

Expected: `api` Up (not Restarting); `docker logs school-planning-api-1` shows `Running upgrade 0002 -> 0003` or no pending migration and `data loaded`. Promote the user's own account (ask the user which email): `docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api python -m app.users role <email> admin`.

- [ ] **Step 6: Smoke test on http://localhost:8080** — sign in as the admin: header menu shows Admin portal; `/admin/users` and `/admin/activity` load; sign in as a viewer: no save buttons, `/admin` redirects to the dashboard.

- [ ] **Step 7: Commit**

```powershell
git add README.md deploy/README.md
git commit -m "Docs: roles, first administrator, promoting an admin after the update"
```
