/**
 * Illustrations for the landing page's placeholders: Rwanda's real district outlines with decorative shading, in the
 * dashboard's palette (theme.tsx) and light / dark mode. They show no figures — the data is behind sign-in.
 */
import type { ReactNode } from 'react';
import { COLORS, GAP_CLASSES, GRADE_RAMP, useTheme, type Mode } from '../theme';
import { DISTRICTS, DOTS, MAP_HEIGHT, MAP_WIDTH } from './rwandaMap';

/** Stable pseudo-random number in [0, 1) for a name, so the shading does not change between visits. */
function shade(name: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < name.length; i++) h = Math.imul(h ^ name.charCodeAt(i), 16777619);
  return ((h >>> 0) % 1000) / 1000;
}

function RwandaSvg({ fill, stroke, label, children }: {
  fill: (name: string) => string; stroke: string; label: string; children?: ReactNode;
}) {
  return (
    // Right-aligned: the caption sits bottom-left
    <svg className="lp-geo-svg" viewBox={`-4 -4 ${MAP_WIDTH + 8} ${MAP_HEIGHT + 8}`} preserveAspectRatio="xMaxYMid meet"
      role="img" aria-label={label}>
      {DISTRICTS.map((d) => (
        <path key={d.name} d={d.d} fill={fill(d.name)} stroke={stroke} strokeWidth={1.4} strokeLinejoin="round" />
      ))}
      {children}
    </svg>
  );
}

/* ------------------------------------------------------------------ 01 population: the dashboard's blue ramp */
export function PopulationIllustration() {
  const { mode } = useTheme();
  const ramp = GRADE_RAMP[mode].slice(0, 5);
  const c = COLORS[mode];
  return (
    <RwandaSvg label="Illustration: Rwanda's districts shaded in blues" stroke={c.surface}
      fill={(n) => ramp[Math.floor(shade(n, 1) * ramp.length)]}>
      {DISTRICTS.map((d) => (
        <circle key={d.name} cx={d.cx} cy={d.cy} r={4 + shade(d.name, 2) * 9} fill={c.ink} fillOpacity={0.25}
          stroke={c.surface} strokeWidth={1} />
      ))}
    </RwandaSvg>
  );
}

/* ------------------------------------------------------------------ 02 capacity and access */
export function CapacityIllustration() {
  const { mode } = useTheme();
  const c = COLORS[mode];
  return (
    <RwandaSvg label="Illustration: points spread over Rwanda with circles around them" fill={() => c.surface}
      stroke={c.axis}>
      {DOTS.map(([x, y], i) => (
        <circle key={`a${i}`} cx={x} cy={y} r={15} fill={c.available} fillOpacity={0.1} />
      ))}
      {DOTS.map(([x, y], i) => (
        <circle key={`d${i}`} cx={x} cy={y} r={3} fill={i % 7 === 0 ? c.required : c.available} stroke={c.surface}
          strokeWidth={1} />
      ))}
    </RwandaSvg>
  );
}

/* ------------------------------------------------------------------ 03 demand: the dashboard's gap colours */
/** Low, Moderate, High, Very High: exact fit grey, then the deficit classes of the map (1–3, 4–9, 10+ short). */
export function demandColors(mode: Mode): string[] {
  return ['Exact fit', '1–3 short', '4–9 short', '10+ short'].map((label) => GAP_CLASSES.find((g) => g.label === label)![mode]);
}

export function DemandIllustration() {
  const { mode } = useTheme();
  const colors = demandColors(mode);
  return (
    <RwandaSvg label="Illustration: Rwanda's districts in four demand colours" stroke={COLORS[mode].surface}
      fill={(n) => colors[Math.min(3, Math.floor(shade(n, 3) ** 1.4 * 4))]} />
  );
}

/* ------------------------------------------------------------------ 04 future demand */
/** Rooms available (flat) against rooms required (rising) over the landing page's years; no figures. */
export function FutureIllustration({ years, year }: { years: number[]; year: number }) {
  const { mode } = useTheme();
  const c = COLORS[mode];
  const W = 600, H = 200, pad = { l: 16, r: 16, t: 18, b: 30 };
  const x = (i: number) => pad.l + (i * (W - pad.l - pad.r)) / (years.length - 1);
  const y = (v: number) => pad.t + (1 - v) * (H - pad.t - pad.b); // v in [0, 1]
  const capacity = years.map(() => 0.42);
  const demand = years.map((_, i) => 0.3 + i * 0.2);
  const line = (vs: number[]) => vs.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  const k = Math.max(0, years.indexOf(year));
  // The shortage: where demand runs above capacity, up to the chosen year
  const top = demand.slice(0, k + 1).map((v, i) => Math.max(v, capacity[i]));
  const back = capacity.slice(0, k + 1).map((v, i) => `L${x(i)},${y(v)}`).reverse().join('');
  const area = `${line(top)}${back}Z`;

  return (
    <div className="lp-future">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Illustration: projected demand rising above current capacity by ${year}`}>
        {[0.25, 0.5, 0.75].map((v) => <line key={v} x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke={c.grid} />)}
        {k > 0 && <path d={area} fill={c.deficit} fillOpacity={0.2} />}
        <path d={line(capacity)} fill="none" stroke={c.available} strokeWidth={3} strokeLinecap="round" />
        <path d={line(demand)} fill="none" stroke={c.required} strokeWidth={3} strokeLinecap="round" />
        <line x1={x(k)} x2={x(k)} y1={pad.t - 6} y2={H - pad.b} stroke={c.muted} strokeDasharray="3 3" />
        <circle cx={x(k)} cy={y(capacity[k])} r={5} fill={c.surface} stroke={c.available} strokeWidth={2.5} />
        <circle cx={x(k)} cy={y(demand[k])} r={5} fill={c.surface} stroke={c.required} strokeWidth={2.5} />
        {years.map((yr, i) => (
          <text key={yr} x={x(i)} y={H - 8} textAnchor={i === 0 ? 'start' : i === years.length - 1 ? 'end' : 'middle'}
            fontSize={12} fontWeight={i === k ? 700 : 500} fill={i === k ? c.ink : c.muted}>{yr}</text>
        ))}
      </svg>
    </div>
  );
}
