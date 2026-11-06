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

Open `http://SERVER:8080` and sign in with a MINEDUC GIS portal account: every portal user can sign in and becomes a
viewer at their first sign-in; an administrator gives the admin role in the admin portal → Users, or
`python -m app.users role <username> admin` for the very first one (see
[backend/README.md](../backend/README.md#users-and-sign-in)). The API must
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
3. **Dashboard** — build it once (on any PC with Node 20+): `cd dashboard; npm ci; npm run build`. It is built for
   the sub-path `/school/`, so in IIS create an application named `school` whose folder holds `dashboard\dist\*` plus
   `deploy\windows\web.config`. Install the IIS modules
   *URL Rewrite* and *Application Request Routing*, and tick **Enable proxy** in ARR → Server Proxy Settings; the
   `web.config` then forwards `/api` to the service and sends the page addresses (`/login`, `/dashboard` …) to
   `index.html`.

The build lives under the sub-path `/school/` (an IIS application such as `https://server/school/`): the pages and the
API (`/school/api`) work under it. On a Windows PC where npm runs scripts through Git Bash, a `VITE_BASE` or
`VITE_API_URL` that starts with `/` is turned into a Windows folder path (`/Users/.../Git/school/`): set
`$env:MSYS_NO_PATHCONV='1'` first, and check `dist\index.html` refers to `/school/assets/...` before deploying. For another path, or the root of a site, build with it:
`$env:VITE_BASE='/'; npm run build` (the Docker image does this for its nginx). If the API is on
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
   On the Geohub server, the IIS application `school` holds `dashboard\dist\*` built with a plain
   `npm run build` (`/school/` is the default base; no `VITE_API_URL`) plus `deploy\windows\geohub-web.config` renamed
   `web.config` (once; later builds copy only the `dist` files and leave it in place): it forwards `/school/api/*` to
   `https://gis.mineduc.gov.rw/api/*`. It changes nothing outside `school`: it needs URL Rewrite and ARR (Enable proxy),
   sets no server variables (the `allowedServerVariables` section is locked there and would answer 500.52 everywhere),
   and the Geohub server able to reach `https://gis.mineduc.gov.rw`. Check with
   `https://gh.space.gov.rw/school/api/health`: it must answer JSON, not the page.

With 2. users sign in only once: the dashboard goes through the portal's sign-in (the app item "School Demand &
Demographics", client ID `zCxgnSvJJTL8iCD1`, approved for the organization), so someone signed in to Education Mapping
comes straight in. With 1. they sign in once more inside the frame, with the same portal account ("Remember me" keeps
them signed in for 30 days).

## Updating an installation to repetition, dropout and teachers

The update adds three tables (the API runs the migration on start). Until a repetition and dropout file is published
the API serves no data (the projection needs the rates): in the admin portal → Data, upload the MINEDUC rates workbook
(Repetition and dropout) and the teachers file (Teachers, school year 2026), check, publish. Or run
`python -m etl.load_version2` with the two files in `data-sources/`: it publishes only kinds whose live data came
from the same file names, so school data and catchment uploaded in the admin portal stay as they are.

## Updating an installation to walking distance from Esri Rwanda

Planned schools' walking distance now comes from the Esri Rwanda routing service; the walking network is no longer
uploaded. The update:

1. Set the Esri Rwanda account on the server: `ESRI_USERNAME` and `ESRI_PASSWORD` in `deploy/.env` (Docker) or
   `backend/.env` (Windows service). The server must reach `https://esrirw.rw` over HTTPS. Without them planned schools
   are unavailable and the rest of the dashboard works.
2. Install `requirements.txt` again (`osmium` and `scipy` are no longer needed) and restart the API: migration 0010
   removes the walking-network imports from the history. Their files in `UPLOAD_DIR` (`*.pbf`,
   `import-<id>.network.npz`) are no longer read and can be deleted.
3. Admin portal → Data: the *Walking distance (Esri Rwanda)* card must say Connected.

Uploads are back to 50 MB: the `web.config` / `geohub-web.config` / `nginx.conf` in this repository set that.

## Updating an installation to boundaries from Education Mapping

Districts and sectors now come from Education Mapping's *Administrative boundaries corrected* feature service on the
MINEDUC GIS portal, not from `data-sources/boundaries/`. Load them once, then restart the API:
`python -m etl.boundaries` (from `backend/`), or with Docker
`docker compose -f deploy/docker-compose.yml --env-file deploy/.env run --rm api python -m etl.boundaries`. Only the
boundaries change; 44 sector names change case (Ngororero, Nyagatare and Rulindo: "BWIRA" becomes "Bwira") and keep
their schools. The server already reaches `gh.space.gov.rw` for sign-in.

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
- [ ] Set the Esri Rwanda account (`ESRI_USERNAME`, `ESRI_PASSWORD`) for planned schools' walking distance, and check
      the server reaches it: `Invoke-WebRequest https://esrirw.rw/portal/sharing/rest/info?f=json`; then admin portal →
      Data → *Walking distance (Esri Rwanda)* says Connected.
- [ ] Schedule a database backup.
