# Deploying

Two ways, same application. Pick Docker when the server can run it (one command, identical to development);
otherwise the Windows setup.

## A. Docker Compose (Linux or Windows server with Docker)

```bash
cp deploy/.env.example deploy/.env          # set POSTGRES_PASSWORD, ADMIN_TOKEN; WEB_PORT if 8080 is taken
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm api python -m etl.load_version2
docker compose -f deploy/docker-compose.yml --env-file deploy/.env restart api
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec api python -m app.users create you@example.org --name "Your Name"
```

Open `http://SERVER:8080` and sign in with that account (more accounts: see [backend/README.md](../backend/README.md#users-and-sign-in)). Three containers: `db` (PostgreSQL 17 + PostGIS, data in the `pgdata` volume), `api`
(FastAPI; runs the migrations on start), `web` (nginx: the dashboard, `/api` forwarded to the API). The import reads
the files in `data-sources/` (mounted read-only). Back up with
`docker compose … exec db pg_dump -U school school_planning > backup.sql`.

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
   copy .env.example .env        # DATABASE_URL=postgresql+psycopg://school:…@localhost:5432/school_planning
   .venv\Scripts\python -m alembic upgrade head
   .venv\Scripts\python -m etl.load_version2
   .venv\Scripts\python -m app.users create you@example.org --name "Your Name"     # first account (asks a password)
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

## After an import

Restart the API (`docker compose … restart api`, or restart the *SchoolPlanningAPI* service), or call
`POST /api/admin/reload` with the header `X-Admin-Token: <ADMIN_TOKEN>`. Saved intake plans are kept.

## Checklist before going live

- [ ] Change the database password and set an `ADMIN_TOKEN` (long random string).
- [ ] Put the site behind HTTPS (IIS certificate or a reverse proxy in front of nginx).
- [ ] Only the web port is open to users; the database (5432/5433) and the API port (8000) stay internal.
- [ ] Create an account for each user (`python -m app.users create …`); nobody can see the data without one. Every
      signed-in user can save and delete the shared plans.
- [ ] Schedule a database backup.
