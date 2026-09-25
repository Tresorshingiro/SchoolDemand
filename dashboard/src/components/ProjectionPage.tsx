import { useCallback, useEffect, useMemo, useState } from 'react';
import { fmt, type Dataset, type SchoolLevel } from '../data';
import {
  cohortTable, comboTable, defaultIntake, gradeByDistrict, loadProjectionBase, projectionMeta, runProjection, sameIntake,
  yearDataset, yearTotals,
  type Intake, type ProjectionBase, type ProjectedYear,
} from '../projection';
import type { Mode } from '../theme';
import Overview, { Card } from './Overview';
import IntakePlanner, { FedEntrants } from './IntakePlanner';
import { CohortChart, CompareBars, YearTrend } from './Charts';

// v3: N1 defaults to the catchment totals and P1 comes from N3, so plans saved against the NISR default are dropped
const STORAGE_KEY = 'classroom-dashboard-intake-v3';

function storedIntake(base: ProjectionBase): Intake | null {
  const n = base.years.length - 1;
  const valid = (t: unknown, g: string) =>
    !!t && Object.keys(base.population[g]).every((d) => Array.isArray((t as Record<string, number[]>)[d]) && (t as Record<string, number[]>)[d].length === n);
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const v = JSON.parse(raw) as Intake;
      if (Object.keys(base.intakes).every((g) => valid(v[g], g))) return v;
    }
  } catch {
    /* unreadable — fall back to the default plan */
  }
  return null;
}

function saveIntake(v: Intake) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(v));
  } catch {
    /* storage unavailable — the plan lasts for this visit only */
  }
}

/** Students by grade and year: each cohort moves one step down and to the right. */
function CohortTable({ years, baseYear, year, rows, entryNote }: {
  years: number[]; baseYear: number; year: number; rows: { grade: string; byYear: number[] }[]; entryNote: string;
}) {
  return (
    <div className="overflow-x-auto px-4 pb-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            <th className="px-2 py-1.5 text-left font-medium">Grade</th>
            {years.map((y) => (
              <th key={y} className={`px-2 py-1.5 text-right font-medium ${y === year ? 'text-ink' : ''}`}>
                {y}{y === baseYear ? '*' : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, gi) => (
            <tr key={r.grade} className="border-b border-line">
              <td className="px-2 py-1.5 text-ink">{r.grade}</td>
              {r.byYear.map((v, yi) => (
                <td key={yi}
                  className={`num px-2 py-1.5 text-right ${years[yi] === year ? 'bg-[var(--line)] font-semibold text-ink' : 'text-ink2'} ${
                    gi === yi ? 'underline decoration-accent decoration-2 underline-offset-4' : ''}`}>
                  {fmt(v)}
                </td>
              ))}
            </tr>
          ))}
          <tr className="text-ink">
            <td className="px-2 py-1.5 font-semibold">Total</td>
            {years.map((y, yi) => (
              <td key={y} className="num px-2 py-1.5 text-right font-semibold">
                {fmt(rows.reduce((s, r) => s + r.byYear[yi], 0))}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">
        * actual. Underlined: the {baseYear} {rows[0]?.grade} cohort moving up a grade each year. Each year the last grade
        leaves the level and {entryNote}.
      </p>
    </div>
  );
}

/** Students per combination (rows) and year (columns); rows sorted by the selected year. */
function CombinationTable({ years, baseYear, year, rows }: {
  years: number[]; baseYear: number; year: number;
  rows: { combination: string; students: number[]; groups: number[] }[];
}) {
  const yi = Math.max(years.indexOf(year), 0);
  const sorted = [...rows].sort((a, b) => b.students[yi] - a.students[yi] || b.students[0] - a.students[0]);
  return (
    <div className="px-4 pb-4">
      <div className="print-expand max-h-[420px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-line text-xs text-muted">
              <th className="px-2 py-1.5 text-left font-medium">Combination</th>
              {years.map((y) => (
                <th key={y} className={`px-2 py-1.5 text-right font-medium ${y === year ? 'text-ink' : ''}`}>
                  {y}{y === baseYear ? '*' : ''}
                </th>
              ))}
              <th className="px-2 py-1.5 text-right font-medium">Class groups {year}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.combination} className="border-b border-line">
                <td className="px-2 py-1.5 text-ink">{r.combination}</td>
                {r.students.map((v, k) => (
                  <td key={k} className={`num px-2 py-1.5 text-right ${k === yi ? 'bg-[var(--line)] font-semibold text-ink' : 'text-ink2'}`}>
                    {fmt(v)}
                  </td>
                ))}
                <td className="num px-2 py-1.5 text-right text-ink2">{fmt(r.groups[yi])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">
        * actual. Students keep their combination as they move up; each school's new entrants are split by its {baseYear} mix
        in the entry grade. A breakdown of the grade totals — rooms are counted per grade, not per combination.
      </p>
    </div>
  );
}

export default function ProjectionPage({ current, mode }: { current: Dataset; mode: Mode }) {
  const [base, setBase] = useState<ProjectionBase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [intake, setIntake] = useState<Intake | null>(null);
  const [year, setYear] = useState(2030);
  const [plannerOpen, setPlannerOpen] = useState(true);

  useEffect(() => {
    loadProjectionBase()
      .then((b) => {
        setBase(b);
        setIntake(storedIntake(b) ?? defaultIntake(b));
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const changeIntake = useCallback((next: Intake) => {
    setIntake(next);
    saveIntake(next);
  }, []);

  // Name, district, sector and coordinates of every school (from any of its 2026 rows)
  const info = useMemo(() => {
    const m = new Map<number, SchoolLevel>();
    for (const r of current.schools) if (!m.has(r.c)) m.set(r.c, r);
    return m;
  }, [current]);
  const result = useMemo<ProjectedYear[] | null>(
    () => (base && intake ? runProjection(base, intake, info) : null),
    [base, intake, info],
  );
  const meta = useMemo(() => (base ? projectionMeta(base, current.meta) : current.meta), [base, current]);
  // Students per district and year for every entry grade
  const entryByDistrict = useMemo(() => {
    if (!base || !result) return {};
    return Object.fromEntries(base.levels.map((l) => [l.grades[0], gradeByDistrict(result, meta, l.grades[0], info)]));
  }, [base, result, meta, info]);
  const presetLabel = useMemo(() => {
    if (!base || !intake) return '';
    return sameIntake(intake, base.population) ? base.defaultLabel : 'Custom plan';
  }, [base, intake]);
  const pickYear = useCallback((y: string) => setYear(Number(y)), []);

  if (error) return <div className="p-8 text-sm text-ink2">Could not load the projection: {error}</div>;
  if (!base || !intake || !result) return <div className="grid min-h-[50vh] place-items-center text-sm text-muted">Loading projection…</div>;

  const py = result.find((r) => r.year === year) ?? result[result.length - 1];
  const isBase = year === base.baseYear;
  const years = base.years.slice(1);
  // Where the new students of an entry grade come from: a district pool (P6 -> S1) or the same school (N3 -> P1)
  const feedOf = (grade: string) => {
    const f = base.feeds.find(([, targets]) => targets.includes(grade));
    if (f) return { source: f[0], targets: f[1], sameSchool: false };
    const sf = base.schoolFeeds.find(([, dst]) => dst === grade);
    return sf ? { source: sf[0], targets: [sf[1]], sameSchool: true } : undefined;
  };
  const entryNote = (grade: string) => {
    if (base.intakes[grade] !== undefined) return `the new ${grade} from the intake plan arrives`;
    const feed = feedOf(grade);
    return feed ? `the new ${grade} arrives from the ${feed.source} of the year before` : `no new ${grade} arrives`;
  };

  return (
    <Overview
      key="projection"
      data={yearDataset(py, meta)}
      mode={mode}
      showLevels
      scopePrefix={`${year}${isBase ? ' actual' : ' projected'} · Intake: ${presetLabel}`}
      panelContext={`${isBase ? 'Actual' : 'Projected'} ${year} · Intake: ${presetLabel}`}
      notes={{
        available: `${base.baseYear} rooms, no new construction`,
        gradeChart: "Each grade's rooms = the school's rooms for the level shared out between its grades that year.",
      }}
      controls={
        <>
          <span className="hidden text-xs text-muted sm:inline">Intake: {presetLabel}</span>
          <label className="flex items-center gap-2 text-sm text-ink2">
            Year
            <select aria-label="Year" value={year} className="h-8 px-2 text-sm font-medium text-ink"
              onChange={(e) => setYear(Number(e.target.value))}>
              {base.years.map((y) => (
                <option key={y} value={y}>{y}{y === base.baseYear ? ' (actual)' : ''}</option>
              ))}
            </select>
          </label>
        </>
      }
      top={(codes, filters) => {
        const level = base.levels.find((l) => l.level === filters.level) ?? base.levels[0];
        const entry = level.grades[0];
        const age = base.intakes[entry];
        const feed = feedOf(entry);
        const byDistrict = entryByDistrict[entry];
        const cohort = cohortTable(result, meta, level.grades, codes);
        const national = years.map((_, yi) => [...byDistrict.values()].reduce((s, v) => s + v[yi + 1], 0));
        const perYear = years.map((y, yi) => `${y} ${fmt(national[yi])}`).join(' · ');
        return (
          <>
            {age !== undefined ? (
              <Card title={`${entry} intake plan — new ${entry} students per district`}
                sub={`Children aged ${age} in the schools' catchment areas · ${sameIntake(intake, base.population, entry) ? base.defaultLabel : 'Custom plan'} · new ${entry} nationally: ${perYear}`}
                aside={<button type="button" onClick={() => setPlannerOpen((o) => !o)} aria-expanded={plannerOpen} className="rounded-md border border-line px-2.5 py-1 text-xs text-ink2 hover:text-ink print:hidden">{plannerOpen ? 'Hide table' : 'Show table'}</button>}>
                {plannerOpen ? (
                  <IntakePlanner base={base} intake={intake} onChange={changeIntake} grade={entry}
                    baseByDistrict={byDistrict} district={filters.district} mode={mode} />
                ) : null}

              </Card>
            ) : feed ? (
              <Card title={`New ${entry} students per district`}
                sub={`From the ${feed.source} of the year before${feed.sameSchool ? ' in the same school' : ''}${feed.targets.length > 1 ? `, split between ${feed.targets.join(' / ')} by each district's ${base.baseYear} mix` : ''} · nationally: ${perYear}`}
                aside={<button type="button" onClick={() => setPlannerOpen((o) => !o)} aria-expanded={plannerOpen} className="rounded-md border border-line px-2.5 py-1 text-xs text-ink2 hover:text-ink print:hidden">{plannerOpen ? 'Hide table' : 'Show table'}</button>}>
                {plannerOpen && (
                  <FedEntrants base={base} grade={entry} source={feed.source} targets={feed.targets} sameSchool={feed.sameSchool}
                    byDistrict={Object.fromEntries(feed.targets.map((t) => [t, entryByDistrict[t]]))} district={filters.district}
                    mode={mode} />
                )}
              </Card>
            ) : null}
            <Card title="Students by grade and year"
              sub="Cohorts move up one grade a year. The selected year is highlighted; click a column to show that year.">
              <div className="print-cols-5 grid items-start gap-4 px-2 lg:grid-cols-5">
                <div className="print-span-3 pb-3 lg:col-span-3">
                  <CohortChart rows={cohort} years={base.years} baseYear={base.baseYear} year={year} mode={mode} onPick={pickYear} />
                </div>
                <div className="print-span-2 lg:col-span-2">
                  <CohortTable years={base.years} baseYear={base.baseYear} year={year} entryNote={entryNote(entry)} rows={cohort} />
                </div>
              </div>
            </Card>
            {(base.combos[base.levels.indexOf(level)] ?? []).length > 0 && (
              <Card title="Students by combination and year"
                sub={`${level.grades.join(', ')} combined. The selected year is highlighted; largest first.`}>
                <CombinationTable years={base.years} baseYear={base.baseYear} year={year}
                  rows={comboTable(result, meta, level.grades, codes)} />
              </Card>
            )}
          </>
        );
      }}
      shortageTop={(codes, filters) => {
        const level = base.levels.find((l) => l.level === filters.level) ?? base.levels[0];
        const byYear = yearTotals(result, filters.level, codes);
        return (
          <div className="print-cols-2 grid gap-4 lg:grid-cols-2">
            <Card title="Classrooms short by year" sub="Classrooms to build if no rooms are added. Click a bar to show that year.">
              <div className="px-2 pb-3">
                <YearTrend data={byYear} mode={mode} year={year} baseYear={base.baseYear} onPick={pickYear} fullDay={level.fullDay} />
              </div>
            </Card>
            <Card title="Rooms available vs required by year"
              sub={`Rooms stay at the ${base.baseYear} count while the rooms needed follow the students. Click a year to show it.`}>
              <div className="px-2 pb-3">
                <CompareBars data={byYear.map((d) => ({ ...d, name: String(d.year) }))} mode={mode} fullDay={level.fullDay}
                  highlight={String(year)} onPick={pickYear} label="Rooms available versus required by year" />
              </div>
            </Card>
          </div>
        );
      }}
    />
  );
}
