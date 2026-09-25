/**
 * Classroom projection for every level, run in the browser so planners can change the N1 / P1 intake.
 * Same algorithm as scripts/projection.py (see its docstring) — keep the two in step.
 */
import { totals, type ComboRow, type Dataset, type GradeRow, type Meta, type SchoolLevel, type Totals } from './data';

export interface ProjectedLevel {
  level: number; // index into meta.levels
  grades: string[]; // projected grades (TVET without the L1-L2 short courses)
  capacity: number;
  fullDay: boolean; // no double shift: every class group needs a room, combinations never share
}

export interface ProjectionBase {
  baseYear: number;
  years: number[]; // baseYear first
  levels: ProjectedLevel[];
  grades: string[]; // every projected grade, the column order of `schools`
  gradeIndex: number[]; // grades[k] -> index into meta.grades
  intakes: Record<string, number>; // entry grade -> age of the children who enter it (N1: 3)
  feeds: [string, string[]][]; // leavers of a grade -> entry grades next year, per district, e.g. ['P6', ['S1']]
  schoolFeeds: [string, string][]; // leavers -> entry grade next year in the same school, else pooled by sector: ['N3', 'P1']
  population: Record<string, Record<string, number[]>>; // entry grade -> district -> default plan (catchment totals), years[1..]
  estimated: Record<string, number[]>; // entry grade -> years not measured (catchment 2030 repeats 2029)
  defaultLabel: string; // name of the default plan
  catchment: number[][]; // [code, children aged 3 in the school's catchment per year of years[1..]]
  schools: number[][]; // [code, rooms per level..., students per grade..., class groups per grade...]
  combos: string[][]; // per level: its combinations, most students first (empty = no combinations)
  schoolCombos: number[][]; // 2026 [code, grade index into grades, combination index within its level, students, class groups]
}

/** New students per entry grade (N1, P1) and district, for years[1..]. */
export type Intake = Record<string, Record<string, number[]>>;


let baseCache: Promise<ProjectionBase> | null = null;

export function loadProjectionBase(): Promise<ProjectionBase> {
  if (!baseCache) {
    baseCache = fetch(`${import.meta.env.BASE_URL}data/projection_base.json`).then((res) => {
      if (!res.ok) throw new Error(`Could not load projection_base.json (${res.status})`);
      return res.json() as Promise<ProjectionBase>;
    });
    baseCache.catch(() => {
      baseCache = null;
    });
  }
  return baseCache;
}

const roundHalfUp = (x: number) => Math.floor(x + 0.5);

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

/** Split `total` whole units in proportion to `weights`, largest remainders first (ties to the lower grade). */
function largestRemainder(total: number, weights: number[]): number[] {
  const wsum = weights.reduce((s, w) => s + w, 0);
  if (wsum <= 0) return weights.map(() => 0);
  const share = weights.map((w) => (total * w) / wsum);
  const alloc = share.map(Math.floor);
  let left = total - alloc.reduce((s, v) => s + v, 0);
  const order = share.map((v, i) => [v - alloc[i], i] as const).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (const [, i] of order) {
    if (left <= 0) break;
    alloc[i] += 1;
    left -= 1;
  }
  return alloc;
}

function shareRooms(rooms: number, groups: number[], required: number[]): number[] {
  const gTotal = groups.reduce((s, v) => s + v, 0);
  if (gTotal > rooms) return largestRemainder(rooms, groups);
  const extraNeed = required.map((r, k) => Math.max(r - groups[k], 0));
  const spare = rooms - gTotal;
  const extra = spare >= extraNeed.reduce((s, v) => s + v, 0) ? extraNeed : largestRemainder(spare, extraNeed);
  return groups.map((g, k) => g + extra[k]);
}

/** Totals of `values` per key. */
function sumBy(keys: string[], values: number[]): Map<string, number> {
  const out = new Map<string, number>();
  keys.forEach((k, i) => out.set(k, (out.get(k) ?? 0) + values[i]));
  return out;
}

/** Full-day levels: each grade gets the rooms it needs, or a proportional share when the school has too few. */
function shareByNeed(rooms: number, need: number[]): number[] {
  return rooms >= need.reduce((s, v) => s + v, 0) ? need : largestRemainder(rooms, need);
}

export interface ProjectedYear {
  year: number;
  schools: SchoolLevel[]; // one row per school x level
  grades: GradeRow[];
  combos: ComboRow[]; // school x grade x combination (Upper Secondary, TVET, TTC)
}

/**
 * Run the projection. `info` supplies name, district, sector and coordinates for each school
 * (any 2026 row of the school in the current dataset).
 */
export function runProjection(base: ProjectionBase, intake: Intake, info: Map<number, SchoolLevel>): ProjectedYear[] {
  const L = base.levels.length;
  const G = base.grades.length;
  const gi = new Map(base.grades.map((g, k) => [g, k]));
  const capOf = new Map(base.levels.flatMap((l) => l.grades.map((g) => [g, l.capacity] as const)));
  const schools = base.schools.filter((s) => info.has(s[0]));
  const n = schools.length;
  const district = schools.map((s) => info.get(s[0])!.d);
  const rooms = schools.map((s) => s.slice(1, 1 + L));
  let students = schools.map((s) => s.slice(1 + L, 1 + L + G));
  let groups = schools.map((s) => s.slice(1 + L + G, 1 + L + 2 * G));

  // 2026 district totals per grade, each school's share of its district, and entry group sizes
  const dTot = new Map<string, number[]>();
  students.forEach((st, i) => {
    const t = dTot.get(district[i]) ?? new Array<number>(G).fill(0);
    st.forEach((v, k) => (t[k] += v));
    dTot.set(district[i], t);
  });
  const entry = base.levels.map((l) => l.grades[0]);
  const share: Record<string, number[]> = {};
  const size: Record<string, number[]> = {};
  for (const g of entry) {
    const k = gi.get(g)!;
    share[g] = students.map((st, i) => (st[k] > 0 ? st[k] / dTot.get(district[i])![k] : 0));
    size[g] = students.map((st, i) => (groups[i][k] > 0 ? st[k] / groups[i][k] : capOf.get(g)!));
  }
  const mix: Record<string, number[]> = {};
  for (const [, targets] of base.feeds) {
    for (const t of targets) {
      mix[t] = district.map((d) => {
        const tot = dTot.get(d)!;
        const entrants = targets.reduce((s, x) => s + tot[gi.get(x)!], 0);
        return entrants > 0 ? tot[gi.get(t)!] / entrants : 0;
      });
    }
  }

  // N1: each school's catchment, scaled so its district adds up to the plan
  const Y = base.years.length - 1;
  const catchOf = new Map(base.catchment.map(([c, ...v]) => [c, v]));
  const catchment = schools.map((s) => catchOf.get(s[0]) ?? new Array<number>(Y).fill(0));
  const catchTotal = base.years.slice(1).map((_, yi) => sumBy(district, catchment.map((c) => c[yi])));

  // N3 -> P1: schools offering the target level keep their own leavers; the others' leavers are pooled by
  // sector (district when the sector has none of the target grade) and shared by the 2026 students of that grade
  const levelOf = new Map(base.levels.flatMap((l, li) => l.grades.map((g) => [g, li] as const)));
  const sector = schools.map((s, i) => `${district[i]}|${info.get(s[0])!.s}`);
  const offers: Record<string, boolean[]> = {};
  const sectorShare: Record<string, number[]> = {};
  const districtShare: Record<string, number[]> = {};
  for (const [, dst] of base.schoolFeeds) {
    const li = levelOf.get(dst)!;
    const k = gi.get(dst)!;
    offers[dst] = rooms.map((r) => r[li] > 0);
    const weight = students.map((st, i) => (offers[dst][i] ? st[k] : 0));
    const poolShare = (key: string[]) => {
      const total = sumBy(key, weight);
      return weight.map((w, i) => (total.get(key[i])! > 0 ? w / total.get(key[i])! : 0));
    };
    sectorShare[dst] = poolShare(sector);
    districtShare[dst] = poolShare(district);
  }

  // Combinations (Upper Secondary, TVET, TTC): per level, school x grade of the level x combination
  const comboLevels = base.levels
    .map((l, li) => ({ li, grades: l.grades, names: base.combos[li] ?? [] }))
    .filter((cl) => cl.names.length > 0);
  const rowOf = new Map(schools.map((s, i) => [s[0], i]));
  const cStudents = new Map<number, number[][][]>();
  const cGroups = new Map<number, number[][][]>();
  const blank = (cl: (typeof comboLevels)[number]) =>
    schools.map(() => cl.grades.map(() => new Array<number>(cl.names.length).fill(0)));
  for (const cl of comboLevels) {
    cStudents.set(cl.li, blank(cl));
    cGroups.set(cl.li, blank(cl));
  }
  for (const [code, k, c, st, g] of base.schoolCombos) {
    const i = rowOf.get(code);
    const cl = comboLevels.find((x) => x.grades.includes(base.grades[k]));
    if (i === undefined || !cl) continue;
    const kk = cl.grades.indexOf(base.grades[k]);
    cStudents.get(cl.li)![i][kk][c] = st;
    cGroups.get(cl.li)![i][kk][c] = g;
  }
  // 2026 mix of the entry grade, used to split each year's new students and groups
  const mixStudents = new Map(comboLevels.map((cl) => [cl.li, cStudents.get(cl.li)!.map((s) => [...s[0]])]));
  const mixGroups = new Map(comboLevels.map((cl) => [cl.li, cGroups.get(cl.li)!.map((s) => [...s[0]])]));

  return base.years.map((year, yi) => {
    if (yi > 0) {
      const prevS = students;
      const prevG = groups;
      students = prevS.map(() => new Array<number>(G).fill(0));
      groups = prevG.map(() => new Array<number>(G).fill(0));
      for (const { grades } of base.levels) {
        for (let k = 1; k < grades.length; k++) {
          const to = gi.get(grades[k])!;
          const from = gi.get(grades[k - 1])!;
          for (let i = 0; i < n; i++) {
            students[i][to] = prevS[i][from];
            groups[i][to] = prevG[i][from];
          }
        }
      }
      const fresh: [string, number[]][] = [];
      for (const g of Object.keys(base.intakes)) {
        const total = catchTotal[yi - 1];
        fresh.push([g, schools.map((_, i) => {
          const t = total.get(district[i])!;
          return t > 0 ? roundHalfUp(((intake[g]?.[district[i]]?.[yi - 1] ?? 0) * catchment[i][yi - 1]) / t) : 0;
        })]);
      }
      for (const [src, dst] of base.schoolFeeds) {
        const k = gi.get(src)!;
        const leavers = prevS.map((st) => st[k]);
        const away = leavers.map((v, i) => (offers[dst][i] ? 0 : v));
        const sectorPool = sumBy(sector, away);
        // sectors with leavers but no school to receive them: their leavers go to the district
        const receives = sumBy(sector, sectorShare[dst]);
        const districtPool = sumBy(district, away.map((v, i) => (receives.get(sector[i])! > 0 ? 0 : v)));
        fresh.push([dst, schools.map((_, i) => (offers[dst][i] ? leavers[i] : 0)
          + roundHalfUp(sectorPool.get(sector[i])! * sectorShare[dst][i])
          + roundHalfUp(districtPool.get(district[i])! * districtShare[dst][i]))]);
      }
      for (const [src, targets] of base.feeds) {
        const k = gi.get(src)!;
        const pool = new Map<string, number>();
        prevS.forEach((st, i) => pool.set(district[i], (pool.get(district[i]) ?? 0) + st[k]));
        for (const t of targets) {
          fresh.push([t, schools.map((_, i) => roundHalfUp(pool.get(district[i])! * mix[t][i] * share[t][i]))]);
        }
      }
      for (const [g, v] of fresh) {
        const k = gi.get(g)!;
        for (let i = 0; i < n; i++) {
          students[i][k] = v[i];
          groups[i][k] = Math.ceil(v[i] / size[g][i]);
        }
      }
      // Combinations move up with their cohort; new entrants are split by the school's 2026 mix
      for (const cl of comboLevels) {
        const e = gi.get(cl.grades[0])!;
        const prevS = cStudents.get(cl.li)!;
        const prevG = cGroups.get(cl.li)!;
        cStudents.set(cl.li, prevS.map((s, i) => [largestRemainder(students[i][e], mixStudents.get(cl.li)![i]), ...s.slice(0, -1)]));
        cGroups.set(cl.li, prevG.map((s, i) => [largestRemainder(groups[i][e], mixGroups.get(cl.li)![i]), ...s.slice(0, -1)]));
      }
    }

    const comboRows: ComboRow[] = [];
    for (const cl of comboLevels) {
      const cs = cStudents.get(cl.li)!;
      const cg = cGroups.get(cl.li)!;
      schools.forEach((s, i) => {
        cl.grades.forEach((grade, kk) => {
          cl.names.forEach((name, c) => {
            if (cs[i][kk][c] > 0 || cg[i][kk][c] > 0) {
              comboRows.push([s[0], base.gradeIndex[gi.get(grade)!], name, cs[i][kk][c], cg[i][kk][c]]);
            }
          });
        });
      });
    }

    const schoolRows: SchoolLevel[] = [];
    const gradeRows: GradeRow[] = [];
    base.levels.forEach(({ level, grades, capacity: cap, fullDay }, li) => {
      const cols = grades.map((g) => gi.get(g)!);
      const cs = cStudents.get(li);
      const cg = cGroups.get(li);
      schools.forEach((s, i) => {
        const r = rooms[i][li];
        if (r <= 0) return; // level not offered in 2026
        const code = s[0];
        const st = cols.map((k) => students[i][k]);
        const gr = cols.map((k) => groups[i][k]);
        let req: number[];
        let assigned: number[];
        if (fullDay) {
          // every class group needs a room; combinations never share
          req = cs && cg
            ? cols.map((_, j) => cs[i][j].reduce((a, v, c) => a + Math.max(cg[i][j][c], Math.ceil(v / cap)), 0))
            : st.map((v, j) => Math.max(gr[j], Math.ceil(v / cap)));
          assigned = shareByNeed(r, req);
        } else {
          req = st.map((v) => Math.ceil(v / cap));
          assigned = shareRooms(r, gr, req);
        }
        cols.forEach((k, j) => {
          gradeRows.push([code, base.gradeIndex[k], st[j], gr[j], Math.max(gr[j] - assigned[j], 0), assigned[j], req[j], assigned[j] - req[j]]);
        });
        const total = st.reduce((a, v) => a + v, 0);
        const gTotal = gr.reduce((a, v) => a + v, 0);
        const required = fullDay ? req.reduce((a, v) => a + v, 0) : Math.ceil(total / cap);
        schoolRows.push({
          ...info.get(code)!, l: level, st: total, g: gTotal, ds: Math.max(gTotal - r, 0), a: r, r: required, gap: r - required,
        });
      });
    });
    return { year, schools: schoolRows, grades: gradeRows, combos: comboRows };
  });
}

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
    throw new Error(`No year columns found. Expected columns like pop3_${years[0]}, pop6_${years[0]} or ${years[0]}.`);
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
