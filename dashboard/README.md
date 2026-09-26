# Classroom Sufficiency Dashboard 2026

React + Vite + TypeScript + Tailwind, with an ArcGIS (`@arcgis/core`) map — same stack as BTS `ecofleet-web`.
No backend: the data is three static JSON files in `public/data/`, exported from the Python analysis.

## Run

```powershell
npm install
npm run data      # re-export public/data from the source roster (python scripts/export_dashboard_data.py)
npm run dev       # http://localhost:5173
```

## Deploy

```powershell
npm run build     # output in dist/
```

Copy `dist/` to any static web server (IIS, nginx, an internal share). It uses relative paths, so it works from a sub-folder.
Viewers need internet access to `js.arcgis.com` and `services.arcgisonline.com` for the map; everything else is local.

## Map

- Basemap switch (top-right of the map): **Map** = Esri Light/Dark Gray Canvas, **Satellite** = Esri World Imagery
  with the World Boundaries and Places labels. Neither needs an API key; falls back satellite -> canvas -> OpenStreetMap.
  The viewer's choice is remembered in their browser.
- Optional: set `VITE_ARCGIS_TOKEN` in `.env` to use an Esri API key.
- Schools are drawn from the JSON as a `GeoJSONLayer` built in the browser (the BTS `featureLayers.ts` pattern).
  Schools with missing or out-of-Rwanda coordinates are left off the map but stay in the table.
- **Satellite imagery is the default**; everything outside Rwanda is shaded and the view cannot pan away from Rwanda.
- **Clusters / Schools** switch: clusters group nearby schools (colour = average gap, label = number of schools; hover for
  students, schools in deficit and classrooms short; click to zoom in). From about 1:150,000 every school shows alone,
  sized by students; from about 1:40,000 (zoom 14) a close-up layer draws every school the same large size in its gap
  colour, with names from zoom 15 (GIS team's advice). Esri place names appear from about zoom 13.
- **District and sector boundaries** (switchable; sector lines from about zoom 9, names when zoomed in). The district /
  sector picked in the page filters is outlined in amber.
- **Legend panel on the map** (bottom left, collapsible) is also the map's filter: click Deficit / Exact fit / Surplus
  or a class (10+ short … 10+ spare) to hide or show those schools; it holds the Clusters / Schools switch and the
  District / Sector boundary checkboxes. **Find a school** (top left) searches the schools in view.
- District names show from about zoom 9 (at national zoom the clusters and district outlines carry the view).
- Boundaries: `public/data/districts.geojson`, `sectors.geojson`, `rwanda.geojson`, built by
  `python scripts/build_boundaries.py` from geoBoundaries (Open Data Rwanda 2012, CC BY 4.0), names matched to the roster.

## Page

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

  The whole page recalculates in the browser (`src/projection.ts`, same algorithm as `scripts/projection.py`). A viewer's
  plan is saved in their own browser only — share a plan by sending the CSV.

  Excel copy of a plan: `python scripts/build_projection_workbook.py --intake intake_plan.csv`.

## PDF report

**Generate report** (filter bar, both pages) prints the current view — level, area, year and intake plan — as an
A4-landscape report: light theme, a heading with the scope and print date, every chart at full length, the map as a
snapshot and the first 25 schools of the table in its current sort. It opens the browser's print dialog; choose
**Save as PDF**. How it works: `src/print.ts` (the `.print-*` classes in `src/index.css` fix the report layout).

## Numbers

All figures come from `scripts/analysis.py` and `scripts/projection.py`, the same modules that build the Excel
outputs (`School_Classroom_Analysis_2026.xlsx`, `Classroom_Projection_2026_2030_*.xlsx` via
`python scripts/build_projection_workbook.py`), so the dashboard and workbooks always agree. If you change the
projection rules, change both `scripts/projection.py` and `src/projection.ts` — they were checked to give identical
results for every school, grade and year.
Capacity is 45 students per classroom for every level.

To update the projection with new catchment figures, replace `Chachement area.xlsx` (same columns: `school_code`,
`N1`, `Pop2027` … `Pop2030`), then run `npm run data` and `python scripts/build_projection_workbook.py`. Once real
2030 figures arrive, remove 2030 from `ESTIMATED` in `scripts/projection.py`.
