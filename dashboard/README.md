# Classroom Sufficiency Dashboard 2026

React + Vite + TypeScript + Tailwind, with an ArcGIS (`@arcgis/core`) map — same stack as BTS `ecofleet-web`.
All data comes from the FastAPI backend (`../backend`, calls in `src/api.ts`): the 2026 dataset, the district /
sector boundaries, the projection runs and the saved plans.

## Run

```powershell
npm install
npm run dev       # http://localhost:5173/school/ — /school/api is forwarded to the API on http://127.0.0.1:8000 (vite.config.ts)
```

Start the API first (see `../backend/README.md`); `API_PROXY_TARGET` points the dev server at another one. Sign in
with a MINEDUC GIS portal account (the API checks it with the portal).

## Pages and sign-in

| Address | Page | |
|---|---|---|
| `/`, `/dashboard` | The dashboard (`src/App.tsx`) | signed-in users only, loaded after sign-in |
| `/admin/*` | The admin portal (`src/admin/`) | administrators only |
| `/legal/{privacy,terms,disclaimer,accessibility}` | `src/site/LegalPage.tsx` | public |

There is no landing or sign-in page: a visitor without a session is sent to the MINEDUC GIS portal's sign-in
(`src/portalSignIn.ts`, OAuth implicit grant for the app item `zCxgnSvJJTL8iCD1`) and comes back to the site's base
with a portal token; `src/auth.tsx` removes it from the address and sends it to `POST /api/auth/portal-token`, which
sets the HttpOnly session cookie (the page then asks `/api/auth/me`). When the portal comes back without a token, or
the API refuses it, the page says why instead of going round again. **Sign out** (dashboard header, admin portal) ends
the session and the portal's (`oauth2/signout`), then the portal returns to the site. The return address is the
site's base on the current host, so every host the dashboard is served from must be a redirect URL of the app item.
The legal pages keep the layout of the School Demand & Demographics site (`src/site/site.css`, scoped under `.site`)
in the dashboard's theme. Routing: `react-router-dom` in `src/main.tsx`.

## Deploy

```powershell
npm run build     # output in dist/
```

Serve `dist/` with `/api` forwarded to the API: nginx in the Docker setup (`nginx.conf`, `Dockerfile`), IIS with
`../deploy/windows/web.config` on Windows — see `../deploy/README.md`. Both also send page addresses (`/login`,
`/dashboard` …) to `index.html`. The build lives under `/school/`; for another path build with `VITE_BASE` (`/` for the
root of a site, as the Docker image does); when the API lives elsewhere, build
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
- The map opens on the **whole country** filling the view (zoom is not snapped to tile levels); the **Home** button under
  the zoom buttons goes back to it, and so does clearing the district filter.
- **Legend panel on the map** (top left, under zoom and Home, collapsible) is also the map's filter: click Deficit / Exact fit / Surplus
  or a class (10+ short … 10+ spare) to hide or show those schools; it holds the Clusters / Schools switch and the
  District / Sector boundary checkboxes. **Find a school** (top left) searches the schools in view.
- District names show from about zoom 9 (at national zoom the clusters and district outlines carry the view).
- Boundaries: `GET /api/boundaries/{country,districts,sectors}` (PostGIS), loaded by the import job from Education
  Mapping's *Administrative boundaries corrected* feature service on the MINEDUC GIS portal (boundaries as of 2022;
  `python -m etl.boundaries` refreshes them).

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
  - **Demand per school from its catchment area** (Pre-Primary): the children aged 3 in each school's catchment in the
    selected year (2027 when 2026 is selected) against its N1 students in 2026, the 50 largest catchments in scope; the tooltip adds the rooms those children need and the rooms N1 has that year. Per-school figures
    come with `GET /api/projection/config` (`catchment`).
  - **P1** = the promoted N3 of the year before: each school's promoted N3 move to its own P1; stand-alone nurseries'
    are shared to the primary schools of their sector. Children who did not attend pre-primary are not added.
  - **S1** = the promoted P6 pupils of the district the year before.
  - **S4 / L3 / Y1** = the promoted S3 students of the district the year before, split by the district's 2026 mix.
  - **Repetition and dropout** (on by default; see "Trying other assumptions"), every level and year: each grade keeps its repeaters, loses its dropouts and promotes
    the rest, at its district's rates of the latest school year in the MINEDUC file (`Repetition and dropout
    rates.xlsx`, Average; Rwanda for a school without a district). Class streams follow the students; a cohort keeps
    its stream size as it moves up.
  - TVET L1–L2 short courses are not projected.

  The projection is calculated on the server (`POST /api/projection/run`, ≈2 s for a new plan, then cached); the page
  keeps showing the previous result with "Recalculating…" meanwhile. **Saved plans**: the Plan bar above the intake
  table opens, saves, saves as and deletes plans stored in the database — shared with everyone who signs in (each
  plan records who created it). The browser remembers the plan on screen (and unsaved edits) between visits.

## Planned new schools and walking distance

A planned school takes extra students only from crowded schools within walking distance along the Esri Rwanda road
network (its routing service, in Walking mode; 2 km for Pre-Primary and Primary, 3 km for other levels, editable),
counting the short way to the nearest road at each end. The API asks the service; nothing is uploaded. The map draws the
area reachable on foot after calculation, and schools with no route are counted apart. Slope and walking time are not
considered. Without the service (not set up on the server, or not answering) planned schools are unavailable and the
rest of the dashboard works.

## Trying other assumptions

The filter bar has **Students per classroom** (one number for every level, 20-100, default 46) and **Repetition** and
**Dropout** switches (default on). Anyone signed in can use them; they change only that person's screen, are never
saved and return to the defaults on reload (**Reset** does so at once). The number changes rooms required and gaps in
every year, the switches the projected years only; with a rate off, the students it affected are promoted. Full-day
levels still need a room per class stream, so a higher number may barely reduce their shortage. A saved plan's summary
always uses the defaults. The scope text shows what differs from the defaults and the PDF report states the values.

## Teachers

The **Teachers** section (under the shortage charts, same filters) shows teachers and pupils per teacher from the
MINEDUC teachers file (`t` on each school × level row; `src/teachers.ts`): cards, pupils per teacher by district (by
sector when a district is picked), by year, and the 50 schools with the most pupils per teacher (click for the
school's details). Projected years divide the projected students by the base year's teachers (no recruitment
assumed). Schools not in the file (mostly private) or with no teachers recorded for a level have no teacher data: they
are left out of pupils per teacher and counted apart, never shown as 0 teachers. The school table and the school
details show teachers and pupils per teacher too. Teachers needed / short will come once MINEDUC gives its norm.

## PDF report

**Generate report** (filter bar, both pages) prints the current view — level, area, year and intake plan — as an
A4-landscape report: light theme, a heading with the scope and print date, every chart at full length, the map as a
snapshot and the first 25 schools of the table in its current sort. It opens the browser's print dialog; choose
**Save as PDF**. How it works: `src/print.ts` (the `.print-*` classes in `src/index.css` fix the report layout).

## Numbers

All figures come from `backend/app/domain/analysis.py` and `projection.py`, run by the API. The browser only displays
and filters them.
Capacity is 46 students per classroom for every level (`LEVELS` in `analysis.py`).

To update the data, replace the files in `data-sources/` (same columns), run the import job
(`python -m etl.load_version2` in `backend/`) and restart the API. Once real 2030 catchment figures arrive, remove
2030 from `ESTIMATED` in `backend/app/domain/projection.py`.
