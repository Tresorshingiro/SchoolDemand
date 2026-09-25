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

## Pages

- **Current 2026** (`#/`) — every level, from the 2026 roster.
- **Projection 2027–2030** (`#/projection`) — a planning tool for every level. Each grade moves up one step a year and
  rooms stay at the 2026 count for each level. New students:
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

**Download PDF** (filter bar, both pages) prints the current view — level, area, year and intake plan — as an
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
