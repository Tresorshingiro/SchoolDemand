# Deploying

Two ways, same application. Pick Docker when the server can run it (one command, identical to development);
otherwise the Windows setup.

## A. Docker Compose (Linux or Windows server with Docker)

```bash
cp deploy/.env.example deploy/.env          # set POSTGRES_PASSWORD, ADMIN_TOKEN; WEB_PORT if 8080 is taken
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm api python -m etl.load_version2
docker compose -f deploy/docker-compose.yml --env-file deploy/.env restart api
```

Open `http://SERVER:8080` and sign in with a MINEDUC GIS portal account: every portal user can sign in and becomes an
administrator at their first sign-in (see [backend/README.md](../backend/README.md#users-and-sign-in)). The API must
reach `https://gh.space.gov.rw/portal` (`PORTAL_URL`) over HTTPS. Existing installations: the email / password
accounts made before can no longer sign in; they stay in the user list (and on the history), disable them there. Three containers: `db` (PostgreSQL 17 + PostGIS, data in the `pgdata` volume), `api`
(FastAPI; runs the migrations on start), `web` (nginx: the dashboard, `/api` forwarded to the API). The import reads
the files in `data-sources/` (mounted read-only); files uploaded in the admin portal are kept in the `uploads` volume
(the import history and the way back to an earlier file). Back up with
`docker compose … exec db pg_dump -U school school_planning > backup.sql`, and the `uploads` volume with the database.

## B. Windows server without Docker (IIS)

1. **PostgreSQL 16/17 with PostGIS** — install PostgreSQL, then Application Stack Builder → Spatial Extensions →
   PostGIS. Create the database and user:
   ```sql
   CREATE USER school WITH PASSWORD '…';
   CREATE DATABASE school_planning OWNER school;
   \c school_planning
   CREATE EXTENSION postgis;
   ```
2. **API** — install Python 3.12, copy the repository (or at least `backend/` and `data-sources/`), then:
   ```powershell
   cd backend
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   copy .env.example .env        # DATABASE_URL=postgresql+psycopg://school:…@127.0.0.1:5432/school_planning
                                 # UPLOAD_DIR=D:\school-planning\uploads (a folder the service can write; back it up)
   .venv\Scripts\python -m alembic upgrade head
   .venv\Scripts\python -m etl.load_version2
   ..\deploy\windows\install-api-service.ps1 -Nssm C:\tools\nssm\win64\nssm.exe   # as Administrator
   ```
   The API then runs as the Windows service *SchoolPlanningAPI* on `127.0.0.1:8000` (logs in `backend\logs`).
3. **Dashboard** — build it once (on any PC with Node 20+): `cd dashboard; npm ci; npm run build`. In IIS, create a
   site whose folder holds `dashboard\dist\*` plus `deploy\windows\web.config`. Install the IIS modules
   *URL Rewrite* and *Application Request Routing*, and tick **Enable proxy** in ARR → Server Proxy Settings; the
   `web.config` then forwards `/api` to the service and sends the page addresses (`/login`, `/dashboard` …) to
   `index.html`.

If the site lives under a sub-path (an IIS application such as `https://server/school/`), build it with that path:
`$env:VITE_BASE='/school/'; npm run build` — the pages and the API (`/school/api`) then work under it. If the API is on
another host, build with `VITE_API_URL` (e.g. `https://api-server/api`) and set `CORS_ORIGINS` for the API; the sign-in
cookie then needs both on the same site (same domain).

The sign-in cookie is marked Secure when the browser uses HTTPS (the `web.config` and nginx tell the API). If a proxy
in front terminates HTTPS without saying so, set `SESSION_COOKIE_SECURE=true` for the API.

## Inside Education Mapping (gh.space.gov.rw)

Education Mapping shows the dashboard in a frame. Two ways to keep the sign-in working there, usable together:

1. **Frame from gis.mineduc.gov.rw** (External URL `https://gis.mineduc.gov.rw/school/dashboard`). The browser treats
   the frame as another site and keeps the sign-in cookie only when it is `SameSite=None; Secure; Partitioned`, which
   the API sends whenever the cookie is Secure. On the MINEDUC server put `SESSION_COOKIE_SECURE=true` in
   `backend\.env` (the API only sees plain HTTP from IIS) and restart the service. Chrome and Edge keep such a cookie;
   Safari blocks every cookie of a frame from another site, so use 2. there.
2. **The dashboard served from gh.space.gov.rw** (External URL `https://gh.space.gov.rw/school/dashboard`). The frame is
   then on the same site as Education Mapping and any browser keeps the cookie; the data stays on the MINEDUC server.
   On the Geohub server, the IIS application `school` holds `dashboard\dist\*` built with
   `$env:VITE_BASE='/school/'; npm run build` (no `VITE_API_URL`) plus `deploy\windows\geohub-web.config` renamed
   `web.config`: it forwards `/school/api/*` to `https://gis.mineduc.gov.rw/api/*`. Needs URL Rewrite and ARR (Enable
   proxy), the server variables `HTTP_HOST` and `HTTP_X_FORWARDED_PROTO` allowed in URL Rewrite → View Server
   Variables at the server level, and the Geohub server able to reach `https://gis.mineduc.gov.rw`. Check with
   `https://gh.space.gov.rw/school/api/health`: it must answer JSON, not the page.

Either way users sign in once more inside the frame, with the same portal account as Education Mapping ("Remember me"
keeps them signed in for 30 days); signing in only once needs Education Mapping to pass its portal token to the page.

## After an import

Restart the API (`docker compose … restart api`, or restart the *SchoolPlanningAPI* service), or call
`POST /api/admin/reload` with the header `X-Admin-Token: <ADMIN_TOKEN>`. Saved intake plans are kept.

## Checklist before going live

- [ ] Change the database password and set an `ADMIN_TOKEN` (long random string).
- [ ] Put the site behind HTTPS (IIS certificate or a reverse proxy in front of nginx).
- [ ] Only the web port is open to users; the database (5432/5433) and the API port (8000) stay internal.
- [ ] Check that the server reaches the portal: `Invoke-WebRequest https://gh.space.gov.rw/portal/sharing/rest/info?f=json`.
      Nobody can see the data without a portal account. Make people viewers in the admin portal → Users when they
      should not manage data, accounts or the shared plans.
- [ ] Schedule a database backup.
