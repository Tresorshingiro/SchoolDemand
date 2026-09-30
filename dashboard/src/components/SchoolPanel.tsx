import { Fragment, useEffect, useMemo } from 'react';
import { fmt, fmtGap, statusOf, type Dataset } from '../data';
import { STATUS_COLORS, type Mode } from '../theme';

interface Props {
  code: number;
  data: Dataset;
  mode: Mode;
  onClose: () => void;
  /** Optional line under the school name, e.g. the projected year. */
  context?: string;
}

function GapCell({ gap, mode }: { gap: number; mode: Mode }) {
  const status = statusOf(gap);
  return (
    <td className="num whitespace-nowrap px-2 py-1.5 text-right font-semibold">
      <span className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: STATUS_COLORS[mode][status] }} aria-hidden />
      {fmtGap(gap)}
      <span className="sr-only"> ({status})</span>
    </td>
  );
}

/** Slide-over with one school's figures for every level, grade detail and data-quality flags. */
export default function SchoolPanel({ code, data, mode, onClose, context }: Props) {
  const levels = useMemo(() => data.schools.filter((r) => r.c === code).sort((a, b) => a.l - b.l), [data, code]);
  const grades = useMemo(() => data.grades.filter((g) => g[0] === code).sort((a, b) => a[1] - b[1]), [data, code]);
  // Combinations of each grade (Upper Secondary, TVET, Professional Education), most students first
  const combos = useMemo(() => {
    const m = new Map<number, [string, number, number][]>();
    for (const [c, gi, name, st, g] of data.combos) {
      if (c !== code) continue;
      m.set(gi, [...(m.get(gi) ?? []), [name, st, g]]);
    }
    for (const list of m.values()) list.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return m;
  }, [data, code]);
  const issues = data.meta.schoolIssues[String(code)] ?? [];
  const levelOf = (grade: string) => data.meta.levels.find((l) => l.grades.includes(grade));
  const hasFullDay = levels.some((r) => data.meta.levels[r.l].fullDay);
  const info = levels[0];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!info) return null;

  return (
    <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-line bg-surface shadow-2xl"
      role="dialog" aria-label={`Details for ${info.n}`}>
      <header className="flex items-start gap-3 border-b border-line p-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-ink">{info.n}</h2>
          <p className="text-xs text-muted">
            Code {info.c} · {info.d} district · {info.s} sector
            {info.x === null ? ' · no valid coordinates' : ''}
          </p>
          {context && <p className="mt-1 text-xs font-medium text-accent">{context}</p>}
        </div>
        <button type="button" onClick={onClose} aria-label="Close details"
          className="rounded-md px-2 py-1 text-lg leading-none text-muted hover:text-ink">×</button>
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto p-4">
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">By level</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th className="px-2 py-1.5 font-medium">Level</th>
                <th className="px-2 py-1.5 text-right font-medium">Students</th>
                <th className="px-2 py-1.5 text-right font-medium">Groups</th>
                <th className="px-2 py-1.5 text-right font-medium">Avail.</th>
                <th className="px-2 py-1.5 text-right font-medium">Req.</th>
                <th className="px-2 py-1.5 text-right font-medium">Gap</th>
              </tr>
            </thead>
            <tbody>
              {levels.map((r) => (
                <tr key={r.l} className="border-b border-line">
                  <td className="px-2 py-1.5 text-ink">{data.meta.levels[r.l].label}</td>
                  <td className="num px-2 py-1.5 text-right">{fmt(r.st)}</td>
                  <td className="num px-2 py-1.5 text-right">{fmt(r.g)}</td>
                  <td className="num px-2 py-1.5 text-right">{fmt(r.a)}</td>
                  <td className="num px-2 py-1.5 text-right">{fmt(r.r)}</td>
                  <GapCell gap={r.gap} mode={mode} />
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">By grade</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th className="px-2 py-1.5 font-medium">Grade</th>
                <th className="px-2 py-1.5 text-right font-medium">Students</th>
                <th className="px-2 py-1.5 text-right font-medium">Groups</th>
                <th className="px-2 py-1.5 text-right font-medium">{hasFullDay ? 'Double shift / no room' : 'Double shift'}</th>
                <th className="px-2 py-1.5 text-right font-medium">Avail.</th>
                <th className="px-2 py-1.5 text-right font-medium">Req.</th>
                <th className="px-2 py-1.5 text-right font-medium">Gap</th>
              </tr>
            </thead>
            <tbody>
              {grades.map(([, gi, st, cg, ds, av, rq, gap]) => {
                const sub = combos.get(gi) ?? [];
                const level = levelOf(data.meta.grades[gi]);
                return (
                  <Fragment key={gi}>
                    <tr className={sub.length ? '' : 'border-b border-line'}>
                      <td className="px-2 py-1.5 text-ink">{data.meta.grades[gi]}</td>
                      <td className="num px-2 py-1.5 text-right">{fmt(st)}</td>
                      <td className="num px-2 py-1.5 text-right">{fmt(cg)}</td>
                      <td className="num px-2 py-1.5 text-right">{fmt(ds)}</td>
                      <td className="num px-2 py-1.5 text-right">{fmt(av)}</td>
                      <td className="num px-2 py-1.5 text-right">{fmt(rq)}</td>
                      <GapCell gap={gap} mode={mode} />
                    </tr>
                    {sub.length > 0 && (
                      <tr className="border-b border-line">
                        <td colSpan={7} className="px-2 pb-2">
                          <ul className="flex flex-wrap gap-1.5" aria-label={`${data.meta.grades[gi]} combinations`}>
                            {sub.map(([name, cst, ccg]) => {
                              const need = level?.fullDay ? Math.max(ccg, Math.ceil(cst / level.capacity)) : null;
                              return (
                                <li key={name} className="rounded-md border border-line px-2 py-1 text-xs">
                                  <span className="font-medium text-ink">{name}</span>
                                  <span className="num ml-1.5 text-ink2">
                                    {fmt(cst)} st · {fmt(ccg)} {ccg === 1 ? 'group' : 'groups'}
                                    {need !== null && <> · needs {fmt(need)} {need === 1 ? 'room' : 'rooms'}</>}
                                  </span>
                                </li>
                              );
                            })}
                          </ul>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">
            {context
              ? "Avail. = the school's rooms shared out to each grade this year."
              : 'A room shared by two grades counts in each grade, but once in the level total above.'}
            {hasFullDay && ' Secondary, TVET and Professional Education study full day: no double shift, so that column counts class groups without a room, and every class group needs its own room (combinations never share).'}
            {combos.size > 0 && (context
              ? ' Boxes: each combination; cohorts keep their combination, new entrants follow the 2026 mix.'
              : ' Boxes: each combination.')}
          </p>
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Data quality</h3>
          {issues.length ? (
            <ul className="space-y-1 text-sm text-ink2">
              {issues.map(([issue, n]) => (
                <li key={issue} className="flex justify-between gap-3">
                  <span>{issue}</span>
                  <span className="num text-muted">{fmt(n)} row{n === 1 ? '' : 's'}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No issues flagged for this school.</p>
          )}
        </section>
      </div>
    </aside>
  );
}
