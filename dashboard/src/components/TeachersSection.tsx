import { fmt, type SchoolLevel } from '../data';
import {
  fmtRatio, hasTeachers, pupilsPerTeacher, teacherRows, teacherStudents, teacherTotals, teacherTotalsBy,
} from '../teachers';
import type { Mode } from '../theme';
import { PupilsPerTeacherBars, PupilsPerTeacherTrend, type TeacherItem } from './Charts';
import { Card, SectionTitle } from './Overview';

const TOP_SCHOOLS = 50; // schools in the highest-pupils-per-teacher chart

function Figure({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="card px-3.5 py-2">
      <div className="text-xs text-ink2">{label}</div>
      <div className="mt-1 text-xl font-semibold leading-tight text-ink">{value}</div>
      <div className="text-[11px] leading-snug text-muted">{note}</div>
    </div>
  );
}

/**
 * Teachers and pupils per teacher for the schools in scope (`codes`) and the level of the filters: the year shown, by
 * area, by year, and the schools with the most pupils per teacher. `byYear` holds every year's school x level rows with
 * their teachers (projected years: the base year's teachers, teachers.ts withTeachers).
 */
export default function TeachersSection({ byYear, year, baseYear, actualYears, level, district, codes, mode, onPickSchool,
  onPickYear }: {
  byYear: { year: number; rows: SchoolLevel[] }[];
  year: number;
  baseYear: number;
  actualYears: number[];
  level: number;
  district: string;
  codes: Set<number>;
  mode: Mode;
  onPickSchool: (code: string) => void;
  onPickYear: (year: string) => void;
}) {
  const scoped = (rows: SchoolLevel[]) => teacherRows(rows.filter((r) => codes.has(r.c)), level);
  const rows = scoped(byYear.find((y) => y.year === year)?.rows ?? []);
  const t = teacherTotals(rows);

  const areaOf = district ? (r: SchoolLevel) => r.s : (r: SchoolLevel) => r.d;
  const areas: TeacherItem[] = [...teacherTotalsBy(rows.filter(hasTeachers), areaOf)]
    .map(([name, a]) => ({ name, ratio: a.ratio ?? 0, teachers: a.teachers, students: a.students }));
  const trend = byYear.map((y) => {
    const a = teacherTotals(scoped(y.rows));
    return { year: y.year, ratio: a.ratio, teachers: a.teachers, students: a.students };
  });
  const names = new Map<string, number>();
  const top = rows.filter(hasTeachers)
    .map((r) => ({ r, ratio: pupilsPerTeacher(r)! }))
    .sort((a, b) => b.ratio - a.ratio)
    .slice(0, TOP_SCHOOLS)
    .map(({ r, ratio }) => {
      const name = `${r.n} · ${r.c}`;
      names.set(name, r.c);
      return { name, ratio, teachers: r.t!, students: teacherStudents(r) };
    });

  const projected = year > baseYear;
  const heldNote = projected ? `held at the ${baseYear} count` : `${year} teachers file`;
  return (
    <>
      <SectionTitle title="Teachers"
        sub={`Public and government-aided schools in the MINEDUC teachers file${projected ? `; ${year} students with the ${baseYear} teachers (no recruitment assumed)` : ''}`} />
      {t.schools === 0 ? (
        <Card title={`No teacher data for ${year}`}
          sub="None of the schools in scope has teachers in the MINEDUC teachers file (private schools are not in it).">
          <div className="pb-2" />
        </Card>
      ) : (
        <>
          <div className="print-tiles-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Figure label="Teachers" value={fmt(t.teachers)} note={heldNote} />
            <Figure label="Pupils per teacher" value={fmtRatio(t.ratio)}
              note={`${fmt(t.students)} students of the schools with teacher data`} />
            <Figure label="Schools with teacher data" value={fmt(t.schools)}
              note={t.noDataSchools || t.noDataStudents
                ? `${fmt(t.noDataSchools)} schools, ${fmt(t.noDataStudents)} students without teacher data (mostly private schools)`
                : 'every school in scope'} />
          </div>
          <div className="print-cols-2 grid gap-4 lg:grid-cols-2">
            <Card title={`Pupils per teacher by ${district ? 'sector' : 'district'}`}
              sub={`${year}${projected ? ' projected' : ''} · schools with teacher data only`}>
              <div className="px-2 pb-3">
                <PupilsPerTeacherBars data={areas} mode={mode} label={`Pupils per teacher by ${district ? 'sector' : 'district'}`} />
              </div>
            </Card>
            <Card title="Pupils per teacher by year"
              sub={`Actual, then projected students with the ${baseYear} teachers · click a bar to show that year`}>
              <div className="px-2 pb-3">
                <PupilsPerTeacherTrend data={trend} mode={mode} year={year} actual={actualYears} onPick={onPickYear} />
              </div>
            </Card>
          </div>
          <Card title={`Highest pupils per teacher — ${Math.min(TOP_SCHOOLS, top.length)} schools`}
            sub={`${year} · click a bar for the school's details`}>
            <div className="print-expand px-2 pb-3">
              <PupilsPerTeacherBars data={top} mode={mode} label="Schools with the most pupils per teacher"
                pickText="Click for the school's details"
                onPick={(name) => {
                  const code = names.get(name);
                  if (code !== undefined) onPickSchool(String(code));
                }} />
            </div>
          </Card>
        </>
      )}
    </>
  );
}
