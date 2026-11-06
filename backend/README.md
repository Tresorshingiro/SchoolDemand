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
                       school_plans (planned new schools), admin (users, audit log), data_admin (uploads, imports)
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
are no accounts to create: a portal user who signs in for the first time is added to `users` as a **viewer**, with the
name and email of their portal profile (refreshed at each sign-in). There are two roles: **admins** manage accounts
(admin portal, `/admin`), the data and saved plans; **viewers** see all the data and can try plans but not save them.
An admin makes someone an admin, a viewer again, or disables them in the admin portal; that is kept at their next
sign-ins. Passwords are changed and reset in the portal. From the command line:

```powershell
.venv\Scripts\python -m app.users role jdoe viewer      # or admin
.venv\Scripts\python -m app.users disable jdoe          # blocks sign-in here, signs out everywhere (enable to undo)
.venv\Scripts\python -m app.users list
```

**Single sign-on.** The dashboard has no sign-in form: a page that needs a session goes through the portal's OAuth
sign-in (`oauth2/authorize`, implicit grant) for the dashboard's application item in the portal (client ID
`zCxgnSvJJTL8iCD1`; its redirect URLs must list the site's base on every host, e.g. `https://gh.space.gov.rw/school/`).
Someone already signed in to the portal comes straight back — the first time the portal asks them to Allow the app,
unless a portal administrator approved it for the organization. The portal returns a token in the address; the
dashboard sends it to `POST /api/auth/portal-token`; the API asks `community/self` whose it is and opens the session.
Signing out ends the session and the portal's (`oauth2/signout`). Dashboard settings: `VITE_PORTAL_URL`,
`VITE_PORTAL_CLIENT_ID` (defaults above). `POST /api/auth/login` (username and password) still works for scripts and
tests. (`oauth2/platformSelf`, which would skip the redirect, refuses the app: OAUTH_0068 "Invalid client_id".)

The API must reach the portal over HTTPS; when it cannot, sign-in answers 503. Signing in sets an HttpOnly cookie
(`sp_session`, SameSite=Lax, Secure over HTTPS) holding a random token; the database keeps only its SHA-256
(`user_sessions`). A session lasts until the browser closes (at most `SESSION_HOURS`, 12) or, with "Remember me",
`REMEMBER_DAYS` (30). Ten wrong passwords for one username within 15 minutes block that username here for 15 minutes
(before the portal locks the account). Every route except `/api/health` and `/api/auth/login` answers 401 without a
session (`/api/auth/portal-token` neither); changing saved plans and `/api/admin/*` answer 403 for viewers. Saved plans record who created them; admin
actions and first sign-ins are recorded in `audit_log`.

The database connection comes from `DATABASE_URL`, or is built from `deploy/.env` (POSTGRES_USER / PASSWORD / DB,
host localhost, port 5433). For another database copy `.env.example` to `.env`.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/health` | API, database, the school years and class streams loaded (no sign-in needed: no file or person names) |
| POST | `/api/auth/login` | `{"username", "password", "remember"}` (MINEDUC GIS portal account) → sets the session cookie |
| POST | `/api/auth/portal-token` | `{"token", "remember"}`: the signed-in portal user's token (single sign-on) → sets the session cookie |
| POST | `/api/auth/logout` | ends the session |
| GET | `/api/auth/me` | the signed-in user (401 when not signed in) |
| GET | `/api/meta` | levels, grades, capacity, source, data-quality counts, school years (`actualYears`, `baseYear`, `projectionYears`), live `sources` |
| GET | `/api/meta`, `/api/school-levels`, `/api/grades`, `/api/combos` `?year=` | a published school year (default: the newest) |
| GET | `/api/school-levels` | 2026, one record per school × level; `t` = its teachers (null = no teacher data); `?capacity=` (20-100): at that many students per classroom |
| GET | `/api/grades` | 2026, one row per school × grade; `?capacity=` as above |
| GET | `/api/combos` | 2026, students and class groups per school × grade × combination |
| GET | `/api/boundaries/{country,districts,sectors}` | GeoJSON outlines (PostGIS; loaded from Education Mapping's boundary service, see Updating the data) |
| GET | `/api/projection/config` | years, levels, how new students enter, the default intake plan, the repetition and dropout `rates` |
| GET | `/api/projection/default` | the projection with the default (catchment) plan |
| POST | `/api/projection/run` | the projection for `{"intake": {"N1": {"Gasabo": [2027, 2028, 2029, 2030], …}}, "schools": [planned new schools]}`; a planned school is `{"name", "latitude", "longitude", "levels": {"PRI": 12}, "opening_year", "walking_km"}` (one level, or NUR + PRI) and appears in the rows as code -1, -2 …, described in `planned` (with `ring`, the schools within walking distance on the network, `area`, `unreachable`, `snap_km`, `on_main_network`; 422 when walking distance is not set up, 503 when the Esri Rwanda routing service does not answer). What-if fields, never saved: `"capacity"` (students per classroom, every level, 20-100, default 46), `"repetition"`, `"dropout"` (default true) |
| GET / POST | `/api/scenarios` | saved intake plans: list (any user) / save a new one (admins) |
| GET / PUT / DELETE | `/api/scenarios/{id}` | open (any user) / update / delete (admins) a saved plan |
| GET / POST | `/api/school-plans` | saved plans of new schools: list (any user) / save a new one (admins; the summary of what it changes is stored with it) |
| GET / PUT / DELETE | `/api/school-plans/{id}` | open (any user) / update / delete (admins) a plan of new schools |
| POST | `/api/school-plans/{id}/copy` | admin: copy an archived plan of new schools into the current years |
| GET | `/api/admin/users` | admin: everyone who has signed in |
| PATCH | `/api/admin/users/{id}` | admin: `{"role", "is_active"}` |
| GET | `/api/admin/audit` | admin: who changed what, newest first (`limit`, `before`, `user_id`, `action`) |
| POST | `/api/admin/reload` | re-read the database after an import (signed-in admin, or header `X-Admin-Token`) |
| GET | `/api/admin/data/sources` | admin: the live data of each kind |
| GET | `/api/admin/data/walking` | admin: the walking-distance service (Esri Rwanda): set up, answering, its travel mode |
| POST | `/api/admin/data/uploads` | admin: multipart `kind`, `file`, `academic_year` → the import, checked in the background |
| GET | `/api/admin/data/imports`, `/imports/{id}` | admin: history; one import with its report |
| POST | `/api/admin/data/imports/{id}/publish` · `discard` · `recheck` · `withdraw` | admin: the import's lifecycle |
| GET | `/api/admin/data/templates/{kind}` | admin: an example file |
| POST | `/api/scenarios/{id}/copy` | admin: copy an archived plan into the current years |

## Updating the data

In the admin portal (Data → Upload): school data (one school year), the catchment file, NISR district totals, the
MINEDUC repetition and dropout rates (the workbook with its two sheets; the projection needs them, so they are
replaced, never withdrawn) or the MINEDUC teachers file (one school year).
The file is checked (errors block publishing, warnings are listed with the rows concerned); Publish replaces the live
data in one transaction and reloads the API. Every import is kept (`UPLOAD_DIR`, default `../data-uploads`) and can be
published again; a school year or the NISR figures can be withdrawn. The newest published school year is the base of
the projection (the four years after it); saved plans made for an older base year are archived and can be copied.
From the command line, `python -m etl.load_version2` loads `data-sources/` through the same checks (files already
live are skipped, and so is a kind whose live data came from another file, such as an upload in the admin portal:
`--replace` publishes over it).

### Boundaries

Provinces, districts and sectors come from Education Mapping's public feature service on the MINEDUC GIS portal
(`BOUNDARIES_URL`, default *Administrative boundaries corrected* on `gh.space.gov.rw`, boundaries as of 2022). The import
job loads them into the database, simplified to about 20 m (`BOUNDARIES_SIMPLIFY`, degrees), with the country outline as
the union of the districts; `python -m etl.boundaries` refreshes only them (then restart the API or reload). Rows keep
their code, so schools keep their sector when a name changes; names follow the service's spelling, and school data is
matched to them ignoring case (the school data writes Ngororero, Nyagatare and Rulindo's sectors in capitals). The job
refuses a service answer without 30 districts and 416 sectors.

### Walking distance (planned schools)

Nothing is uploaded: the API asks Esri Rwanda's network analysis services (`ESRI_ROUTING_URL`, default the
`Routing042026` NAServer on `esrirw.rw`, built from OpenStreetMap roads and kept up to date by Esri Rwanda). For each
planned school, one Origin Destination Cost Matrix solve gives the walking distance to the schools within its distance in
a straight line, in the service's *Walking* travel mode with its one-way restriction removed, plus each point's walk to the
road; one Service Area solve gives the area drawn on the map. A solve takes about 0.3 s (about 3 s for 20 km in Kigali);
results are kept in memory (`WALKING_CACHE_SIZE`, 256). The API signs in to Esri Rwanda's portal with `ESRI_USERNAME` /
`ESRI_PASSWORD` (an Esri Rwanda account, kept on the server; or a fixed `ESRI_TOKEN`) and needs HTTPS access to
`esrirw.rw`. Without them planned schools are unavailable (422); when the service does not answer, a run with planned
schools answers 503 and the dashboard switches them off; everything else keeps working. Admin portal → Data shows whether
the service answers.

Responses are prepared once and sent gzipped. The data is read from the database at startup (≈10 s) and kept in
memory; a projection for a new plan takes ≈2 s and is cached (16 plans by default, `PROJECTION_CACHE_SIZE`).

## The engine

`app/domain/analysis.py` and `projection.py` hold every rule (their docstrings explain them); the API and the
dashboard use nothing else. Change a rule there, then run the tests (`test_default_projection_matches_the_files` compares the database-backed projection with the
file-based one).

## Database changes

Edit `app/models.py`, then `.venv\Scripts\python -m alembic revision --autogenerate -m "what changed"`, check the
file in `alembic/versions/`, and `alembic upgrade head`. The API container runs `alembic upgrade head` on start.
