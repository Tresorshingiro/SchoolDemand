# Backend — FastAPI + PostgreSQL / PostGIS

```
backend/
  app/
    main.py            the FastAPI app (routes under /api, docs at /api/docs), loads the data at startup
    config.py          settings from the environment / .env (DATABASE_URL, ADMIN_TOKEN, CORS_ORIGINS …)
    db.py, models.py   SQLAlchemy engine and tables (following database/schema.dbml)
    domain/            the engine: analysis.py (the rules), projection.py (base year + 4 years), dashboard.py (API shapes)
    imports/           data uploads: tables, report, checks, publish, service (upload -> check -> publish), worker
    services/          repository.py (reads the database into the engine's inputs), store.py (in-memory data of every
                       school year, ready-made JSON, projection cache), auth.py (sessions, roles), portal.py (sign-in
                       through the MINEDUC GIS portal), audit.py
    routers/           system (health, reload), auth, data (school years + boundaries), projection, scenarios,
                       admin (users, audit log), data_admin (uploads, imports)
    users.py           manage user accounts (python -m app.users ...)
  alembic/             database migrations
  etl/load_version2.py loads data-sources/ through the same pipeline as the admin portal
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
.venv\Scripts\python -m pytest -q                               # the whole suite (≈ 5 min)
```

## Users and sign-in

Everyone signs in with their **MINEDUC GIS portal** account (`PORTAL_URL`, default
`https://gh.space.gov.rw/portal`): the API sends the username and password to the portal's `generateToken`, asks the
portal who the token belongs to (`community/self`), and drops the portal token. No password is stored here, and there
are no accounts to create: a portal user who signs in for the first time is added to `users` as an **admin**, with the
name and email of their portal profile (refreshed at each sign-in). There are two roles: **admins** manage accounts
(admin portal, `/admin`), the data and saved plans; **viewers** see all the data and can try plans but not save them.
An admin can make someone a viewer or disable them in the admin portal; that is kept at their next sign-ins. Passwords
are changed and reset in the portal. From the command line:

```powershell
.venv\Scripts\python -m app.users role jdoe viewer      # or admin
.venv\Scripts\python -m app.users disable jdoe          # blocks sign-in here, signs out everywhere (enable to undo)
.venv\Scripts\python -m app.users list
```

The API must reach the portal over HTTPS; when it cannot, sign-in answers 503. Signing in sets an HttpOnly cookie
(`sp_session`, SameSite=Lax, Secure over HTTPS) holding a random token; the database keeps only its SHA-256
(`user_sessions`). A session lasts until the browser closes (at most `SESSION_HOURS`, 12) or, with "Remember me",
`REMEMBER_DAYS` (30). Ten wrong passwords for one username within 15 minutes block that username here for 15 minutes
(before the portal locks the account). Every route except `/api/health` and `/api/auth/login` answers 401 without a
session; changing saved plans and `/api/admin/*` answer 403 for viewers. Saved plans record who created them; admin
actions and first sign-ins are recorded in `audit_log`.

The database connection comes from `DATABASE_URL`, or is built from `deploy/.env` (POSTGRES_USER / PASSWORD / DB,
host localhost, port 5433). For another database copy `.env.example` to `.env`.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/health` | API, database and the loaded import (no sign-in needed) |
| POST | `/api/auth/login` | `{"username", "password", "remember"}` (MINEDUC GIS portal account) → sets the session cookie |
| POST | `/api/auth/logout` | ends the session |
| GET | `/api/auth/me` | the signed-in user (401 when not signed in) |
| GET | `/api/meta` | levels, grades, capacity, source, data-quality counts, school years (`actualYears`, `baseYear`, `projectionYears`), live `sources` |
| GET | `/api/meta`, `/api/school-levels`, `/api/grades`, `/api/combos` `?year=` | a published school year (default: the newest) |
| GET | `/api/school-levels` | 2026, one record per school × level |
| GET | `/api/grades` | 2026, one row per school × grade |
| GET | `/api/combos` | 2026, students and class groups per school × grade × combination |
| GET | `/api/boundaries/{country,districts,sectors}` | GeoJSON outlines (PostGIS) |
| GET | `/api/projection/config` | years, levels, how new students enter, the default intake plan |
| GET | `/api/projection/default` | the projection with the default (catchment) plan |
| POST | `/api/projection/run` | the projection for `{"intake": {"N1": {"Gasabo": [2027, 2028, 2029, 2030], …}}}` |
| GET / POST | `/api/scenarios` | saved intake plans: list (any user) / save a new one (admins) |
| GET / PUT / DELETE | `/api/scenarios/{id}` | open (any user) / update / delete (admins) a saved plan |
| GET | `/api/admin/users` | admin: everyone who has signed in |
| PATCH | `/api/admin/users/{id}` | admin: `{"role", "is_active"}` |
| GET | `/api/admin/audit` | admin: who changed what, newest first (`limit`, `before`, `user_id`, `action`) |
| POST | `/api/admin/reload` | re-read the database after an import (signed-in admin, or header `X-Admin-Token`) |
| GET | `/api/admin/data/sources` | admin: the live data of each kind |
| POST | `/api/admin/data/uploads` | admin: multipart `kind`, `file`, `academic_year` → the import, checked in the background |
| GET | `/api/admin/data/imports`, `/imports/{id}` | admin: history; one import with its report |
| POST | `/api/admin/data/imports/{id}/publish` · `discard` · `recheck` · `withdraw` | admin: the import's lifecycle |
| GET | `/api/admin/data/templates/{kind}` | admin: an example file |
| POST | `/api/scenarios/{id}/copy` | admin: copy an archived plan into the current years |

## Updating the data

In the admin portal (Data → Upload): school data (one school year), the catchment file, or NISR district totals.
The file is checked (errors block publishing, warnings are listed with the rows concerned); Publish replaces the live
data in one transaction and reloads the API. Every import is kept (`UPLOAD_DIR`, default `../data-uploads`) and can be
published again; a school year or the NISR figures can be withdrawn. The newest published school year is the base of
the projection (the four years after it); saved plans made for an older base year are archived and can be copied.
From the command line, `python -m etl.load_version2` loads `data-sources/` through the same checks (files already
live are skipped).

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
