/** The dashboard's data, served by the API (backend/app). */
import { getJson } from './api';

export interface SchoolLevel {
  c: number; // school code
  n: string; // school name
  d: string; // district
  s: string; // sector
  l: number; // level index into meta.levels
  st: number; // total students
  g: number; // total classrooms (class groups)
  ds: number; // classrooms in double shift
  a: number; // classrooms available (physical rooms)
  r: number; // required classrooms
  gap: number; // available - required
  y: number | null; // latitude (null when missing / outside Rwanda)
  x: number | null; // longitude
}

/** [school, gradeIndex, students, classGroups, doubleShift, available, required, gap] */
export type GradeRow = [number, number, number, number, number, number, number, number];

export interface Level {
  key: string;
  label: string;
  grades: string[];
  capacity: number;
  /** Full-day level (secondary, TVET, TTC): no double shift — `ds` counts class groups without a room. */
  fullDay: boolean;
}

export interface Meta {
  built: string;
  source: string;
  levels: Level[];
  grades: string[];
  roster: { rows: number; schools: number; students: number };
  issues: Record<string, number>;
  schoolIssues: Record<string, [string, number][]>;
  unmapped: number;
}

/** [school, gradeIndex, combination, students, classGroups] — Upper Secondary, TVET and TTC only. */
export type ComboRow = [number, number, string, number, number];

export interface Dataset {
  schools: SchoolLevel[];
  grades: GradeRow[];
  combos: ComboRow[];
  meta: Meta;
}

/** The 2026 dataset from the API (backend/app/domain/dashboard.py current). */
export async function loadDataset(): Promise<Dataset> {
  const [schools, grades, meta, combos] = await Promise.all([
    getJson<SchoolLevel[]>('/school-levels'),
    getJson<GradeRow[]>('/grades'),
    getJson<Meta>('/meta'),
    getJson<{ names: string[]; rows: [number, number, number, number, number][] }>('/combos'),
  ]);
  return {
    schools,
    grades,
    meta,
    combos: combos.rows.map(([c, gi, ni, st, g]): ComboRow => [c, gi, combos.names[ni], st, g]),
  };
}

/* ------------------------------------------------------------------ filters and totals */

export interface Filters {
  level: number;
  district: string;
  sector: string;
}

export function applyFilters(rows: SchoolLevel[], f: Filters): SchoolLevel[] {
  return rows.filter(
    (r) => r.l === f.level && (!f.district || r.d === f.district) && (!f.sector || r.s === f.sector),
  );
}

export interface Totals {
  schools: number;
  students: number;
  classGroups: number;
  doubleShift: number;
  available: number;
  required: number;
  netGap: number;
  short: number; // sum of deficits of schools in deficit
  deficitSchools: number;
  exactSchools: number;
  surplusSchools: number;
}

export function totals(rows: SchoolLevel[]): Totals {
  const t: Totals = {
    schools: rows.length, students: 0, classGroups: 0, doubleShift: 0, available: 0, required: 0,
    netGap: 0, short: 0, deficitSchools: 0, exactSchools: 0, surplusSchools: 0,
  };
  for (const r of rows) {
    t.students += r.st;
    t.classGroups += r.g;
    t.doubleShift += r.ds;
    t.available += r.a;
    t.required += r.r;
    t.netGap += r.gap;
    if (r.gap < 0) {
      t.short -= r.gap;
      t.deficitSchools += 1;
    } else if (r.gap === 0) t.exactSchools += 1;
    else t.surplusSchools += 1;
  }
  return t;
}

/** Group rows by a key and return totals per group. */
export function totalsBy(rows: SchoolLevel[], key: (r: SchoolLevel) => string): Map<string, Totals> {
  const groups = new Map<string, SchoolLevel[]>();
  for (const r of rows) {
    const k = key(r);
    const list = groups.get(k);
    if (list) list.push(r);
    else groups.set(k, [r]);
  }
  return new Map([...groups].map(([k, list]) => [k, totals(list)]));
}

export interface GradeTotals {
  grade: string;
  students: number;
  classGroups: number;
  doubleShift: number;
  available: number;
  required: number;
  short: number;
}

/** Per-grade totals for the grades of one level, restricted to the given schools. */
export function gradeTotals(grades: GradeRow[], meta: Meta, level: number, schoolCodes: Set<number>): GradeTotals[] {
  const levelGrades = meta.levels[level].grades;
  const byGrade = new Map<string, GradeTotals>(
    levelGrades.map((g) => [g, { grade: g, students: 0, classGroups: 0, doubleShift: 0, available: 0, required: 0, short: 0 }]),
  );
  for (const [school, gi, st, cg, ds, av, rq, gap] of grades) {
    const t = byGrade.get(meta.grades[gi]);
    if (!t || !schoolCodes.has(school)) continue;
    t.students += st;
    t.classGroups += cg;
    t.doubleShift += ds;
    t.available += av;
    t.required += rq;
    if (gap < 0) t.short -= gap;
  }
  return [...byGrade.values()];
}

/** Rwanda's districts by province. */
const PROVINCES: Record<string, string[]> = {
  'City of Kigali': ['Gasabo', 'Kicukiro', 'Nyarugenge'],
  'Eastern Province': ['Bugesera', 'Gatsibo', 'Kayonza', 'Kirehe', 'Ngoma', 'Nyagatare', 'Rwamagana'],
  'Northern Province': ['Burera', 'Gakenke', 'Gicumbi', 'Musanze', 'Rulindo'],
  'Southern Province': ['Gisagara', 'Huye', 'Kamonyi', 'Muhanga', 'Nyamagabe', 'Nyanza', 'Nyaruguru', 'Ruhango'],
  'Western Province': ['Karongi', 'Ngororero', 'Nyabihu', 'Nyamasheke', 'Rubavu', 'Rusizi', 'Rutsiro'],
};
const PROVINCE_OF = new Map(Object.entries(PROVINCES).flatMap(([p, ds]) => ds.map((d) => [d, p] as const)));
export const provinceOf = (district: string) => PROVINCE_OF.get(district) ?? 'Unknown';

export interface AreaGrades {
  area: string;
  students: number[]; // per grade of the level
  classGroups: number[];
}

/** Students and class groups per area (district, sector...) and grade of one level, for the given school rows. */
export function gradesByArea(grades: GradeRow[], meta: Meta, level: number, rows: SchoolLevel[],
  key: (r: SchoolLevel) => string): AreaGrades[] {
  const levelGrades = meta.levels[level].grades;
  const areaOf = new Map(rows.map((r) => [r.c, key(r)]));
  const out = new Map<string, AreaGrades>();
  for (const [school, gi, st, cg] of grades) {
    const area = areaOf.get(school);
    const k = levelGrades.indexOf(meta.grades[gi]);
    if (area === undefined || k < 0) continue;
    let a = out.get(area);
    if (!a) {
      a = { area, students: levelGrades.map(() => 0), classGroups: levelGrades.map(() => 0) };
      out.set(area, a);
    }
    a.students[k] += st;
    a.classGroups[k] += cg;
  }
  return [...out.values()];
}

export type Status = 'Deficit' | 'Exact fit' | 'Surplus';
export const statusOf = (gap: number): Status => (gap < 0 ? 'Deficit' : gap === 0 ? 'Exact fit' : 'Surplus');

const nf = new Intl.NumberFormat('en-US');
export const fmt = (n: number) => nf.format(n);
export const fmtGap = (n: number) => (n > 0 ? `+${nf.format(n)}` : nf.format(n));
export const pct = (part: number, whole: number) => (whole ? `${((part / whole) * 100).toFixed(1)}%` : '—');
