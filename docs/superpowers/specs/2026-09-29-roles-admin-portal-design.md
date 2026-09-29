# Roles and admin portal — design

Date: 2026-09-29 · Sub-project 1 of 2 (sub-project 2: [data sources](2026-09-29-data-sources-design.md))

## Goal

Two kinds of users. **Admins** manage accounts and are the only ones who can change shared things (saved plans
today, the data in sub-project 2). **Viewers** see all the data of the whole country and can try "what-if" intake
plans, but cannot save anything. Admins work in a separate **admin portal** (`/admin`) with its own layout; the
dashboard stays the same for everyone.

## Decisions

| Question | Decision |
|---|---|
| Roles | Two: `admin`, `viewer`. No per-district scoping. |
| Viewer in the intake planner | Can edit the numbers and see the projection; cannot save, rename or delete plans. |
| New user's password | The admin types (or generates) a temporary password and gives it to the person; the person must choose a new one at first sign-in. No email. |
| Where the portal lives | Inside the current React app, `/admin`, admins only. |
| First admin | Created on the command line (`python -m app.users create … --admin` or `role … admin`). |
| Existing accounts | Become viewers when the migration runs. |

## Database — migration `0003_roles`

`users` gets:

| Column | Type | |
|---|---|---|
| `role` | varchar(10), not null, default `viewer` | `admin` or `viewer` (check constraint) |
| `must_change_password` | boolean, not null, default false | set when an admin creates the account or resets the password |
| `created_by_id` | int, null, FK users.id | the admin who created the account |

New table `audit_log`:

| Column | Type | |
|---|---|---|
| `id` | bigint pk | |
| `at` | timestamptz, default now() | |
| `user_id` | int, null, FK users.id (on delete set null) | who did it |
| `action` | varchar(40) | `user.create`, `user.update`, `user.role`, `user.disable`, `user.enable`, `user.password_reset`, `user.password_change`, `scenario.create`, `scenario.update`, `scenario.delete` (sub-project 2 adds `data.*`) |
| `target` | varchar(200) | e.g. the user's email or the plan name |
| `detail` | jsonb, null | e.g. `{"from": "viewer", "to": "admin"}` |

Index on `at desc`. `database/schema.dbml` and the `models.py` docstring are updated to match.

## Permissions (`backend/app/services/auth.py`)

- `current_user` — unchanged meaning: any signed-in, active user. **New:** if the user has `must_change_password`,
  every route except `GET /auth/me`, `POST /auth/password` and `POST /auth/logout` answers
  `403 {"detail": "password_change_required"}`.
- `require_admin` — new dependency: `current_user` + `role == "admin"`, else `403 "Only an administrator can do this."`.
- `audit(session, user, action, target, detail=None)` — helper that adds an `audit_log` row in the caller's transaction.

## API

Changed:

| Route | Before | After |
|---|---|---|
| `POST /api/scenarios`, `PUT /api/scenarios/{id}`, `DELETE /api/scenarios/{id}` | any user | **admin**; each writes an audit entry |
| `GET /api/scenarios`, `GET /api/scenarios/{id}` | any user | any user |
| data, boundaries, `/projection/*` (incl. `POST /projection/run`) | any user | any user (viewers' what-ifs) |
| `GET /api/auth/me` | `id, email, full_name` | + `role`, `must_change_password` |
| `POST /api/admin/reload` | admin token | admin token **or** a signed-in admin |

New:

| Method | Path | Who | Body → result |
|---|---|---|---|
| POST | `/api/auth/password` | any signed-in user | `{current_password, new_password}` → 204; 400 when the current password is wrong or the new one is the same. New ≥ 8 characters. Clears `must_change_password`, ends the user's **other** sessions. |
| GET | `/api/admin/users` | admin | list: id, email, full_name, role, is_active, must_change_password, created_at, last_login_at |
| POST | `/api/admin/users` | admin | `{email, full_name, role, password}` → 201 user. Sets `must_change_password`. 409 if the email exists. |
| PATCH | `/api/admin/users/{id}` | admin | any of `{full_name, role, is_active}` → user. Disabling ends the user's sessions. |
| POST | `/api/admin/users/{id}/password` | admin | `{password}` → 204. Sets `must_change_password`, ends the user's sessions. |
| GET | `/api/admin/audit` | admin | `?limit=50&before=<id>&user_id=&action=` → entries (with the actor's name / email), newest first |

Rules (checked in the same transaction, the admin rows locked with `SELECT … FOR UPDATE`):

- An admin cannot change their own role or disable themselves (`409 "You cannot remove your own admin access."`).
- There is always at least one active admin (`409 "At least one active administrator is needed."`).
- Emails are trimmed and lower-cased (as today); passwords ≥ 8 characters (as today).

## Command line (`python -m app.users`)

- `create EMAIL --name NAME [--admin]` — as today, plus the role. Accounts made here do **not** get
  `must_change_password` (the person typing is the owner).
- `role EMAIL admin|viewer` — new.
- `list` — shows the role too.

## Frontend (`dashboard/src`)

Routing (`main.tsx`):

- `/dashboard` — everyone signed in (as today).
- `/admin/*` — `RequireAdmin` guard; viewers are sent to `/dashboard`. Lazy-loaded like the dashboard.
- `/account/password` — change password. `RequireAuth` sends a user with `must_change_password` here from any other
  page, and the API's `password_change_required` answer triggers the same redirect.

`auth.tsx`: `User` gets `role` and `must_change_password`; helpers `isAdmin(user)`. After a password change the
user object is refreshed from `/auth/me`.

Dashboard header (`App.tsx`): the user name becomes a menu — **Change password**, **Admin portal** (admins),
**Sign out**.

Intake planner (`IntakePlanner.tsx` / `ProjectionPage.tsx`): for viewers the Save / Save as / Rename / Delete
controls are not rendered and a short note reads *"You can try plans; only an administrator can save them."*
Opening saved plans and editing numbers work as today.

Admin portal (`src/admin/`):

- `AdminLayout.tsx` — sidebar (logo · **Users** · **Activity** · separator · **Data** greyed "coming soon" until
  sub-project 2 · bottom: "← Dashboard", user name, sign out, theme toggle). Same tokens, fonts and light / dark
  theme as the dashboard (`index.css`, `theme.tsx`). Below `md` the sidebar becomes a top bar with a menu button.
- `UsersPage.tsx` — table (name + email, role, status: Active / Disabled / Must change password, last sign-in, row
  menu). Search box, role and status filters. **Add user** opens a side panel: email, name, role, temporary password
  with **Generate** (12 random characters from `crypto.getRandomValues`, no look-alike characters) and **Copy**.
  After saving, the password is shown once with *"Give this password to <name>; they will choose their own at
  first sign-in."* Row menu: Edit (name, role), Reset password (same panel / show-once flow), Disable / Enable.
  Actions forbidden by the rules above are disabled with a tooltip giving the reason.
- `ActivityPage.tsx` — audit entries as sentences ("Jane reset Eric's password · 10:42"), filters by user and
  action, "Load more" paging.
- `admin/api.ts` — typed calls to the routes above (using `api.ts`).

`ChangePasswordPage.tsx` (`src/site/`, public-page layout): current password, new password, repeat; when forced,
a line explains why and there is no way out except Sign out.

## Errors

- API messages stay plain sentences; the pages show them inline next to the form or as a banner.
- A disabled user's next request gets 401 → the existing `AUTH_EXPIRED` flow sends them to sign-in.
- A viewer calling a write route directly gets 403 (the UI never offers it).

## Testing

Backend (pytest, alongside the existing tests; `conftest.py` gets an admin test user — the existing `client`
fixture signs in as admin so the current scenario tests keep passing — plus a `viewer` client fixture):

- Viewer: reads data, runs `/projection/run`, lists and opens plans; 403 on POST / PUT / DELETE `/scenarios` and
  every `/admin/*` route.
- Admin users API: create (201, `must_change_password` true; duplicate email 409; short password 422), list, edit
  name / role, disable (the user's sessions end → 401), enable, reset password (sessions end, flag set).
- Guards: self-demotion and self-disable 409; the last active admin cannot be demoted or disabled.
- Forced change: a new user gets `403 password_change_required` on data routes, can call `/auth/me` and
  `/auth/password`, then has normal access.
- `/auth/password`: wrong current password → 400 "The current password is wrong."; same password as before → 400;
  success ends other sessions but keeps the current one.
- Audit: each admin action above writes exactly one entry with the right action and target; `/admin/audit` paging.
- `/admin/reload` works with a signed-in admin, is refused for a viewer.

Frontend: `tsc -b` clean; manual check in the browser as admin and as viewer (menu, hidden save buttons, portal
guard, add user → forced password change → dashboard).

## Rollout

1. `alembic upgrade head` (the API container does it on start) — every account becomes a viewer.
2. `python -m app.users role <your email> admin`.
3. Rebuild the API and web images (`docker compose … up -d --build`) — this also replaces the stale API image that
   currently fails with "Can't locate revision '0002'".

## Out of scope

Data uploads, import history and the MINEDUC connector (sub-project 2 — its pages go in this portal's sidebar and
its actions in this audit log). Per-district access, email invitations, self sign-up, password recovery by email.
