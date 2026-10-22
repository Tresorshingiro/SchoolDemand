/**
 * Planned new schools ("what if we build a school here?"): what the dashboard sends with a projection run, what the
 * server answers about them, saved plans of new schools, and the before → after figures. The calculation itself is
 * on the server (backend/app/domain/new_schools.py).
 */
import { getJson, sendJson } from './api';
import { totals, type SchoolLevel } from './data';
import type { Intake, ProjectedYear, ProjectionBase } from './projection';

/** A planned school as sent to the API. `levels`: level key (NUR, PRI, LSE, USE, TVE, TTC) -> classrooms. */
export interface PlannedSchoolInput {
  name: string;
  latitude: number;
  longitude: number;
  levels: Record<string, number>;
  opening_year: number;
  walking_km: number;
}

/** A planned school as the server describes it in a run (code -1, -2 ... in the rows). */
export interface PlannedOut {
  c: number;
  n: string;
  d: string;
  s: string;
  y: number;
  x: number;
  levels: number[]; // indexes into meta.levels
  classrooms: number[]; // per entry of `levels`
  opening: number;
  km: number;
  ring: Record<string, number[]>; // level index -> codes of the existing schools within walking distance
}

/** Walking distance by level key: 2 km for Pre-Primary and Primary, 3 km for the others. */
export const DEFAULT_KM: Record<string, number> = { NUR: 2, PRI: 2, LSE: 3, USE: 3, TVE: 3, TTC: 3 };

/** A standard school: 2 classrooms per projected grade of the level (index into meta.levels). */
export function defaultClassrooms(base: ProjectionBase, levelIndex: number): number {
  return 2 * (base.levels.find((l) => l.level === levelIndex)?.grades.length ?? 3);
}

/** The planned school as a row of the dashboard's school lookup (name, place), so its rows show in every year. */
export const plannedInfo = (p: PlannedOut): SchoolLevel => ({
  c: p.c, n: p.n, d: p.d, s: p.s, l: p.levels[0], st: 0, g: 0, ds: 0, a: 0, r: 0, gap: 0, y: p.y, x: p.x,
});

/* ------------------------------------------------------------------ saved plans of new schools */

export interface SchoolPlanSummary {
  id: number;
  name: string;
  description: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  base_year: number;
  archived: boolean;
  schools: number;
  summary: { levels: Record<string, Record<string, Record<string, { short: [number, number]; deficit_schools: [number, number] }>>> } | null;
}

export interface SchoolPlan extends SchoolPlanSummary {
  plan_schools: PlannedSchoolInput[];
}

export const listSchoolPlans = () => getJson<SchoolPlanSummary[]>('/school-plans');
export const getSchoolPlan = (id: number) => getJson<SchoolPlan>(`/school-plans/${id}`);
export const createSchoolPlan = (name: string, schools: PlannedSchoolInput[], intake: Intake) =>
  sendJson<SchoolPlan>('POST', '/school-plans', { name, schools, intake });
export const updateSchoolPlan = (id: number, name: string, schools: PlannedSchoolInput[], intake: Intake,
  description?: string | null) =>
  sendJson<SchoolPlan>('PUT', `/school-plans/${id}`, { name, schools, intake, description: description ?? null });
export const deleteSchoolPlan = (id: number) => sendJson<void>('DELETE', `/school-plans/${id}`);
export const copySchoolPlan = (id: number, name: string) => sendJson<SchoolPlan>('POST', `/school-plans/${id}/copy`, { name });

/* ------------------------------------------------------------------ what changes */

export interface Impact {
  short: [number, number]; // classrooms short, before / after
  deficitSchools: [number, number];
  doubleShift: [number, number]; // class groups on double shift (without a room on full-day levels)
  classGroups: [number, number];
}

/** Before → after totals of one level for the schools in `codes` (planned schools have no row before). */
export function impact(before: ProjectedYear, after: ProjectedYear, level: number, codes: Set<number>): Impact {
  const pick = (py: ProjectedYear) => totals(py.schools.filter((r) => r.l === level && codes.has(r.c)));
  const b = pick(before);
  const a = pick(after);
  return {
    short: [b.short, a.short],
    deficitSchools: [b.deficitSchools, a.deficitSchools],
    doubleShift: [b.doubleShift, a.doubleShift],
    classGroups: [b.classGroups, a.classGroups],
  };
}

/* ------------------------------------------------------------------ remembered in this browser */

export interface StoredSchools {
  planId: number | null;
  on: boolean;
  schools: PlannedSchoolInput[];
}

const SCHOOLS_KEY = 'classroom-dashboard-school-plan-v1';

export function storedSchools(baseYear: number): StoredSchools | null {
  try {
    const raw = localStorage.getItem(`${SCHOOLS_KEY}-${baseYear}`);
    if (!raw) return null;
    const v = JSON.parse(raw) as StoredSchools;
    return Array.isArray(v.schools) ? v : null;
  } catch {
    return null; // unreadable — start without planned schools
  }
}

export function saveSchools(baseYear: number, v: StoredSchools) {
  try {
    localStorage.setItem(`${SCHOOLS_KEY}-${baseYear}`, JSON.stringify(v));
  } catch {
    /* storage unavailable — the planned schools last for this visit only */
  }
}
