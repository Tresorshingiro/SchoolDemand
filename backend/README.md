# Backend — FastAPI + PostgreSQL / PostGIS

```
backend/
  app/
    main.py            the FastAPI app (routes under /api, docs at /api/docs), loads the data at startup
    config.py          settings from the environment / .env (DATABASE_URL, ADMIN_TOKEN, CORS_ORIGINS …)
    db.py, models.py   SQLAlchemy engine and tables (following database/schema.dbml)
    domain/            the engine: analysis.py (2026 rules), projection.py (2026-2030), dashboard.py (API shapes)
    services/          repository.py (reads the database into the engine's inputs), store.py (in-memory data,
                       ready-made JSON, projection cache)
    routers/           system (health, reload), data (2026 + boundaries), projection, scenarios
  alembic/             database migrations
  etl/load_version2.py import job for the development data (data-sources/)
  tests/               pytest, against the loaded database
```

## Set up (development)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
docker compose -f ..\deploy\docker-compose.yml --env-file ..\deploy\.env up -d db    # PostGIS on localhost:5433
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m etl.load_version2
.venv\Scripts\python -m uvicorn app.main:app --reload          # http://localhost:8000/api/docs
.venv\Scripts\python -m pytest -q                               # 14 tests
```

The database connection comes from `DATABASE_URL`, or is built from `deploy/.env` (POSTGRES_USER / PASSWORD / DB,
host localhost, port 5433). For another database copy `.env.example` to `.env`.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/health` | API, database and the loaded import |
| GET | `/api/meta` | levels, grades, capacity, source, data-quality counts |
| GET | `/api/school-levels` | 2026, one record per school × level |
| GET | `/api/grades` | 2026, one row per school × grade |
| GET | `/api/combos` | 2026, students and class groups per school × grade × combination |
| GET | `/api/boundaries/{country,districts,sectors}` | GeoJSON outlines (PostGIS) |
| GET | `/api/projection/config` | years, levels, how new students enter, the default intake plan |
| GET | `/api/projection/default` | the projection with the default (catchment) plan |
| POST | `/api/projection/run` | the projection for `{"intake": {"N1": {"Gasabo": [2027, 2028, 2029, 2030], …}}}` |
| GET / POST | `/api/scenarios` | saved intake plans: list / save a new one |
| GET / PUT / DELETE | `/api/scenarios/{id}` | open / update / delete a saved plan |
| POST | `/api/admin/reload` | re-read the database after an import (header `X-Admin-Token`) |

Responses are prepared once and sent gzipped. The data is read from the database at startup (≈10 s) and kept in
memory; a projection for a new plan takes ≈2 s and is cached (16 plans by default, `PROJECTION_CACHE_SIZE`).

## The engine

`app/domain/analysis.py` and `projection.py` hold every rule (their docstrings explain them). The Excel scripts in
`scripts/` import the same modules, so the workbooks, the API and the dashboard always agree. Change a rule there,
then run the tests (`test_default_projection_matches_the_files` compares the database-backed projection with the
file-based one).

## Database changes

Edit `app/models.py`, then `.venv\Scripts\python -m alembic revision --autogenerate -m "what changed"`, check the
file in `alembic/versions/`, and `alembic upgrade head`. The API container runs `alembic upgrade head` on start.
