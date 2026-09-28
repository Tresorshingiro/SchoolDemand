/**
 * The classroom projection 2026–2030. It is calculated on the server (backend/app/domain/projection.py); this module
 * loads its configuration, asks for a run for an intake plan, turns the compact answer into per-year datasets and
 * holds the helpers the page builds its tables and charts with.
 */
import { getJson, sendJson } from './api';
import { totals, type ComboRow, type Dataset, type GradeRow, type Meta, type SchoolLevel, type Totals } from './data';

export interface ProjectedLevel {
  level: number; // index into meta.levels
  grades: string[]; // projected grades (TVET without the L1-L2 short courses)
  capacity: number;
  fullDay: boolean; // no double shift: every class group needs a room, combinations never share
}

/** GET /api/projection/config */
export interface ProjectionBase {
  baseYear: number;
  years: number[]; // baseYear first
  levels: ProjectedLevel[];
  grades: string[]; // every projected grade
  gradeIndex: number[]; // grades[k] -> index into meta.grades
  intakes: Record<string, number>; // entry grade -> age of the children who enter it (N1: 3)
  feeds: [string, string[]][]; // leavers of a grade -> entry grades next year, per district, e.g. ['P6', ['S1']]
  schoolFeeds: [string, string][]; // leavers -> entry grade next year in the same school, else pooled by sector: ['N3', 'P1']
  population: Record<string, Record<string, number[]>>; // entry grade -> district -> default plan (catchment totals), years[1..]
  estimated: Record<string, number[]>; // entry grade -> years not measured (catchment 2030 repeats 2029)
  /** Children aged 3 in each pre-primary school's catchment area: rows [school, value per year of `years`]. */
  catchment: { years: number[]; rows: number[][] };
  defaultLabel: string; // name of the default plan
  combos: string[][]; // per level: its combinations, most students first (empty = no combinations)
}

/** New students per entry grade (N1) and district, for years[1..]. */
export type Intake = Record<string, Record<string, number[]>>;

let baseCache: Promise<ProjectionBase> | null = null;

export function loadProjectionBase(): Promise<ProjectionBase> {
  if (!baseCache) {
    baseCache = getJson<ProjectionBase>('/projection/config');
    baseCache.catch(() => {
      baseCache = null;
    });
  }
  return baseCache;
}

const copyIntake = (v: Intake): Intake =>
  Object.fromEntries(Object.entries(v).map(([g, t]) => [g, Object.fromEntries(Object.entries(t).map(([d, a]) => [d, [...a]]))]));

/** The default plan: new N1 = the children aged 3 in the schools' catchments (no repetition modelled). */
export const defaultIntake = (base: ProjectionBase): Intake => copyIntake(base.population);

/** Does the plan for one entry grade (or every entry grade) equal `b`? */
export function sameIntake(a: Intake, b: Intake, grade?: string): boolean {
  const grades = grade ? [grade] : Object.keys(b);
  return grades.every((g) => {
    const keys = Object.keys(b[g] ?? {});
    return keys.length === Object.keys(a[g] ?? {}).length && keys.every((d) => a[g]?.[d]?.every((v, i) => v === b[g][d][i]));
  });
}

export interface ProjectedYear {
  year: number;
  schools: SchoolLevel[]; // one row per school x level
  grades: GradeRow[];
  combos: ComboRow[]; // school x grade x combination (Upper Secondary, TVET, TTC)
}

/** The server's answer: rows of numbers for every year (see backend/app/domain/dashboard.py encode_projection). */
interface ProjectionRun {
  years: number[];
  schools: number[][]; // [year, school, level, students, class groups, double shift, rooms, required, gap]
  grades: number[][]; // [year, school, grade index, students, class groups, double shift, rooms assigned, required, gap]
  combos: { names: string[]; rows: number[][] }; // [year, school, grade index, combination index, students, class groups]
}

/**
 * Run the projection on the server for a plan (the default plan uses the precomputed run). `info` supplies name,
 * district, sector and coordinates for each school (any 2026 row of the school in the current dataset).
 */
export async function fetchProjection(base: ProjectionBase, intake: Intake, info: Map<number, SchoolLevel>): Promise<ProjectedYear[]> {
  const run = sameIntake(intake, base.population)
    ? await getJson<ProjectionRun>('/projection/default')
    : await sendJson<ProjectionRun>('POST', '/projection/run', { intake });
  const byYear = new Map<number, ProjectedYear>(run.years.map((year) => [year, { year, schools: [], grades: [], combos: [] }]));
  for (const [year, c, l, st, g, ds, a, r, gap] of run.schools) {
    const school = info.get(c);
    if (school) byYear.get(year)!.schools.push({ ...school, l, st, g, ds, a, r, gap });
  }
  for (const [year, ...row] of run.grades) byYear.get(year)!.grades.push(row as GradeRow);
  for (const [year, c, gi, ni, st, g] of run.combos.rows) byYear.get(year)!.combos.push([c, gi, run.combos.names[ni], st, g]);
  return run.years.map((y) => byYear.get(y)!);
}

/* ------------------------------------------------------------------ saved plans (scenarios) */

export interface ScenarioSummary {
  id: number;
  name: string;
  description: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface Scenario extends ScenarioSummary {
  intake: Intake;
}

export const listScenarios = () => getJson<ScenarioSummary[]>('/scenarios');
export const getScenario = (id: number) => getJson<Scenario>(`/scenarios/${id}`);
export const createScenario = (name: string, intake: Intake, description?: string) =>
  sendJson<Scenario>('POST', '/scenarios', { name, intake, description: description || null });
export const updateScenario = (id: number, name: string, intake: Intake, description?: string | null) =>
  sendJson<Scenario>('PUT', `/scenarios/${id}`, { name, intake, description: description ?? null });
export const deleteScenario = (id: number) => sendJson<void>('DELETE', `/scenarios/${id}`);

/** meta with each level's grades replaced by the projected ones (TVET without L1-L2). */
export function projectionMeta(base: ProjectionBase, meta: Meta): Meta {
  const byLevel = new Map(base.levels.map((l) => [l.level, l.grades]));
  return { ...meta, levels: meta.levels.map((l, i) => ({ ...l, grades: byLevel.get(i) ?? l.grades })) };
}

export const yearDataset = (py: ProjectedYear, meta: Meta): Dataset => ({
  schools: py.schools, grades: py.grades, combos: py.combos, meta,
});

export interface YearTotals extends Totals {
  year: number;
}

export function yearTotals(result: ProjectedYear[], level: number, codes: Set<number>): YearTotals[] {
  return result.map((py) => ({ year: py.year, ...totals(py.schools.filter((r) => r.l === level && codes.has(r.c))) }));
}

/** Students per grade (rows) and year (columns) for the given grades and schools. */
export function cohortTable(result: ProjectedYear[], meta: Meta, grades: string[], codes: Set<number>): { grade: string; byYear: number[] }[] {
  const table = grades.map((grade) => ({ grade, byYear: result.map(() => 0) }));
  result.forEach((py, yi) => {
    for (const [c, gi, st] of py.grades) {
      if (!codes.has(c)) continue;
      const k = grades.indexOf(meta.grades[gi]);
      if (k >= 0) table[k].byYear[yi] += st;
    }
  });
  return table;
}

/** Students and class groups per combination (rows) and year (columns) for the given grades and schools. */
export function comboTable(result: ProjectedYear[], meta: Meta, grades: string[], codes: Set<number>): {
  combination: string; students: number[]; groups: number[];
}[] {
  const rows = new Map<string, { combination: string; students: number[]; groups: number[] }>();
  result.forEach((py, yi) => {
    for (const [c, gi, name, st, g] of py.combos) {
      if (!codes.has(c) || !grades.includes(meta.grades[gi])) continue;
      const row = rows.get(name) ?? { combination: name, students: result.map(() => 0), groups: result.map(() => 0) };
      row.students[yi] += st;
      row.groups[yi] += g;
      rows.set(name, row);
    }
  });
  return [...rows.values()];
}

/** One pre-primary school's catchment demand in a year, next to its N1 today and its N1 rooms that year. */
export interface CatchmentDemand {
  code: number;
  demand: number; // children aged 3 in the catchment area that year
  enrolled: number; // N1 students in the base year
  rooms: number; // rooms shared to N1 that year (projection)
}

/**
 * Catchment demand of the schools in `codes` for `year` (the first catchment year when `year` has none, e.g. 2026).
 * Returns the year used and one row per school with a catchment figure.
 */
export function catchmentDemand(base: ProjectionBase, result: ProjectedYear[], meta: Meta, year: number,
  codes: Set<number>): { year: number; rows: CatchmentDemand[] } {
  const { years, rows } = base.catchment;
  const yi = Math.max(0, years.indexOf(year));
  const used = years[yi];
  const n1 = meta.grades.indexOf('N1');
  const n1Of = (py: ProjectedYear | undefined, col: number) => {
    const m = new Map<number, number>();
    for (const g of py?.grades ?? []) if (g[1] === n1) m.set(g[0], g[col]);
    return m;
  };
  const enrolled = n1Of(result.find((py) => py.year === base.baseYear), 2);
  const rooms = n1Of(result.find((py) => py.year === used), 5);
  return {
    year: used,
    rows: rows.filter(([c]) => codes.has(c)).map(([c, ...v]) => ({
      code: c, demand: v[yi], enrolled: enrolled.get(c) ?? 0, rooms: rooms.get(c) ?? 0,
    })),
  };
}

/** Students in one grade by district (rows) and year (columns), e.g. the new S1 each year. */
export function gradeByDistrict(result: ProjectedYear[], meta: Meta, grade: string, info: Map<number, SchoolLevel>): Map<string, number[]> {
  const out = new Map<string, number[]>();
  result.forEach((py, yi) => {
    for (const [c, gi, st] of py.grades) {
      if (meta.grades[gi] !== grade) continue;
      const d = info.get(c)!.d;
      const row = out.get(d) ?? result.map(() => 0);
      row[yi] += st;
      out.set(d, row);
    }
  });
  return out;
}

/* ------------------------------------------------------------------ CSV (pop3_YYYY columns, NISR layout) */

export function intakeToCsv(base: ProjectionBase, intake: Intake): string {
  const years = base.years.slice(1);
  const grades = Object.keys(base.intakes);
  const header = ['district_name', ...grades.flatMap((g) => years.map((y) => `pop${base.intakes[g]}_${y}`))];
  const districts = Object.keys(base.population[grades[0]]);
  const lines = [header.join(',')];
  for (const d of districts) {
    lines.push([d, ...grades.flatMap((g) => intake[g]?.[d] ?? years.map(() => 0))].join(','));
  }
  return lines.join('\n') + '\n';
}

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let quoted = false;
  for (const ch of line) {
    if (ch === '"') quoted = !quoted;
    else if (ch === ',' && !quoted) {
      out.push(cur);
      cur = '';
    } else cur += ch;
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

/**
 * Parse a district x year CSV. Columns pop3_2027 ... set N1 (NISR layout; pop6 columns of older plans are
 * ignored); plain year columns (2027, ...) set `fallbackGrade`. Unknown districts are reported, not added.
 */
export function intakeFromCsv(base: ProjectionBase, text: string, current: Intake, fallbackGrade: string): {
  intake: Intake; unknown: string[]; updated: number; grades: string[];
} {
  const years = base.years.slice(1);
  const rows = text.split(/\r?\n/).filter((l) => l.trim());
  if (!rows.length) throw new Error('The file is empty.');
  const header = splitCsvLine(rows[0]);
  const cols: [string, number[]][] = Object.entries(base.intakes)
    .map(([g, age]) => [g, years.map((y) => header.indexOf(`pop${age}_${y}`))] as [string, number[]])
    .filter(([, c]) => c.some((k) => k >= 0));
  if (!cols.length) {
    const plain = years.map((y) => header.indexOf(String(y)));
    if (plain.some((k) => k >= 0)) cols.push([fallbackGrade, plain]);
  }
  if (!cols.length) {
    throw new Error(`No year columns found. Expected columns like pop3_${years[0]} or ${years[0]}.`);
  }
  const intake = copyIntake(current);
  const byLower = new Map(Object.keys(base.population[cols[0][0]]).map((d) => [d.toLowerCase(), d]));
  const unknown: string[] = [];
  let updated = 0;
  for (const line of rows.slice(1)) {
    const cells = splitCsvLine(line);
    const d = byLower.get((cells[0] ?? '').toLowerCase());
    if (!d) {
      if (cells[0]) unknown.push(cells[0]);
      continue;
    }
    for (const [g, c] of cols) {
      c.forEach((k, yi) => {
        if (k < 0) return;
        const v = Number((cells[k] ?? '').replace(/[,\s]/g, ''));
        if (Number.isFinite(v) && v >= 0) intake[g][d][yi] = Math.round(v);
      });
    }
    updated += 1;
  }
  return { intake, unknown, updated, grades: cols.map(([g]) => g) };
}
