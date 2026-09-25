import { useCallback, useMemo, useState, type ReactNode } from 'react';
import {
  applyFilters, fmt, fmtGap, gradeTotals, gradesByArea, pct, provinceOf, totals, totalsBy,
  type Dataset, type Filters, type Totals,
} from '../data';
import type { Mode } from '../theme';
import { printReport, usePrinting } from '../print';
import SchoolMap from './SchoolMap';
import SchoolTable from './SchoolTable';
import SchoolPanel from './SchoolPanel';
import {
  CompareBars, CrowdingByArea, DoubleShiftByArea, GapHistogram, GradeChart, GradeLegend, ShortageByArea, StackedGradesByArea, StatusSplit, dsName,
} from './Charts';

export const PRIMARY = 1;

export function Card({ title, sub, children, className = '', aside }: {
  title: string; sub?: string; children: ReactNode; className?: string; aside?: ReactNode;
}) {
  return (
    <section className={`card ${className}`}>
      <header className="flex flex-wrap items-start gap-2 px-4 pb-2 pt-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** Heading that opens a part of the page (what schools have, where classrooms are short). */
export function SectionTitle({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="print-keep-next flex flex-wrap items-baseline gap-x-3 gap-y-0.5 pt-4">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {sub && <p className="text-xs text-muted">{sub}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ stat tiles */

const ICONS = {
  school: 'M3 21h18M5 21V10l7-5 7 5v11M9 21v-5h6v5M12 5V2l3 1.5L12 5',
  students: 'M16 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 18.5V20M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M20 20v-1.5a3.5 3.5 0 0 0-2.5-3.3M15.5 4.2a3.5 3.5 0 0 1 0 6.6',
  groups: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  door: 'M4 21h16M6 21V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v17M14 12h.01',
  required: 'M9 4h6v3H9zM9 5.5H6a1 1 0 0 0-1 1V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6.5a1 1 0 0 0-1-1h-3M9 12h6M9 16h4',
  shift: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 7v5l3 2',
  alert: 'M12 3 2 20h20L12 3M12 10v4M12 17h.01',
} as const;

function Icon({ name, className = '' }: { name: keyof typeof ICONS; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75"
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

function Stat({ icon, label, value, note, alert = false, className = '' }: {
  icon: keyof typeof ICONS; label: string; value: string; note?: string; alert?: boolean; className?: string;
}) {
  return (
    <div className={`card relative overflow-hidden px-4 py-3 ${className}`}>
      {alert && <div className="absolute inset-x-0 top-0 h-[3px] bg-[var(--deficit)]" aria-hidden="true" />}
      <div className="flex items-center gap-2 text-xs text-ink2">
        <span className={`grid h-7 w-7 place-items-center rounded-md ${
          alert ? 'bg-[var(--deficit-soft)] text-[var(--deficit)]' : 'bg-[var(--accent-soft)] text-accent'}`}>
          <Icon name={icon} />
        </span>
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold text-ink">{value}</div>
      {note && <div className="mt-0.5 text-xs text-muted">{note}</div>}
    </div>
  );
}

function Tiles({ t, notes, level }: {
  t: Totals; notes: { available: string }; level: { label: string; capacity: number; fullDay: boolean };
}) {
  const avg = (a: number, b: number) => (b ? fmt(Math.round(a / b)) : '—');
  return (
    <div className="print-cols-tiles grid gap-4 xl:grid-cols-[4fr_3fr]">
      <section aria-label="What schools have">
        <div className="print-tiles-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat icon="school" label="Schools" value={fmt(t.schools)} note={`offering ${level.label.toLowerCase()}`} />
          <Stat icon="students" label="Students" value={fmt(t.students)} note={`${avg(t.students, t.schools)} per school on average`} />
          <Stat icon="groups" label="Class groups" value={fmt(t.classGroups)}
            note={`${avg(t.students, t.classGroups)} students per group on average`} />
          <Stat icon="door" label="Rooms available" value={fmt(t.available)} note={notes.available} />
        </div>
      </section>
      <section aria-label="What is needed">
        <div className="print-tiles-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Stat icon="required" label="Rooms required" value={fmt(t.required)}
            note={level.fullDay
              ? `a room per class group, ${level.capacity} per room, per grade and combination`
              : `students ÷ ${level.capacity}, rounded up per school`} />
          <Stat icon="shift" label={dsName(level.fullDay)} value={fmt(t.doubleShift)}
            note={`${pct(t.doubleShift, t.classGroups)} of class groups${level.fullDay ? ' · full day, no double shift' : ''}`} />
          <Stat icon="alert" label="Classrooms short" value={fmt(t.short)} alert className="col-span-2 sm:col-span-1"
            note={`in ${fmt(t.deficitSchools)} schools · net gap ${fmtGap(t.netGap)}`} />
        </div>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ page */

interface Props {
  data: Dataset;
  mode: Mode;
  /** Show the school-level switch (otherwise fixed to primary). */
  showLevels?: boolean;
  /** Extra controls at the start of the filter bar. */
  controls?: ReactNode;
  /** Prefix for the scope line on the right of the filter bar. */
  scopePrefix?: string;
  /** Extra cards below the stat tiles, given the school codes in scope and the current filters. */
  top?: (codes: Set<number>, filters: Filters) => ReactNode;
  /** Extra cards opening the shortage part of the page. */
  shortageTop?: (codes: Set<number>, filters: Filters) => ReactNode;
  notes: { available: string; gradeChart: string };
  /** Line shown under the school name in the detail panel. */
  panelContext?: string;
  footer?: (capacity: number) => ReactNode;
}

/** Filter bar, stat tiles, resource charts, then shortage map, charts and school table over one Dataset. */
export default function Overview({
  data, mode, showLevels = false, controls, scopePrefix, top, shortageTop, notes, panelContext, footer,
}: Props) {
  const [filters, setFilters] = useState<Filters>({ level: PRIMARY, district: '', sector: '' });
  const [selected, setSelected] = useState<number | null>(null);
  const printing = usePrinting();

  const levelRows = useMemo(() => data.schools.filter((r) => r.l === filters.level), [data, filters.level]);
  const districts = useMemo(() => [...new Set(levelRows.map((r) => r.d))].sort(), [levelRows]);
  const sectors = useMemo(
    () => (filters.district ? [...new Set(levelRows.filter((r) => r.d === filters.district).map((r) => r.s))].sort() : []),
    [levelRows, filters.district],
  );
  const rows = useMemo(() => applyFilters(data.schools, filters), [data, filters]);
  const codes = useMemo(() => new Set(rows.map((r) => r.c)), [rows]);
  const t = useMemo(() => totals(rows), [rows]);

  // Area charts: districts for the whole level, or the sectors of the chosen district.
  const areaRows = useMemo(
    () => (filters.district ? levelRows.filter((r) => r.d === filters.district) : levelRows),
    [levelRows, filters.district],
  );
  const areaLabel = filters.district ? 'sector' : 'district';
  const areaKey = useCallback((r: { d: string; s: string }) => (filters.district ? r.s : r.d), [filters.district]);
  const byArea = useMemo(() => [...totalsBy(areaRows, areaKey)], [areaRows, areaKey]);
  const areaGrades = useMemo(
    () => gradesByArea(data.grades, data.meta, filters.level, areaRows, areaKey),
    [data, filters.level, areaRows, areaKey],
  );
  // Available vs required: provinces for the whole country, sectors inside a district.
  const compare = useMemo(() => {
    const groups = filters.district ? byArea : [...totalsBy(levelRows, (r) => provinceOf(r.d))];
    return groups
      .map(([name, x]) => ({ name, ...x }))
      .sort((a, b) => (filters.district ? b.short - a.short : a.name.localeCompare(b.name)));
  }, [filters.district, byArea, levelRows]);
  const grades = useMemo(
    () => gradeTotals(data.grades, data.meta, filters.level, codes),
    [data, filters.level, codes],
  );

  const pickArea = useCallback(
    (name: string) =>
      setFilters((f) => (f.district ? { ...f, sector: f.sector === name ? '' : name } : { ...f, district: name, sector: '' })),
    [],
  );
  const closePanel = useCallback(() => setSelected(null), []);
  const pickLevel = (i: number) => {
    setFilters({ level: i, district: '', sector: '' });
    setSelected(null);
  };
  const flagged = useMemo(() => new Set(Object.keys(data.meta.schoolIssues).map(Number)), [data.meta]);
  const gaps = useMemo(() => rows.map((r) => r.gap), [rows]);

  const { meta } = data;
  const level = meta.levels[filters.level];
  const scope = [filters.sector && `${filters.sector} sector`, filters.district && `${filters.district} district`]
    .filter(Boolean).join(', ') || 'All districts';
  const reportScope = scopePrefix ?? `${meta.built.slice(0, 4)} actual`;
  const reportFile = ['Classroom_Sufficiency', level.label, filters.sector || filters.district || 'Rwanda', reportScope]
    .join(' - ').replace(/[·:]/g, '').replace(/\s+/g, ' ').trim();
  const pickHint = filters.district ? 'Click a bar to filter to that sector.' : 'Click a bar to filter to that district.';

  return (
    <>
      {/* One filter row above everything it scopes */}
      <div className="sticky top-0 z-30 border-b border-line bg-page/95 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-2 px-4 py-2 sm:px-6"
          title={`${scopePrefix ? `${scopePrefix} · ` : ''}${level.label} (${level.grades.join(', ')}) · ${scope}`}>
          {showLevels && (
            <>
              <div className="hidden gap-0.5 rounded-lg bg-[var(--line)] p-0.5 lg:flex" role="radiogroup" aria-label="School level">
                {meta.levels.map((l, i) => (
                  <button key={l.key} type="button" role="radio" aria-checked={filters.level === i}
                    onClick={() => pickLevel(i)}
                    className={`rounded-md px-3 py-1 text-sm ${filters.level === i
                      ? 'bg-surface font-medium text-ink shadow-sm' : 'text-ink2 hover:text-ink'}`}>
                    {l.label}
                  </button>
                ))}
              </div>
              <select aria-label="School level" value={filters.level} className="h-8 px-2 text-sm lg:hidden"
                onChange={(e) => pickLevel(Number(e.target.value))}>
                {meta.levels.map((l, i) => <option key={l.key} value={i}>{l.label}</option>)}
              </select>
            </>
          )}
          <select aria-label="District" value={filters.district} className="h-8 px-2 text-sm"
            onChange={(e) => setFilters((f) => ({ ...f, district: e.target.value, sector: '' }))}>
            <option value="">All districts</option>
            {districts.map((d) => <option key={d}>{d}</option>)}
          </select>
          {filters.district && (
            <select aria-label="Sector" value={filters.sector} className="h-8 px-2 text-sm"
              onChange={(e) => setFilters((f) => ({ ...f, sector: e.target.value }))}>
              <option value="">All sectors</option>
              {sectors.map((s) => <option key={s}>{s}</option>)}
            </select>
          )}
          {(filters.district || filters.sector) && (
            <button type="button" className="px-1 text-sm text-accent hover:underline"
              onClick={() => setFilters((f) => ({ ...f, district: '', sector: '' }))}>
              Clear
            </button>
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {controls}
            <button type="button" onClick={() => void printReport(reportFile)}
              title="Opens the print dialog: choose Save as PDF"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-surface px-3 text-sm text-ink2 hover:text-ink">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.75"
                strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 3v12M7 10l5 5 5-5M5 21h14" />
              </svg>
              Download PDF
            </button>
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-[1400px] space-y-4 px-4 py-4 sm:px-6">
        {/* Report heading, shown only on paper */}
        <div className="hidden border-b border-line pb-3 print:block">
          <h2 className="text-lg font-semibold text-ink">{level.label} ({level.grades.join(', ')}) · {scope}</h2>
          <p className="text-xs text-ink2">
            {reportScope} · Capacity {level.capacity} students per room · Source: {meta.source} · Printed {new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>
        <Tiles t={t} notes={notes} level={level} />

        {top?.(codes, filters)}

        {/* ---------------------------------------------------------------- what schools have */}
        <SectionTitle title="Students and rooms"
          sub={`${level.label} by ${areaLabel}${filters.district ? ` · ${filters.district} district` : ''}`} />
        <div className="print-cols-2 grid gap-4 lg:grid-cols-2">
          <Card title={`Students by ${areaLabel} and grade`}
            sub={`Largest first. ${pickHint}`} aside={<GradeLegend grades={level.grades} mode={mode} />}>
            <div className="print-expand max-h-[440px] overflow-y-auto px-2 pb-2">
              <StackedGradesByArea data={areaGrades} grades={level.grades} measure="students" mode={mode} areaLabel={areaLabel}
                onPick={pickArea} />
            </div>
          </Card>
          <Card title={`Students per room by ${areaLabel}`}
            sub={`Students ÷ rooms available. Red: more than the ${level.capacity} a room seats. Most crowded first. ${pickHint}`}>
            <div className="print-expand max-h-[440px] overflow-y-auto px-2 pb-2">
              <CrowdingByArea data={byArea} capacity={level.capacity} mode={mode} areaLabel={areaLabel} onPick={pickArea} />
            </div>
          </Card>
        </div>

        {/* ---------------------------------------------------------------- where classrooms are short */}
        <SectionTitle title="Where classrooms are short"
          sub={`Rooms available against rooms required at ${level.capacity} students per room`} />

        {shortageTop?.(codes, filters)}

        <div className="print-cols-3 grid gap-4 lg:grid-cols-3">
          <Card title="Schools on the map" sub="Click a school for its details. Colour shows the classroom gap." className="print-span-2 print-map flex min-h-[600px] flex-col lg:col-span-2">
            <div className="flex-1">
              <SchoolMap rows={rows} mode={mode} selected={selected} onSelect={setSelected} />
            </div>
          </Card>
          <div className="flex flex-col gap-4">
            <Card title="Schools by classroom gap" sub={`${fmt(t.schools)} schools in scope · same colours as the map`}>
              <div className="px-4 pb-2"><StatusSplit t={t} mode={mode} /></div>
              <div className="px-2 pb-2"><GapHistogram gaps={gaps} mode={mode} /></div>
            </Card>
            <Card title={`Classrooms short by ${areaLabel}`} sub={pickHint} className="flex-1">
              <div className="print-expand max-h-[300px] overflow-y-auto px-2 pb-2">
                <ShortageByArea data={byArea} mode={mode} areaLabel={areaLabel} onPick={pickArea} />
              </div>
            </Card>
          </div>
        </div>

        <div className="print-cols-3 grid gap-4 lg:grid-cols-3">
          <Card title={`Rooms available vs required by ${filters.district ? 'sector' : 'province'}`}
            sub={filters.district ? 'Sectors with the largest shortage first. Click a bar to filter.' : `Every district of each province, ${level.label.toLowerCase()}.`}>
            <div className="print-expand max-h-[320px] overflow-y-auto px-2 pb-3">
              <CompareBars data={compare} mode={mode} fullDay={level.fullDay} horizontal
                label={`Rooms available versus required by ${filters.district ? 'sector' : 'province'}`}
                onPick={filters.district ? pickArea : undefined} />
            </div>
          </Card>
          <Card title="Rooms available vs required, by grade" sub={notes.gradeChart}>
            <div className="px-2 pb-3"><GradeChart data={grades} mode={mode} fullDay={level.fullDay} /></div>
          </Card>
          <Card title={level.fullDay ? `Class groups without a room by ${areaLabel}` : `Double-shift share by ${areaLabel}`}
            sub={level.fullDay
              ? 'Full-day level: no double shift, so a class group that shares a room has no room of its own.'
              : 'Class groups that share their room with another group.'}>
            <div className="print-expand max-h-[320px] overflow-y-auto px-2 pb-2">
              <DoubleShiftByArea data={byArea} mode={mode} areaLabel={areaLabel} fullDay={level.fullDay} />
            </div>
          </Card>
        </div>

        <Card title="Schools" sub="Largest deficits first. Click a row for details; click a column to sort. The filters here only narrow this table.">
          <SchoolTable rows={rows} mode={mode} selected={selected} onSelect={setSelected} flagged={flagged}
            fullDay={level.fullDay} />
        </Card>

        {footer ? <footer className="space-y-1 pb-8 pt-2 text-xs text-muted">{footer(level.capacity)}</footer> : <div className="pb-4" />}
      </main>

      {selected !== null && !printing && (
        <SchoolPanel code={selected} data={data} mode={mode} onClose={closePanel} context={panelContext} />
      )}
    </>
  );
}
