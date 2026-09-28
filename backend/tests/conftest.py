"""Integration tests: they need the database with an import loaded (python -m etl.load_version2)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text

from app import models as M
from app.db import SessionLocal, engine
from app.services.auth import hash_password

TEST_EMAIL, TEST_PASSWORD = "pytest-user@example.test", "pytest-password-123"


def _database_ready() -> bool:
    try:
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT count(*) FROM import_runs WHERE status = 'success'")).scalar())
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def test_user():
    """A throw-away account, removed after the tests."""
    with SessionLocal() as s:
        s.execute(delete(M.User).where(M.User.email == TEST_EMAIL))
        s.add(M.User(email=TEST_EMAIL, full_name="Pytest User", password_hash=hash_password(TEST_PASSWORD), is_active=True))
        s.commit()
    yield {"email": TEST_EMAIL, "password": TEST_PASSWORD}
    with SessionLocal() as s:
        s.execute(delete(M.User).where(M.User.email == TEST_EMAIL))
        s.commit()


@pytest.fixture(scope="session")
def app_():
    if not _database_ready():
        pytest.skip("database not reachable or not loaded — start it and run python -m etl.load_version2")
    from app.main import app

    with TestClient(app):  # runs the startup once: loads the data into memory
        yield app


@pytest.fixture(scope="session")
def client(app_, test_user):
    """Signed in as the test user (the session cookie stays in the client)."""
    c = TestClient(app_)  # no `with`: the data is already loaded by app_
    r = c.post("/api/auth/login", json=test_user)
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def anonymous(app_):
    """Not signed in."""
    return TestClient(app_)
