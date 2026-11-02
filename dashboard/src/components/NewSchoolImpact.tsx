import type { ReactNode } from 'react';
import { fmt, fmtGap, pct, type Meta, type SchoolLevel } from '../data';
import { impact, type Impact, type PlannedOut } from '../newSchools';
import type { ProjectedYear } from '../projection';
import { dsName } from './Charts';

function Change({ before, after, better = 'down', format = fmt }: {
  before: number; after: number; better?: 'down' | 'up'; format?: (n: number) => string;
}) {
  const good = better === 'down' ? after < before : after > before;
  return (
    <span className="num whitespace-nowrap">
      {format(before)} <span className="text-accent">→</span>{' '}
      <span className={after === before ? 'text-ink2' : good ? 'font-semibold text-accent' : 'font-semibold text-[var(--deficit)]'}>
        {format(after)}
      </span>
    </span>
  );
}

/** Before → after: what the planned schools of one level change in the selected year. */
export default function NewSchoolImpact({ planned, before, after, level, year, meta, info }: {
  planned: PlannedOut[]; // the planned schools offering `level`
  before: ProjectedYear; // the same year without the planned schools
  after: ProjectedYear;
  level: number;
  year: number;
  meta: Meta;
  info: Map<number, SchoolLevel>;
}) {
  const lv = meta.levels[level];
  const rowOf = (py: ProjectedYear, c: number) => py.schools.find((r) => r.c === c && r.l === level);
  const ring = [...new Set(planned.flatMap((p) => p.ring[String(level)] ?? []))];
  const nearby = new Set([...ring, ...planned.map((p) => p.c)]);
  const districts = [...new Set(planned.map((p) => p.d))].sort();
  const inDistrict = (d: string) => new Set(after.schools.filter((r) => r.l === level && r.d === d).map((r) => r.c));
  const everyone = new Set(after.schools.filter((r) => r.l === level).map((r) => r.c));
  const areas: [string, Impact][] = [
    [`Within walking distance (${ring.length} school${ring.length === 1 ? '' : 's'} + the new)`, impact(before, after, level, nearby)],
    ...districts.map((d): [string, Impact] => [`${d} district`, impact(before, after, level, inDistrict(d))]),
    ['Rwanda', impact(before, after, level, everyone)],
  ];
  const share = (i: Impact, k: 0 | 1) => (i.classGroups[k] ? i.doubleShift[k] / i.classGroups[k] : 0);
  const ringRows = ring
    .map((c) => ({ c, b: rowOf(before, c), a: rowOf(after, c) }))
    .filter((x) => x.b && x.a)
    .sort((x, y) => x.b!.gap - y.b!.gap);

  const headline: ReactNode[] = planned.map((p) => {
    const k = p.levels.indexOf(level);
    const taken = rowOf(after, p.c)?.st ?? 0;
    return (
      <div key={p.c} className="text-sm">
        <span className="font-semibold text-ink">{p.n}</span>
        <span className="text-ink2"> · {lv.label} · {p.classrooms[k]} rooms · opens {p.opening} · {p.km} km</span>
        <div className="text-xs text-muted">
          {year < p.opening
            ? `Opens in ${p.opening} — nothing changes before.`
            : taken
              ? `${fmt(taken)} students in ${year}: the extra students of the crowded schools nearby, and its own cohorts moving up.`
              : `No ${lv.label.toLowerCase()} school within ${p.km} km on foot is short of rooms in ${year}, so nothing changes.`}
        </div>
        {p.snap_km > p.km && (
          <div className="text-xs text-[var(--deficit)]">
            This point is {p.snap_km.toFixed(1)} km from the nearest mapped path, so no school can be reached on foot. Move it closer to a road or path.
          </div>
        )}
        {!p.on_main_network && (
          <div className="text-xs text-[var(--deficit)]">
            This point is on a path not connected to the main network. Nearby schools may be reachable in reality; move it onto a connected road or path.
          </div>
        )}
        {(p.unreachable[String(level)] ?? 0) > 0 && (
          <div className="text-xs text-muted">
            {p.unreachable[String(level)]} {p.unreachable[String(level)] === 1 ? 'school nearby has' : 'schools nearby have'} no walking route on the map and {p.unreachable[String(level)] === 1 ? 'is' : 'are'} not counted.
          </div>
        )}
      </div>
    );
  });

  return (
    <div className="px-4 pb-4">
      <div className="space-y-1.5">{headline}</div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th className="px-2 py-1.5 text-left font-medium">{year}</th>
              <th className="px-2 py-1.5 text-right font-medium">Classrooms short</th>
              <th className="px-2 py-1.5 text-right font-medium">Schools in deficit</th>
              <th className="px-2 py-1.5 text-right font-medium">{dsName(lv.fullDay)}</th>
            </tr>
          </thead>
          <tbody>
            {areas.map(([name, i]) => (
              <tr key={name} className="border-b border-line">
                <td className="px-2 py-1.5 text-ink">{name}</td>
                <td className="px-2 py-1.5 text-right"><Change before={i.short[0]} after={i.short[1]} /></td>
                <td className="px-2 py-1.5 text-right"><Change before={i.deficitSchools[0]} after={i.deficitSchools[1]} /></td>
                <td className="px-2 py-1.5 text-right">
                  <Change before={share(i, 0)} after={share(i, 1)} format={(v) => pct(v * 1000, 1000)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {ringRows.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Schools within walking distance · classroom gap</h3>
          <ul className="mt-1 grid gap-x-6 sm:grid-cols-2">
            {ringRows.map(({ c, b, a }) => (
              <li key={c} className="flex justify-between gap-3 border-b border-line py-1 text-sm">
                <span className="truncate text-ink">{info.get(c)?.n ?? c}</span>
                <Change before={b!.gap} after={a!.gap} better="up" format={fmtGap} />
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="mt-2 text-xs text-muted">
        Before = the same intake plan without the new schools. The rest of the page shows the projection with them; switch
        the plan Off to see it without.
      </p>
    </div>
  );
}
