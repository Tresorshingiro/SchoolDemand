"""Integration tests: they need the database with an import loaded (python -m etl.load_version2)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine


def _database_ready() -> bool:
    try:
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT count(*) FROM import_runs WHERE status = 'success'")).scalar())
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def client():
    if not _database_ready():
        pytest.skip("database not reachable or not loaded — start it and run python -m etl.load_version2")
    from app.main import app

    with TestClient(app) as c:  # runs the startup: loads the data into memory
        yield c
