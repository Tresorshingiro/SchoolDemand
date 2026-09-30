# School planning — classroom sufficiency 2026–2030

Do Rwanda's schools have enough classrooms, now and as cohorts move up and new children start school? A web
dashboard (map, charts, school table, PDF report, editable intake plans) on top of a FastAPI backend and a
PostgreSQL + PostGIS database. Visitors see a public landing page; the dashboard needs a sign-in. Admins manage accounts
and saved plans in the admin portal (`/admin`); viewers see everything and try plans — see
[backend/README.md](backend/README.md#users-and-sign-in).

```
 browser ── dashboard (React, Vite) ──/api──▶ FastAPI (backend/app) ──▶ PostgreSQL + PostGIS
                                               │ analysis + projection engine (app/domain)
 data-sources/*.xlsx, boundaries ──▶ import job (backend/etl) ──┘
```

| Folder | What |
|---|---|
| `backend/` | FastAPI API, database models and migrations (Alembic), import job, the analysis and projection engine, tests — [backend/README.md](backend/README.md) |
| `dashboard/` | React + TypeScript + Tailwind + ArcGIS + ECharts; reads everything from the API — [dashboard/README.md](dashboard/README.md) |
| `deploy/` | Docker Compose (database + API + nginx) and the Windows / IIS setup — [deploy/README.md](deploy/README.md) |
| `data-sources/` | Development data until the MINEDUC / NISR data is connected: `Version 2.xlsx` (2026 roster), `Chachement area.xlsx` (children aged 3 per pre-primary catchment), `boundaries/` (districts, sectors, country) |
| `database/schema.dbml` | Full database design (paste into dbdiagram.io); the backend builds the part in use today |
| `scripts/` | Excel workbooks (`build_workbook.py`, `build_projection_workbook.py`, …) and `build_boundaries.py`; they use the same engine as the API |

## Run it on this PC (development)

```powershell
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d db   # PostGIS on localhost:5433
cd backend
.venv\Scripts\python -m alembic upgrade head                                 # tables
.venv\Scripts\python -m etl.load_version2                                    # load data-sources/ (≈30 s)
.venv\Scripts\python -m app.users create you@example.org --name "Your Name" --admin  # the first administrator
.venv\Scripts\python -m uvicorn app.main:app --reload                        # API on :8000, docs /api/docs
cd ..\dashboard
npm install; npm run dev                                                     # http://localhost:5173
```

First time: `copy deploy\.env.example deploy\.env` (set a password) and create the Python environment — see
[backend/README.md](backend/README.md).

## Run it on a server

`docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build`, then load the data — or the
Windows setup without Docker (PostgreSQL + PostGIS, the API as a Windows service, IIS). Both in
[deploy/README.md](deploy/README.md).

## Update the data

Admins upload new files in the admin portal (Data): school data for a school year, the catchment file, or NISR
district totals. Each file is checked, then published; the history keeps every import and any earlier one can be
published again. A new school year becomes the base of the projection (the four years after it) and earlier years stay
as actual history. `python -m etl.load_version2` does the same for the files in `data-sources/`. The MINEDUC API will
be a connector feeding the same checks once its documentation and access are available.
