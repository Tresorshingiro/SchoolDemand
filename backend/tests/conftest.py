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
            return bool(conn.execute(text("SELECT count(*) FROM import_runs WHERE is_live AND kind = 'school_data'")).scalar())
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
