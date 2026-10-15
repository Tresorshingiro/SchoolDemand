"""Integration tests: they need the database with an import loaded (python -m etl.load_version2).

The MINEDUC GIS portal is replaced by a fake one (fake_sign_in): it knows every username starting with "pytest-",
with the password PORTAL_PASSWORD.
"""
import secrets
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app import models as M
from app.db import SessionLocal, engine
from app.services import portal

TEST_USERNAME, PORTAL_PASSWORD = "pytest-user", "portal-password-123"
PYTEST_USERS = "pytest-%"  # every account the tests create matches this
PORTAL_NAMES = {TEST_USERNAME: "Pytest User"}


def fake_sign_in(username: str, password: str) -> portal.PortalUser:
    """The fake portal: the canonical username is lower case, as the portal writes it."""
    if not username.lower().startswith("pytest-") or password != PORTAL_PASSWORD:
        raise portal.WrongCredentials("Invalid username or password.")
    name = username.lower()
    return portal.PortalUser(name, PORTAL_NAMES.get(name), f"{name}@example.test")


def browser(app) -> TestClient:
    """A client that behaves like the dashboard: it sends the header the API requires on changes (csrf_refused)."""
    return TestClient(app, headers={"X-Requested-With": "fetch"})


def _database_ready() -> bool:
    try:
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT count(*) FROM import_runs WHERE is_live AND kind = 'school_data'")).scalar())
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session", autouse=True)
def _fake_portal():
    real = portal.sign_in
    portal.sign_in = fake_sign_in
    yield
    portal.sign_in = real


@pytest.fixture(scope="session", autouse=True)
def _remove_test_accounts():
    """Accounts made by the tests (fixtures or first sign-ins) are removed at the end."""
    yield
    if _database_ready():
        with SessionLocal() as s:
            s.execute(delete(M.User).where(M.User.username.like(PYTEST_USERS)))
            s.commit()


def add_user(username: str, role: str, full_name: str | None = None) -> int:
    """An account as if the person had signed in before."""
    with SessionLocal() as s:
        s.execute(delete(M.User).where(M.User.username == username))
        s.add(M.User(username=username, full_name=full_name, role=role, is_active=True))
        s.commit()
        return s.scalar(select(M.User.id).where(M.User.username == username))


@pytest.fixture(scope="session")
def test_user():
    """A throw-away administrator account."""
    add_user(TEST_USERNAME, "admin", "Pytest User")
    return {"username": TEST_USERNAME, "password": PORTAL_PASSWORD}


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
    c = browser(app_)  # no `with`: the data is already loaded by app_
    r = c.post("/api/auth/login", json=test_user)
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="session")
def make_client(app_):
    """Factory: a new throw-away account, signed in. make_client("admin" | "viewer")."""
    def make(role: str = "viewer") -> SimpleNamespace:
        username = f"pytest-{role}-{secrets.token_hex(4)}"
        user_id = add_user(username, role, f"Pytest {role}")
        c = browser(app_)
        r = c.post("/api/auth/login", json={"username": username, "password": PORTAL_PASSWORD})
        assert r.status_code == 200, r.text
        return SimpleNamespace(client=c, username=username, password=PORTAL_PASSWORD, id=user_id)

    return make


@pytest.fixture(scope="session")
def viewer(make_client):
    """A signed-in viewer shared by the tests that only read."""
    return make_client("viewer")


@pytest.fixture
def anonymous(app_):
    """Not signed in."""
    return browser(app_)
