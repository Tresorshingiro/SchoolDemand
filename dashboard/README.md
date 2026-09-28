# Classroom Sufficiency Dashboard 2026

React + Vite + TypeScript + Tailwind, with an ArcGIS (`@arcgis/core`) map — same stack as BTS `ecofleet-web`.
All data comes from the FastAPI backend (`../backend`, calls in `src/api.ts`): the 2026 dataset, the district /
sector boundaries, the projection runs and the saved plans.

## Run

```powershell
npm install
npm run dev       # http://localhost:5173 — /api is forwarded to the API on http://127.0.0.1:8000 (vite.config.ts)
```

Start the API first (see `../backend/README.md`); `API_PROXY_TARGET` points the dev server at another one. Create an
account to sign in with: `python -m app.users create you@example.org` in `backend/`.

## Pages and sign-in

| Address | Page | |
|---|---|---|
| `/` | Landing page (`src/site/LandingPage.tsx`) | public |
| `/login` | Sign-in (`src/site/LoginPage.tsx`) | public; goes back to the page asked for (`?next=`) or `/dashboard` |
| `/legal/{privacy,terms,disclaimer,accessibility}` | `src/site/LegalPage.tsx` | public |
| `/dashboard` | The dashboard (`src/App.tsx`) | signed-in users only, loaded after sign-in |

The landing, sign-in and legal pages come from the School Demand & Demographics site designed by the team (their
styles in `src/site/site.css`, scoped under `.site` so they never touch the dashboard; always light). The landing
page's maps and chart are illustrations (`src/site/Illustrations.tsx`, tagged "Illustration"): Rwanda's real district
outlines (`src/site/rwandaMap.ts`, built by `python scripts/build_landing_map.py`) with decorative shading and no
figures, since the data is only for signed-in users. Routing:
`react-router-dom` in `src/main.tsx`. Sign-in state: `src/auth.tsx` — the API sets an HttpOnly session cookie, the page
asks `/api/auth/me`; when the session ends (401) the dashboard returns to the sign-in page. **Sign out** is in the
dashboard header.

## Deploy

```powershell
npm run build     # output in dist/
```

Serve `dist/` with `/api` forwarded to the API: nginx in the Docker setup (`nginx.conf`, `Dockerfile`), IIS with
`../deploy/windows/web.config` on Windows — see `../deploy/README.md`. Both also send page addresses (`/login`,
`/dashboard` …) to `index.html`. Under a sub-path build with `VITE_BASE=/school/`; when the API lives elsewhere, build
with `VITE_API_URL`. Viewers need internet access to `js.arcgis.com` and `services.arcgisonline.com` for the map.

## Map

- Basemap switch (top-right of the map): **Map** = Esri Light/Dark Gray Canvas, **Satellite** = Esri World Imagery
  with the World Boundaries and Places labels. Neither needs an API key; falls back satellite -> canvas -> OpenStreetMap.
  The viewer's choice is remembered in their browser.
- Optional: set `VITE_ARCGIS_TOKEN` in `.env` to use an Esri API key.
- Schools are drawn from the API data as a `GeoJSONLayer` built in the browser (the BTS `featureLayers.ts` pattern).
  Schools with missing or out-of-Rwanda coordinates are left off the map but stay in the table.
- **Satellite imagery is the default**; everything outside Rwanda is shaded and the view cannot pan away from Rwanda.
- **Clusters / Schools** switch: clusters group nearby schools (colour = average gap, label = number of schools; hover for
  students, schools in deficit and classrooms short; click to zoom in). From about 1:150,000 every school shows alone,
  sized by students; from about 1:40,000 (zoom 14) a close-up layer draws every school the same large size in its gap
  colour, with names from zoom 15 (GIS team's advice). Esri place names appear from about zoom 13.
- **District and sector boundaries** (switchable). Sector lines are faint and dashed; nationally they appear from about
  zoom 11 (names too), and when a district is picked in the filters only its sectors show, from about zoom 9. The
  district / sector picked in the page filters is outlined in amber.
- **Legend panel on the map** (bottom left, collapsible) is also the map's filter: click Deficit / Exact fit / Surplus
  or a class (10+ short … 10+ spare) to hide or show those schools; it holds the Clusters / Schools switch and the
  District / Sector boundary checkboxes. **Find a school** (top left) searches the schools in view.
- District names show from about zoom 9 (at national zoom the clusters and district outlines carry the view).
- Boundaries: `GET /api/boundaries/{country,districts,sectors}` (PostGIS), loaded from `data-sources/boundaries/` by
  the import job; those files come from `python scripts/build_boundaries.py` (geoBoundaries, Open Data Rwanda 2012,
  CC BY 4.0, names matched to the roster).

## Page

**Search any school** (filter bar, or press `/`): finds a school anywhere in the country by name (words in any order,
accents ignored) or code, whatever the filters. Picking one switches to a level it offers if needed, drops a district /
sector filter it is outside of, flies the map to it and opens its details (every level it offers). The map's own
**Find a school** box searches only the schools shown on the map.

One page (`src/App.tsx` -> `ProjectionPage`): 2026 actual and 2027–2030 projected, picked with the **Year** control
(the separate "Current 2026" page was removed on 2026-09-26; its 2026 figures are the Year = 2026 view). Every level;
each grade moves up one step a year and rooms stay at the 2026 count for each level. Besides the district charts, the
**Largest 50 schools by students and grade** chart ranks the schools in scope; click a bar for the school's details.
New students:
  - **N1** = children aged 3 living in each pre-primary school's catchment area (`Chachement area.xlsx`, NISR population
    shared to schools by GIS; 2030 repeats 2029 in that file). The **intake plan** table (district × year) defaults to
    the district totals; editing a district scales its schools in proportion to their catchment. Editable cell by cell,
    reset to the catchment default, or downloaded / uploaded as a CSV (`pop3_YYYY` columns).
  - **P1** = the N3 of the year before: each school's N3 moves to its own P1; stand-alone nurseries' N3 is shared to the
    primary schools of their sector. Children who did not attend pre-primary are not added.
  - **S1** = all P6 pupils of the district the year before.
  - **S4 / L3 / Y1** = all S3 students of the district the year before, split by the district's 2026 mix.
  - TVET L1–L2 short courses are not projected.

  The projection is calculated on the server (`POST /api/projection/run`, ≈2 s for a new plan, then cached); the page
  keeps showing the previous result with "Recalculating…" meanwhile. **Saved plans**: the Plan bar above the intake
  table opens, saves, saves as and deletes plans stored in the database — shared with everyone who signs in (each
  plan records who created it). The browser remembers the plan on screen (and unsaved edits) between visits.

  Excel copy of a plan: `python scripts/build_projection_workbook.py --intake intake_plan.csv`.

## PDF report

**Generate report** (filter bar, both pages) prints the current view — level, area, year and intake plan — as an
A4-landscape report: light theme, a heading with the scope and print date, every chart at full length, the map as a
snapshot and the first 25 schools of the table in its current sort. It opens the browser's print dialog; choose
**Save as PDF**. How it works: `src/print.ts` (the `.print-*` classes in `src/index.css` fix the report layout).

## Numbers

All figures come from `backend/app/domain/analysis.py` and `projection.py` — one engine, used by the API and by the
Excel scripts (`School_Classroom_Analysis_2026.xlsx`, `Classroom_Projection_2026_2030_*.xlsx`), so the dashboard and
workbooks always agree. The browser only displays and filters them.
Capacity is 45 students per classroom for every level.

To update the data, replace the files in `data-sources/` (same columns), run the import job
(`python -m etl.load_version2` in `backend/`) and restart the API. Once real 2030 catchment figures arrive, remove
2030 from `ESTIMATED` in `backend/app/domain/projection.py`.
