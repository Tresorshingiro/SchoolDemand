import { useEffect, useRef, useState } from 'react';
import { fmt, pct } from '../data';
import type { Mode } from '../theme';
import { EntrantsChart } from './Charts';
import {
  intakeFromCsv, intakeToCsv, sameIntake,
  type Intake, type ProjectionBase, type Scenario, type ScenarioSummary,
} from '../projection';

/** Number cell that commits on Enter or blur, so the projection is not recomputed on every keystroke. */
function IntakeCell({ value, defaults, label, onCommit }: { value: number; defaults: number; label: string; onCommit: (v: number) => void }) {
  const [text, setText] = useState(fmt(value));
  useEffect(() => setText(fmt(value)), [value]);
  const commit = () => {
    const v = Number(text.replace(/[,\s]/g, ''));
    if (Number.isFinite(v) && v >= 0 && text.trim() !== '') {
      onCommit(Math.round(v));
      setText(fmt(Math.round(v)));
    } else setText(fmt(value));
  };
  const edited = value !== defaults;
  return (
    <td className="px-1 py-0.5 text-right align-top">
      <input
        inputMode="numeric" aria-label={label} value={text}
        onChange={(e) => setText(e.target.value)}
        onFocus={(e) => e.target.select()}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
          if (e.key === 'Escape') setText(fmt(value));
        }}
        className={`num h-7 w-20 px-1.5 text-right text-sm ${edited ? 'font-semibold text-accent' : ''}`}
      />
      {edited && <div className="num text-[10px] leading-3 text-muted">default {fmt(defaults)}</div>}
    </td>
  );
}

/** Saved plans (scenarios in the database), handled by the projection page. */
export interface ScenarioControls {
  list: ScenarioSummary[];
  active: Scenario | null;
  dirty: boolean; // the plan on screen differs from the saved one
  busy: boolean;
  message: string | null;
  defaultLabel: string;
  onOpen: (id: number | null) => void;
  onSave: () => void;
  onSaveAs: (name: string) => void;
  onDelete: () => void;
}

/** Open / save / save as / delete a shared plan. */
function ScenarioBar({ s }: { s: ScenarioControls }) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState('');
  const btn = 'rounded-md border border-line px-3 py-1 text-ink2 hover:text-ink disabled:opacity-50 disabled:hover:text-ink2';
  const submit = () => {
    if (!name.trim()) return;
    s.onSaveAs(name.trim());
    setNaming(false);
    setName('');
  };
  return (
    <div className="mb-3 rounded-md border border-line bg-[var(--line)] px-3 py-2 print:hidden">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-2 text-ink2">
          Plan
          <select aria-label="Open a saved plan" className="h-8 max-w-[260px] px-2 text-sm font-medium text-ink" disabled={s.busy}
            value={s.active?.id ?? ''} onChange={(e) => s.onOpen(e.target.value === '' ? null : Number(e.target.value))}>
            <option value="">{s.defaultLabel} (default)</option>
            {s.list.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </label>
        {s.dirty && <span className="text-xs font-medium text-accent">unsaved changes</span>}
        <button type="button" className={btn} disabled={s.busy || !s.active || !s.dirty} onClick={s.onSave}
          title={s.active ? `Save the changes to "${s.active.name}"` : 'Open a saved plan to save changes to it'}>
          Save
        </button>
        {naming ? (
          <span className="flex items-center gap-1">
            <input autoFocus value={name} maxLength={100} placeholder="Name of the new plan" aria-label="Name of the new plan"
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submit();
                if (e.key === 'Escape') setNaming(false);
              }}
              className="h-8 w-56 px-2 text-sm" />
            <button type="button" className={btn} disabled={s.busy || !name.trim()} onClick={submit}>Save</button>
            <button type="button" className="px-2 text-sm text-muted hover:text-ink" onClick={() => setNaming(false)}>Cancel</button>
          </span>
        ) : (
          <button type="button" className={btn} disabled={s.busy} onClick={() => setNaming(true)}>Save as new plan…</button>
        )}
        {s.active && (
          <button type="button" className="px-2 text-sm text-[var(--deficit)] hover:underline disabled:opacity-50" disabled={s.busy}
            onClick={s.onDelete}>
            Delete
          </button>
        )}
        <span className="ml-auto text-xs text-muted">Saved plans are shared with everyone who uses the dashboard.</span>
      </div>
      {s.message && <p className="mt-1.5 text-xs text-ink2" role="status">{s.message}</p>}
    </div>
  );
}

interface Props {
  base: ProjectionBase;
  intake: Intake;
  onChange: (next: Intake) => void;
  /** Entry grade whose intake is edited (N1 or P1). */
  grade: string;
  /** Students of the entry grade per district in the base year. */
  baseByDistrict: Map<string, number[]>;
  /** District picked in the page filter: show only its row. */
  district?: string;
  mode: Mode;
  /** Saved plans; without it the planner only edits the plan on screen. */
  scenarios?: ScenarioControls | null;
}

/** District x year table of new N1 students; drives the whole projection page. */
export default function IntakePlanner({ base, intake, onChange, grade, baseByDistrict, district, mode, scenarios }: Props) {
  const years = base.years.slice(1);
  const defaults = base.population[grade];
  const estimated = new Set(base.estimated[grade] ?? []);
  const allDistricts = Object.keys(defaults).sort();
  const districts = district && defaults[district] ? [district] : allDistricts;
  const isNisr = sameIntake(intake, base.population, grade);
  const fileRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);

  const setCell = (d: string, yi: number, v: number) => {
    if (intake[grade][d][yi] === v) return;
    onChange({ ...intake, [grade]: { ...intake[grade], [d]: intake[grade][d].map((x, i) => (i === yi ? v : x)) } });
  };

  const reset = () => {
    onChange({ ...intake, [grade]: Object.fromEntries(Object.entries(defaults).map(([d, v]) => [d, [...v]])) });
    setMessage(null);
  };

  const download = () => {
    const blob = new Blob([intakeToCsv(base, intake)], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'intake_plan.csv';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  const upload = async (file: File) => {
    try {
      const { intake: next, unknown, updated, grades } = intakeFromCsv(base, await file.text(), intake, grade);
      onChange(next);
      setMessage(`Loaded ${grades.join(' and ')} for ${updated} district${updated === 1 ? '' : 's'} from ${file.name}.` +
        (unknown.length ? ` Not recognised: ${unknown.join(', ')}.` : ''));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    }
  };

  const total = (yi: number) => districts.reduce((s, d) => s + (intake[grade][d]?.[yi] ?? 0), 0);
  const baseTotal = districts.reduce((s, d) => s + (baseByDistrict.get(d)?.[0] ?? 0), 0);

  return (
    <div className="px-4 pb-4">
      {scenarios && <ScenarioBar s={scenarios} />}
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm print:hidden">
        <button type="button" onClick={reset} disabled={isNisr}
          className="rounded-md border border-line px-3 py-1 text-ink2 hover:text-ink disabled:opacity-50 disabled:hover:text-ink2">
          Reset {grade} to {base.defaultLabel}
        </button>
        <button type="button" onClick={download} className="rounded-md border border-line px-3 py-1 text-ink2 hover:text-ink">
          Download CSV
        </button>
        <button type="button" onClick={() => fileRef.current?.click()} className="rounded-md border border-line px-3 py-1 text-ink2 hover:text-ink">
          Upload CSV
        </button>
        <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
            e.target.value = '';
          }} />
        <span className="ml-auto text-xs text-muted">Press Enter or leave a cell to recalculate. Save the plan to share it.</span>
      </div>
      {message && <p className="mb-2 text-xs text-ink2" role="status">{message}</p>}

      <div className="print-cols-5 grid gap-4 lg:grid-cols-5">
        <div className="print-expand max-h-[330px] overflow-auto rounded-md border border-line print-span-3 lg:col-span-3">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="border-b border-line text-xs text-muted">
                <th className="px-2 py-1.5 text-left font-medium">District</th>
                <th className="px-2 py-1.5 text-right font-medium">{grade} {base.baseYear}*</th>
                {years.map((y) => (
                  <th key={y} className="px-2 py-1.5 text-right font-medium">
                    {y}{estimated.has(y) ? ' (est.)' : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {districts.map((d) => (
                <tr key={d} className="border-b border-line">
                  <td className="px-2 py-1 text-ink">{d}</td>
                  <td className="num px-2 py-1 text-right text-ink2">{fmt(baseByDistrict.get(d)?.[0] ?? 0)}</td>
                  {years.map((y, yi) => (
                    <IntakeCell key={y} value={intake[grade][d]?.[yi] ?? 0} defaults={defaults[d][yi]} label={`${d} new ${grade} ${y}`}
                      onCommit={(v) => setCell(d, yi, v)} />
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot className="sticky bottom-0 bg-surface">
              <tr className="border-t border-line font-semibold text-ink">
                <td className="px-2 py-1.5">{districts.length === 1 ? 'Total' : 'Rwanda'}</td>
                <td className="num px-2 py-1.5 text-right">{fmt(baseTotal)}</td>
                {years.map((y, yi) => <td key={y} className="num px-2 py-1.5 text-right">{fmt(total(yi))}</td>)}
              </tr>
            </tfoot>
          </table>
        </div>
        <div className="print-span-2 lg:col-span-2">
          <div className="text-xs font-medium text-ink2">
            New {grade} per year · {districts.length === 1 ? district : 'Rwanda'}
          </div>
          <EntrantsChart grade={grade} years={base.years} baseYear={base.baseYear} base={baseTotal}
            plan={years.map((_, yi) => total(yi))}
            defaults={years.map((_, yi) => districts.reduce((s, d) => s + (defaults[d]?.[yi] ?? 0), 0))}
            defaultLabel={base.defaultLabel} mode={mode} />
        </div>
      </div>
    </div>
  );
}

interface FedProps {
  base: ProjectionBase;
  /** Entry grade fed by the leavers of `source` (S1 from P6, S4 / L3 / Y1 from S3). */
  grade: string;
  source: string;
  /** Every entry grade fed by the same source (S4, L3, Y1) — for the 2026 mix. */
  targets: string[];
  /** Leavers stay in their own school (N3 -> P1); schools without the grade share theirs by sector. */
  sameSchool?: boolean;
  /** Students per district and year for each grade in `targets` (index 0 = base year). */
  byDistrict: Record<string, Map<string, number[]>>;
  district?: string;
  mode: Mode;
}

/** Read-only district x year table of the new students of an entry grade fed by an earlier grade. */
export function FedEntrants({ base, grade, source, targets, sameSchool = false, byDistrict, district, mode }: FedProps) {
  const rows = byDistrict[grade];
  const all = [...rows.keys()].sort();
  const districts = district && rows.has(district) ? [district] : all;
  const split = targets.length > 1;
  const mix = (d: string) => {
    const tot = targets.reduce((s, t) => s + (byDistrict[t].get(d)?.[0] ?? 0), 0);
    return pct(rows.get(d)?.[0] ?? 0, tot);
  };
  const sum = (yi: number) => districts.reduce((s, d) => s + (rows.get(d)?.[yi] ?? 0), 0);
  return (
    <div className="px-4 pb-4">
      <div className="print-cols-5 grid gap-4 lg:grid-cols-5">
        <div className="print-expand max-h-[330px] overflow-auto rounded-md border border-line print-span-3 lg:col-span-3">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="border-b border-line text-xs text-muted">
                <th className="px-2 py-1.5 text-left font-medium">District</th>
                {split && <th className="px-2 py-1.5 text-right font-medium">Share of {source}</th>}
                {base.years.map((y, yi) => (
                  <th key={y} className="px-2 py-1.5 text-right font-medium">{yi === 0 ? `${grade} ${y}*` : y}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {districts.map((d) => (
                <tr key={d} className="border-b border-line">
                  <td className="px-2 py-1 text-ink">{d}</td>
                  {split && <td className="num px-2 py-1 text-right text-ink2">{mix(d)}</td>}
                  {base.years.map((y, yi) => (
                    <td key={y} className={`num px-2 py-1 text-right ${yi === 0 ? 'text-ink2' : 'text-ink'}`}>{fmt(rows.get(d)?.[yi] ?? 0)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot className="sticky bottom-0 bg-surface">
              <tr className="border-t border-line font-semibold text-ink">
                <td className="px-2 py-1.5">{districts.length === 1 ? 'Total' : 'Rwanda'}</td>
                {split && <td />}
                {base.years.map((y, yi) => <td key={y} className="num px-2 py-1.5 text-right">{fmt(sum(yi))}</td>)}
              </tr>
            </tfoot>
          </table>
        </div>
        <div className="print-span-2 lg:col-span-2">
          <div className="text-xs font-medium text-ink2">
            New {grade} per year · {districts.length === 1 ? district : 'Rwanda'}
          </div>
          <EntrantsChart grade={grade} years={base.years} baseYear={base.baseYear} base={sum(0)}
            plan={base.years.slice(1).map((_, yi) => sum(yi + 1))} mode={mode} />
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">
        * {grade} students enrolled in {base.baseYear}; the year columns are new {grade} students.{' '}
        {districts.length === 1 && <>Showing {district} only — clear the district filter to see all districts. </>}
        {sameSchool ? (
          <>
            New {grade} = the {source} of the year before: each school's {source} moves up to its own {grade}; the {source} of
            schools without {grade} (stand-alone nurseries) is shared to the primary schools of their sector in proportion to
            their {grade} in {base.baseYear}. Children who did not attend pre-primary are not added. It follows from the N1
            plan and the cohorts, so it is not edited here.
          </>
        ) : (
          <>
            New {grade} = every {source} student of the district the year before
            {split ? <>, times the district's {base.baseYear} share of {targets.join(' / ')} students that are in {grade}</> : ''}.
            Shared to the district's schools in proportion to their {grade} in {base.baseYear}. It follows from the N1 plan and
            the cohorts, so it is not edited here.
          </>
        )}
      </p>
    </div>
  );
}
