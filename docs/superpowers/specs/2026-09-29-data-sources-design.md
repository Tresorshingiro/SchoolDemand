# Data sources in the admin portal — design

Date: 2026-09-29 · Sub-project 2 of 2 — builds on [roles and admin portal](2026-09-29-roles-admin-portal-design.md)
(admin role, `/admin` layout, audit log).

## Goal

The admin replaces the data the site uses from the admin portal, without the command line and without risking the
live site: **upload → automatic check → report → Publish** (or Discard), with a history of every import and a way
back to an earlier one. New school years become "actual" and the projection moves forward with them.

## Decisions

| Question | Decision |
|---|---|
| Sources | Three: **school data** (MINEDUC, one school year), **catchment** (GIS, children aged 3 per pre-primary school per year), **NISR population** (children aged 3 per district per year). |
| How they arrive | Excel / CSV upload now. The MINEDUC API is a connector slot added when documentation and access exist (none today). |
| New school year | Becomes actual; earlier years stay actual history. The **base year** = the newest published school year. |
| Projection window | Rolling: the 4 years after the base year (2027 actual → 2028–2031). |
| NISR role | Sets each district's total of new N1 (the default plan); the catchment file only shares that total between the district's schools. Districts / years without NISR figures use the catchment totals. |
| Import flow | Approach 1: stored upload, background check, report, Publish in one transaction, history, republish = rollback. |
| Saved plans when the base year moves | Archived (readable, not runnable); the admin can copy one into the current years. |

## 1. Storage and import flow

### Uploaded files

Stored under `UPLOAD_DIR` (new setting; Docker: a new writable volume `uploads` mounted at `/uploads`; Windows: a
folder set in `backend/.env`), named `<sha256>.<ext>`. Kept for good — they are the history and the rollback source.

### `import_runs` (existing table, migration `0004_imports`)

New columns:

| Column | |
|---|---|
| `kind` | `school_data`, `catchment`, `nisr_population` |
| `academic_year` | smallint — school data only: the year chosen on upload |
| `file_name`, `file_sha256`, `file_size` | the upload |
| `uploaded_by_id`, `published_by_id` | FK users.id |
| `published_at` | |
| `progress` | 0–100 during the check |
| `report` | jsonb — the check results (section 2) |
| `is_live` | boolean — exactly one live import per kind (per kind + year for school data), enforced by a partial unique index |

`status` values: `uploaded → checking → ready | failed`; `ready → published | discarded`; `published → superseded`
when another import of the same kind (and year) is published. A `superseded` import can be published again.

Existing rows from the command-line loads become `kind = school_data, academic_year = 2026, status = published,
is_live = true` (their catchment part is represented by a `catchment` row created by the migration).

### Live tables

- `classrooms` gets `academic_year_id` (rooms belong to a school year; the unique key becomes
  `(academic_year_id, school_id, mineduc_classroom_id)`). The migration fills 2026.
- Publishing **school data for year Y** deletes and re-inserts only year Y's `classrooms`, `class_groups` and
  `data_quality_issues`. Other years are untouched.
- `schools` is upserted by `mineduc_code`; name, sector and coordinates come from the **newest** year that contains
  the school. `is_active` = present in the newest year. Schools are never deleted (history refers to them).
- Publishing a **catchment** file replaces all of `catchment_population`.
- New table `district_population (id, district_id, year, age, population, import_run_id)`, unique
  `(district_id, year, age)`. Publishing a **NISR** file replaces it.
- Districts / sectors / provinces / boundaries are not imported from these files (they come from the boundaries and
  stay as loaded today). A school whose district / sector name is unknown gets `sector_id = null` ("Unknown").

Publish = one database transaction (delete + insert + flags + audit entry), then the API reloads its in-memory
snapshot. If the transaction fails, nothing changes and the import is marked `failed` with the reason. If the
reload fails, the data is published but not yet served: the portal says so and offers **Reload data**.

### Background work

One worker thread in the API process runs checks and publishes, one at a time; later requests wait
(`status = uploaded`, report "waiting for the current check"). The API runs one uvicorn worker (as today), so this is
safe. At startup, imports left in `checking` are marked `failed` ("interrupted — run the check again"); the portal
offers **Check again**.

The check parses the file, validates it, and saves the parsed rows next to the upload (`<sha256>.parsed.pkl`) so
Publish does not parse again. Publishing a superseded import re-parses if the pickle is missing.

### Command line

`etl/load_version2.py` becomes a thin wrapper: for each file in `SCHOOL_DATA_DIR` (Version 2.xlsx as 2026,
Chachement area.xlsx, and a NISR file if present) it stores the upload, runs the same check and publishes it — so a
new server can still be set up without the website. Boundaries keep loading as today.

## 2. File formats and checks

All kinds: `.xlsx` (first sheet) or `.csv`; at most 50 MB; column names matched ignoring case, spaces and
underscores; extra columns ignored. The portal offers a **template** download per kind (headers + one example row).
Problems are **errors** (block Publish) or **warnings** (listed; Publish allowed). The report shows up to 20 affected
rows per problem and offers the full list as CSV.

### School data (MINEDUC) — one school year

Required: `school_code, school_name, district, sector, latitude, longitude, grade, class_group, classroom_id,
classroom_name, Number of students` (alias `students`). Optional: `combination`, `test_code`.

Preparation:

- Text repaired as today (`_fix_mojibake`), grades upper-cased.
- **Room ID** (`test_code`): taken from the file when present; otherwise computed from `classroom_id` within a
  school — a room with 1 or 2 class groups keeps its ID; a room with 3 or more groups (a data-entry error: a room
  holds at most a morning and an afternoon session) becomes one room per group (`<classroom_id>#1`, `#2`, …). A row
  without `classroom_id` gets a room of its own (`row-<n>`).
- **Schools that cannot be placed** (coordinates missing or outside Rwanda's box) are **excluded**, as they were
  when Version 2.xlsx was made; they are listed in the report as a warning with their students.

Errors: required column missing; no rows; grade not one of N1–N3, P1–P6, S1–S6, L1–L5, Y1–Y3; students empty,
negative or not a whole number; school code empty or not numeric; year outside 2000–2100.

Warnings: excluded schools (above); district / sector not in the boundaries; one school with several names, districts
or coordinates (the first is used); every existing data-quality check (`analysis.data_quality`: large / tiny groups,
grade mismatch, repeated names, rooms shared across grades / levels …); rows without `classroom_id`.

Comparison (report "Changes" section): if year Y is already live — "Replaces the live Y data" and the differences
against it; otherwise against the newest live year: schools added / removed, and per level students, class groups,
rooms, required, gap with the % change.

### Catchment (GIS)

Required: `school_code` and one or more `PopYYYY` columns (e.g. `Pop2028`). Other columns (the current file has 48)
are ignored.

Errors: no `Pop` column; a value not a number or negative; school code not numeric.

Warnings: codes that are not a pre-primary school in the newest school data (ignored); pre-primary schools without
a figure (they keep their last known value, their N1 enrolment when none — as today); duplicate codes (the first is
kept); projection years not covered ("2031 repeats 2030").

### NISR population (district totals, age 3)

Required: `district_name` (alias `district`) and one or more `pop3_YYYY` columns — the layout the intake planner
already downloads / reads.

Errors: a district name not among the 30 districts (a typo); a value not a number or negative; the same district twice.

Warnings: districts missing (they use the catchment total); projection years not covered (the last year repeats);
a district whose NISR total differs from its catchment total by more than 20% in a year.

## 3. Several actual years — engine, API, dashboard

### Engine (`backend/app/domain`)

- `BASE_YEAR` / `YEARS` stop being fixed: a `Horizon(base_year, years)` value is derived from the data
  (`years = base..base+4`) and passed to `projection.project`, `default_intake`, `fill_catchment`,
  `dashboard.projection_config` / `encode_projection`. The module constants stay as defaults (2026–2030) so the
  Excel scripts in `scripts/` keep working unchanged from the files.
- Rules that read "the 2026 …" (district share of new students, S4 / L3 / Y1 mix, average group size, combination
  mix, P1 pooling weights) read the base year's roster. No rule changes.
- Catchment and NISR years beyond the data repeat the last given year and are listed in `estimated` (as 2030 is today).
- Default N1 plan per district and year = the NISR figure when there is one, else the district's catchment total.
  Sharing to schools by catchment is unchanged: `ROUND(plan × school catchment / district catchment)`.

### API

- `store.load` reads every published school year. For each actual year it prepares `meta`-independent payloads
  (`school-levels`, `grades`, `combos`) as today; the projection starts from the base year.
- `GET /api/meta` adds `actualYears`, `baseYear`, `projectionYears` and `sources` (per kind: file, year, published by,
  published at).
- `GET /api/school-levels | grades | combos` accept `?year=` (an actual year; default the base year; 404 otherwise).
- `/api/projection/*` keep their shapes; `years` come from the horizon. `complete_intake` checks the number of years
  against the horizon.
- New admin routes (all `require_admin`, all audited):

| Method | Path | |
|---|---|---|
| GET | `/api/admin/data/sources` | per kind: the live import(s), counts, whether the API connector is configured |
| POST | `/api/admin/data/uploads` | multipart: `kind`, `file`, `academic_year` (school data) → 202 import (status `uploaded`) |
| GET | `/api/admin/data/imports` | history, newest first, `?kind=` |
| GET | `/api/admin/data/imports/{id}` | one import with its report and progress (polled by the portal while checking) |
| GET | `/api/admin/data/imports/{id}/file` | the original upload |
| GET | `/api/admin/data/imports/{id}/issues.csv` | every problem row of the report |
| POST | `/api/admin/data/imports/{id}/publish` | `ready` or `superseded` → publish (runs in the worker) |
| POST | `/api/admin/data/imports/{id}/discard` | `ready` / `failed` → `discarded` |
| POST | `/api/admin/data/imports/{id}/recheck` | `failed` → run the check again |
| GET | `/api/admin/data/templates/{kind}` | the template file |

Audit actions: `data.upload`, `data.publish`, `data.discard`, `data.republish`.

### Saved plans

`projection_scenarios.base_year_id` (exists) is set from the horizon when a plan is saved. `GET /api/scenarios` adds
`archived` (= base year differs from the current one). Opening an archived plan returns its values; running it is
refused (409 "This plan was made for 2027–2030; copy it to the current years first."). New admin route
`POST /api/scenarios/{id}/copy` `{name}` → a new plan for the current years: values for years in both are kept, new
years take the default plan.

### Dashboard

- Year picker: every actual year (marked "actual"), then the projected years. An actual year shows that year's data
  (fetched with `?year=`, cached); a projected year shows the projection, as today.
- Trend charts: actual years first (marked `*` as today), then projected. Titles and texts use the horizon
  ("Classroom Sufficiency 2026–2031"); hard-coded "2026" texts in `App.tsx`, `ProjectionPage.tsx`, `SchoolPanel.tsx`,
  `IntakePlanner.tsx`, `projection.ts` read the base year instead. Default year = the last projected year.
- Intake planner: archived plans are listed under "Archived", open read-only; admins see **Copy to current years**.

## 4. Admin portal — Data pages

Sidebar: `Users · Activity · Data` (Data enabled by this sub-project), with two pages.

**Data → Sources** — one card per kind: the live import(s) (school data: one line per actual year) with file, who
published it and when; **Upload** and **Template** buttons; for school data, "API connector: not set up".

Upload flow: choose the file (drop zone or button); school data also asks for the school year (suggested: newest
live year + 1); the import appears with a progress bar; when the check ends its **report** opens:

- header: kind, year, file, status;
- **Errors** (red) and **Warnings** (amber), each with count, first rows, "download all (CSV)";
- **Changes** — the comparison table;
- **Publish** (disabled while there are errors) and **Discard**.

Publish asks for confirmation with the consequences, e.g. *"2027 becomes the base year. The projection moves to
2028–2031 and 3 saved plans will be archived."* or *"Replaces the live 2026 data."*

**Data → History** — every import, newest first: kind, year, file, status, uploaded by / when, published by / when.
Row actions: view report, download file, **Publish again** (for superseded imports; same confirmation), Check again
(failed), Discard (ready / failed).

## 5. Errors

- Upload refused before storing: not `.xlsx` / `.csv`, over 50 MB, empty file.
- Same file (same SHA-256) already live for the same kind (and year): refused — "This file is already live
  (published 26 Sep)." An identical file that is not live is accepted (e.g. to republish).
- Unreadable workbook: import `failed` with the reader's message.
- Publish of a stale report (another import of the same kind and year was published after this one was checked):
  the comparison is recomputed first and the admin confirms again.
- Every failure leaves the live data untouched.

## 6. Testing

Small sample files in `backend/tests/fixtures/` (a few schools, all levels; a catchment and a NISR file), not the
real 10 MB workbook. Tests run against the development database; publishing tests restore the original live imports
afterwards (republish) so the rest of the suite sees the normal 2026 data.

- Each kind: a good file → `ready`, no errors; each error case → listed, Publish refused (409); each warning case
  listed.
- Room ID: on `Version 2.xlsx` with `test_code` removed, the computed rooms group the rows exactly as the file's
  `test_code` does (same partition of rows into rooms, per school). Skipped when the file is absent. If it fails, the
  rule is adjusted until it matches.
- School year 2027 sample published: `baseYear` 2027, projection 2028–2031, `?year=2026` still served, 2026 plans
  archived, running an archived plan 409, copy works.
- Rollback: republishing the previous school data restores `baseYear`, payloads and plan states.
- NISR published: default plan totals equal the NISR figures; each district's new N1 across its schools adds up to
  the plan (± rounding as today); districts without NISR figures use catchment totals.
- Interrupted check marked failed at startup; recheck works.
- Permissions: a viewer gets 403 on every `/admin/data/*` route.
- The existing tests (including the database-vs-files projection comparison on 2026) keep passing.

Frontend: `tsc -b` clean; manual run-through in the browser: upload each template (edited), read the report, publish,
see the year picker change, republish the old data.

## Out of scope

The MINEDUC API connector itself (built when its documentation and access exist; it will create an import of kind
`school_data` and go through the same check and publish). NISR village-level data and computing catchments in the
system. Comparing a past projection with the actual data of that year. Changing the boundaries from the portal.
