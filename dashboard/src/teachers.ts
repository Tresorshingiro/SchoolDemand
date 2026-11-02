/**
 * Teachers and pupils per teacher (backend/app/domain/teachers.py). Each school x level row of an actual school year
 * carries `t`, its teachers (null = no teacher data: the school is not in the MINEDUC teachers file, mostly private
 * schools, or records no teachers for that level). Projected years keep the base year's teachers (withTeachers), as
 * classrooms keep the base year's rooms. A row without teacher data is left out of pupils per teacher and counted
 * apart — never shown as 0 teachers.
 */
import { ALL_LEVELS, bySchool, type SchoolLevel } from './data';

export const teacherKey = (c: number, l: number) => `${c}|${l}`;

/** Teachers of each school x level of an actual year's rows. */
export function teacherMap(rows: SchoolLevel[]): Map<string, number | null> {
  return new Map(rows.map((r) => [teacherKey(r.c, r.l), r.t ?? null]));
}

/** Rows with the teachers of `map` (a projected year with the base year's teachers; planned schools have none). */
export const withTeachers = (rows: SchoolLevel[], map: Map<string, number | null>): SchoolLevel[] =>
  rows.map((r) => ({ ...r, t: map.get(teacherKey(r.c, r.l)) ?? null }));

/** Does the row have teachers to divide by? */
export const hasTeachers = (r: SchoolLevel) => r.t != null && r.t > 0;

/** Students counted against the row's teachers ("All levels" rows: the levels with teacher data only). */
export const teacherStudents = (r: SchoolLevel) => r.tst ?? r.st;

/** Pupils per teacher of a row, null without teacher data. */
export const pupilsPerTeacher = (r: SchoolLevel): number | null => (hasTeachers(r) ? teacherStudents(r) / r.t! : null);

/** One row per school x level of `level`, or per school (levels with teacher data added up) for ALL_LEVELS. */
export const teacherRows = (rows: SchoolLevel[], level: number): SchoolLevel[] =>
  level === ALL_LEVELS ? bySchool(rows) : rows.filter((r) => r.l === level);

export interface TeacherTotals {
  teachers: number;
  students: number; // of the rows with teachers
  ratio: number | null; // pupils per teacher, null when no row has teachers
  schools: number; // rows with teachers
  noDataSchools: number; // rows without teacher data
  noDataStudents: number;
}

export function teacherTotals(rows: SchoolLevel[]): TeacherTotals {
  const t: TeacherTotals = { teachers: 0, students: 0, ratio: null, schools: 0, noDataSchools: 0, noDataStudents: 0 };
  for (const r of rows) {
    if (hasTeachers(r)) {
      t.teachers += r.t!;
      t.students += teacherStudents(r);
      t.schools += 1;
      t.noDataStudents += r.st - teacherStudents(r); // "All levels": the school's levels without teacher data
    } else {
      t.noDataSchools += 1;
      t.noDataStudents += r.st;
    }
  }
  t.ratio = t.teachers ? t.students / t.teachers : null;
  return t;
}

/** teacherTotals per area (district, sector ...). */
export function teacherTotalsBy(rows: SchoolLevel[], key: (r: SchoolLevel) => string): Map<string, TeacherTotals> {
  const groups = new Map<string, SchoolLevel[]>();
  for (const r of rows) {
    const k = key(r);
    const list = groups.get(k);
    if (list) list.push(r);
    else groups.set(k, [r]);
  }
  return new Map([...groups].map(([k, list]) => [k, teacherTotals(list)]));
}

const one = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1, minimumFractionDigits: 1 });
/** "38.4", or "—" without teacher data. */
export const fmtRatio = (v: number | null) => (v == null ? '—' : one.format(v));
