import { useMemo } from 'react';
import EChart from './EChart';
import { fmt, fmtGap, pct, type AreaGrades, type GradeTotals, type Totals } from '../data';
import type { YearTotals } from '../projection';
import { COLORS, GAP_CLASSES, STATUS_COLORS, gradeColors, type Mode } from '../theme';

const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';

function tooltipBase(mode: Mode) {
  const c = COLORS[mode];
  return {
    trigger: 'axis' as const,
    axisPointer: { type: 'shadow' as const, shadowStyle: { color: mode === 'dark' ? 'rgba(255,255,255,0.06)' : 'rgba(11,11,11,0.05)' } },
    backgroundColor: c.surface,
    borderColor: c.axis,
    borderWidth: 1,
    textStyle: { color: c.ink, fontFamily: FONT, fontSize: 12 },
    extraCssText: 'box-shadow: 0 4px 14px rgba(0,0,0,0.12); border-radius: 6px;',
  };
}

function axisStyle(mode: Mode) {
  const c = COLORS[mode];
  return {
    axisLine: { lineStyle: { color: c.axis } },
    axisTick: { show: false },
    axisLabel: { color: c.muted, fontFamily: FONT, fontSize: 11 },
    splitLine: { lineStyle: { color: c.grid, type: 'solid' as const } },
  };
}

const row = (color: string, name: string, value: string) =>
  `<div style="display:flex;gap:10px;justify-content:space-between;align-items:center">` +
  `<span><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-right:6px"></span>${name}</span>` +
  `<b style="font-variant-numeric:tabular-nums">${value}</b></div>`;

/* ------------------------------------------------------------------ shortage by area */

export function ShortageByArea({
  data, mode, areaLabel, onPick,
}: {
  data: [string, Totals][];
  mode: Mode;
  areaLabel: string;
  onPick?: (name: string) => void;
}) {
  const option = useMemo(() => {
    const c = COLORS[mode];
    const sorted = [...data].sort((a, b) => a[1].short - b[1].short); // largest ends up on top
    return {
      animationDuration: 300,
      grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const [name, t] = sorted[ps[0].dataIndex];
          return `<div style="font-weight:600;margin-bottom:4px">${name}</div>` +
            row(c.deficit, 'Classrooms short', fmt(t.short)) +
            `<div style="color:${c.ink2};margin-top:4px">${fmt(t.deficitSchools)} of ${fmt(t.schools)} schools in deficit</div>` +
            (onPick ? `<div style="color:${c.muted};margin-top:2px">Click to filter</div>` : '');
        },
      },
      xAxis: { type: 'value', ...axisStyle(mode), axisLine: { show: false } },
      yAxis: {
        type: 'category', data: sorted.map(([n]) => n), ...axisStyle(mode),
        axisLabel: { ...axisStyle(mode).axisLabel, color: c.ink2 },
      },
      series: [{
        type: 'bar', name: 'Classrooms short', data: sorted.map(([, t]) => t.short),
        barMaxWidth: 14, barCategoryGap: '30%',
        itemStyle: { color: c.deficit, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', color: c.ink2, fontSize: 11, fontFamily: FONT, formatter: (p: { value: number }) => fmt(p.value) },
        cursor: onPick ? 'pointer' : 'default',
      }],
    };
  }, [data, mode, onPick]);

  const height = Math.max(220, data.length * 22 + 24);
  return <EChart option={option} height={height} onClick={onPick} label={`Classrooms short by ${areaLabel}`} />;
}

/* ------------------------------------------------------------------ available vs required by grade */

/** Name of the `doubleShift` measure: full-day levels have no double shift, it counts class groups without a room. */
export const dsName = (fullDay: boolean) => (fullDay ? 'Class groups without a room' : 'Double-shift sessions');

/** One category of an available-vs-required comparison (a grade, a province, a year...). */
export interface CompareItem {
  name: string;
  available: number;
  required: number;
  short: number;
  doubleShift: number;
  students: number;
  classGroups: number;
}

/** Rooms available vs rooms required, side by side per category. Horizontal for long area names. */
export function CompareBars({ data, mode, fullDay = false, horizontal = false, height, label, onPick, highlight }: {
  data: CompareItem[];
  mode: Mode;
  fullDay?: boolean;
  horizontal?: boolean;
  height?: number;
  label: string;
  onPick?: (name: string) => void;
  /** Category drawn at full strength; the others are dimmed (e.g. the selected year). */
  highlight?: string;
}) {
  const option = useMemo(() => {
    const c = COLORS[mode];
    const items = horizontal ? [...data].reverse() : data; // horizontal: first item on top
    const radius = horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0];
    const bars = (key: 'available' | 'required', color: string) => items.map((d) => ({
      value: d[key],
      itemStyle: { color, borderRadius: radius, opacity: highlight === undefined || d.name === highlight ? 1 : 0.45 },
    }));
    const cat = { type: 'category', data: items.map((d) => d.name), ...axisStyle(mode),
      axisLabel: { ...axisStyle(mode).axisLabel, color: c.ink2 } };
    const val = { type: 'value', ...axisStyle(mode), axisLine: { show: false }, ...(horizontal ? { splitNumber: 3 } : {}) };
    return {
      animationDuration: 300,
      grid: { left: 8, right: horizontal ? 16 : 8, top: 36, bottom: 8, containLabel: true },
      legend: {
        top: 0, left: 0, itemWidth: 10, itemHeight: 10, icon: 'roundRect',
        textStyle: { color: c.ink2, fontFamily: FONT, fontSize: 12 },
      },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const g = items[ps[0].dataIndex];
          return `<div style="font-weight:600;margin-bottom:4px">${g.name}</div>` +
            row(c.available, 'Rooms available', fmt(g.available)) +
            row(c.required, 'Rooms required', fmt(g.required)) +
            `<div style="border-top:1px solid ${c.grid};margin:4px 0"></div>` +
            row(c.deficit, 'Classrooms short', fmt(g.short)) +
            row(c.doubleShift, dsName(fullDay), fmt(g.doubleShift)) +
            `<div style="color:${c.ink2};margin-top:4px">${fmt(g.students)} students · ${fmt(g.classGroups)} class groups</div>` +
            (onPick ? `<div style="color:${c.muted};margin-top:2px">Click to select</div>` : '');
        },
      },
      xAxis: horizontal ? val : cat,
      yAxis: horizontal ? cat : val,
      series: [
        { type: 'bar', name: 'Rooms available', data: bars('available', c.available), barMaxWidth: 16, barGap: '15%',
          itemStyle: { color: c.available }, cursor: onPick ? 'pointer' : 'default' },
        { type: 'bar', name: 'Rooms required', data: bars('required', c.required), barMaxWidth: 16,
          itemStyle: { color: c.required }, cursor: onPick ? 'pointer' : 'default' },
      ],
    };
  }, [data, mode, fullDay, horizontal, onPick, highlight]);
  const h = height ?? (horizontal ? Math.max(200, data.length * 40 + 48) : 280);
  return <EChart option={option} height={h} onClick={onPick} label={label} />;
}

export function GradeChart({ data, mode, fullDay = false }: { data: GradeTotals[]; mode: Mode; fullDay?: boolean }) {
  const items = useMemo(() => data.map((g) => ({ ...g, name: g.grade })), [data]);
  return <CompareBars data={items} mode={mode} fullDay={fullDay} label="Rooms available versus rooms required by grade" />;
}

/* ------------------------------------------------------------------ grade legend (HTML, stays put while a chart scrolls) */

export function GradeLegend({ grades, mode }: { grades: string[]; mode: Mode }) {
  const colors = gradeColors(grades.length, mode);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink2" aria-hidden="true">
      {grades.map((g, k) => (
        <span key={g} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: colors[k] }} />
          {g}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ students / class groups by area, stacked by grade */

export function StackedGradesByArea({ data, grades, measure, mode, areaLabel, onPick, labelOf, pickText = 'Click to filter' }: {
  data: AreaGrades[];
  grades: string[];
  measure: 'students' | 'classGroups';
  mode: Mode;
  areaLabel: string;
  onPick?: (name: string) => void;
  /** Display name and a second tooltip line for an area key (e.g. a school code -> name, district · sector). */
  labelOf?: (area: string) => { name: string; sub?: string };
  pickText?: string;
}) {
  const noun = measure === 'students' ? 'students' : 'class groups';
  const option = useMemo(() => {
    const c = COLORS[mode];
    const colors = gradeColors(grades.length, mode);
    const total = (a: AreaGrades) => a[measure].reduce((s, v) => s + v, 0);
    const sorted = [...data].sort((a, b) => total(a) - total(b)); // largest ends up on top
    return {
      animationDuration: 300,
      grid: { left: 8, right: 64, top: 4, bottom: 8, containLabel: true },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const a = sorted[ps[0].dataIndex];
          const l = labelOf?.(a.area);
          return `<div style="font-weight:600">${l?.name ?? a.area}</div>` +
            (l?.sub ? `<div style="color:${c.ink2};margin-bottom:4px">${l.sub}</div>` : '<div style="margin-bottom:4px"></div>') +
            [...grades.keys()].reverse().map((k) => row(colors[k], grades[k], fmt(a[measure][k]))).join('') +
            `<div style="border-top:1px solid ${c.grid};margin:4px 0"></div>` +
            row('transparent', `Total ${noun}`, fmt(total(a))) +
            (onPick ? `<div style="color:${c.muted};margin-top:2px">${pickText}</div>` : '');
        },
      },
      xAxis: { type: 'value', ...axisStyle(mode), axisLine: { show: false } },
      yAxis: {
        type: 'category', data: sorted.map((a) => a.area), ...axisStyle(mode),
        axisLabel: {
          ...axisStyle(mode).axisLabel, color: c.ink2,
          ...(labelOf ? { formatter: (v: string) => labelOf(v).name, width: 190, overflow: 'truncate' } : {}),
        },
      },
      series: [
        ...grades.map((g, k) => ({
          type: 'bar', name: g, stack: 'grades', data: sorted.map((a) => a[measure][k]), barMaxWidth: 16,
          // 1px surface border on each side = the 2px gap between segments
          itemStyle: { color: colors[k], borderColor: c.surface, borderWidth: 1,
            borderRadius: k === grades.length - 1 ? [0, 4, 4, 0] : 0 },
          cursor: onPick ? 'pointer' : 'default',
        })),
        { // zero-width bar at the end of each stack that carries the total label
          type: 'bar', name: 'Total', stack: 'grades', data: sorted.map(() => 0), silent: true,
          label: { show: true, position: 'right', color: c.ink2, fontSize: 11, fontFamily: FONT,
            formatter: (p: { dataIndex: number }) => fmt(total(sorted[p.dataIndex])) },
        },
      ],
    };
  }, [data, grades, measure, mode, onPick, noun, labelOf, pickText]);
  const height = Math.max(160, data.length * 24 + 24);
  return <EChart option={option} height={height} onClick={onPick} label={`${noun} by ${areaLabel} and grade`} />;
}

/* ------------------------------------------------------------------ catchment demand per school */

export interface SchoolDemand {
  code: number;
  name: string;
  sub: string; // district · sector
  demand: number; // children aged 3 in the catchment, `year`
  enrolled: number; // N1 in the base year
  rooms: number; // rooms shared to N1 in `year`
}

/** Children aged 3 in each school's catchment area against its N1 today, one school per row, largest first. */
export function CatchmentDemandChart({ data, year, baseYear, capacity, mode, onPick }: {
  data: SchoolDemand[];
  year: number;
  baseYear: number;
  capacity: number;
  mode: Mode;
  onPick?: (code: string) => void;
}) {
  const option = useMemo(() => {
    const c = COLORS[mode];
    const items = [...data].reverse(); // first item on top
    return {
      animationDuration: 300,
      grid: { left: 8, right: 56, top: 32, bottom: 8, containLabel: true },
      legend: {
        top: 0, left: 0, itemWidth: 10, itemHeight: 10, icon: 'roundRect',
        textStyle: { color: c.ink2, fontFamily: FONT, fontSize: 12 },
      },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const d = items[ps[0].dataIndex];
          const change = d.demand - d.enrolled;
          return `<div style="font-weight:600">${d.name}</div>` +
            `<div style="color:${c.ink2};margin-bottom:4px">${d.sub}</div>` +
            row(c.required, `Children aged 3 in the catchment, ${year}`, fmt(d.demand)) +
            row(c.muted, `N1 students ${baseYear}`, fmt(d.enrolled)) +
            `<div style="color:${c.ink2};margin-top:2px">${fmtGap(change)} (${d.enrolled ? pct(Math.abs(change), d.enrolled) : '—'} ${change >= 0 ? 'more' : 'fewer'})</div>` +
            `<div style="border-top:1px solid ${c.grid};margin:4px 0"></div>` +
            row('transparent', `Rooms needed for them (${capacity} per room)`, fmt(Math.ceil(d.demand / capacity))) +
            row('transparent', `Rooms for N1 in ${year}`, fmt(d.rooms)) +
            (onPick ? `<div style="color:${c.muted};margin-top:2px">Click for the school's details</div>` : '');
        },
      },
      xAxis: { type: 'value', ...axisStyle(mode), axisLine: { show: false }, splitNumber: 4 },
      yAxis: {
        type: 'category', data: items.map((d) => String(d.code)), ...axisStyle(mode),
        axisLabel: {
          ...axisStyle(mode).axisLabel, color: c.ink2, width: 190, overflow: 'truncate',
          formatter: (v: string) => items.find((d) => String(d.code) === v)?.name ?? v,
        },
      },
      series: [
        { type: 'bar', name: `Children aged 3 in the catchment, ${year}`, data: items.map((d) => d.demand),
          barMaxWidth: 12, barGap: '15%', itemStyle: { color: c.required, borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: 'right', color: c.ink2, fontSize: 11, fontFamily: FONT,
            formatter: (p: { value: number }) => fmt(p.value) },
          cursor: onPick ? 'pointer' : 'default' },
        { type: 'bar', name: `N1 students ${baseYear}`, data: items.map((d) => d.enrolled),
          barMaxWidth: 12, itemStyle: { color: c.muted, borderRadius: [0, 4, 4, 0] },
          cursor: onPick ? 'pointer' : 'default' },
      ],
    };
  }, [data, year, baseYear, capacity, mode, onPick]);
  const height = Math.max(200, data.length * 30 + 48);
  return <EChart option={option} height={height} onClick={onPick}
    label={`Children aged 3 in each school's catchment area in ${year} against N1 students in ${baseYear}`} />;
}

/* ------------------------------------------------------------------ students per room by area */

/** Students per available room in each area, against the room capacity: above the line, rooms are over-full. */
export function CrowdingByArea({ data, capacity, mode, areaLabel, onPick }: {
  data: [string, Totals][];
  capacity: number;
  mode: Mode;
  areaLabel: string;
  onPick?: (name: string) => void;
}) {
  const option = useMemo(() => {
    const c = COLORS[mode];
    const perRoom = (t: Totals) => (t.available ? t.students / t.available : 0);
    const sorted = [...data].sort((a, b) => perRoom(a[1]) - perRoom(b[1])); // most crowded on top
    return {
      animationDuration: 300,
      grid: { left: 8, right: 44, top: 24, bottom: 8, containLabel: true },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const [name, t] = sorted[ps[0].dataIndex];
          const v = perRoom(t);
          return `<div style="font-weight:600;margin-bottom:4px">${name}</div>` +
            row(v > capacity ? c.deficit : c.available, 'Students per room', v.toFixed(1)) +
            `<div style="color:${c.ink2};margin-top:4px">${fmt(t.students)} students · ${fmt(t.available)} rooms available</div>` +
            `<div style="color:${c.ink2};margin-top:2px">${v > capacity
              ? `${(v - capacity).toFixed(1)} over the ${capacity} a room seats`
              : `${(capacity - v).toFixed(1)} under the ${capacity} a room seats`}</div>` +
            (onPick ? `<div style="color:${c.muted};margin-top:2px">Click to filter</div>` : '');
        },
      },
      xAxis: { type: 'value', ...axisStyle(mode), axisLine: { show: false } },
      yAxis: {
        type: 'category', data: sorted.map(([n]) => n), ...axisStyle(mode),
        axisLabel: { ...axisStyle(mode).axisLabel, color: c.ink2 },
      },
      series: [{
        type: 'bar', name: 'Students per room', barMaxWidth: 14, cursor: onPick ? 'pointer' : 'default',
        data: sorted.map(([, t]) => {
          const v = perRoom(t);
          return { value: Math.round(v * 10) / 10, itemStyle: { color: v > capacity ? c.deficit : c.available, borderRadius: [0, 4, 4, 0] } };
        }),
        label: { show: true, position: 'right', color: c.ink2, fontSize: 11, fontFamily: FONT,
          formatter: (p: { value: number }) => p.value.toFixed(1) },
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: c.ink2, type: 'solid', width: 1 },
          label: { formatter: `${capacity} per room`, position: 'end', color: c.ink2, fontSize: 11, fontFamily: FONT },
          data: [{ xAxis: capacity }],
        },
      }],
    };
  }, [data, capacity, mode, onPick]);
  const height = Math.max(200, data.length * 22 + 40);
  return <EChart option={option} height={height} onClick={onPick} label={`Students per available room by ${areaLabel}`} />;
}

/* ------------------------------------------------------------------ schools by gap class (histogram) */

export function GapHistogram({ gaps, mode }: { gaps: number[]; mode: Mode }) {
  const option = useMemo(() => {
    const c = COLORS[mode];
    const counts = GAP_CLASSES.map((k) => gaps.filter((g) => g >= k.min && g <= k.max).length);
    const total = gaps.length;
    return {
      animationDuration: 300,
      grid: { left: 8, right: 8, top: 20, bottom: 4, containLabel: true },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const k = GAP_CLASSES[ps[0].dataIndex];
          return `<div style="font-weight:600;margin-bottom:4px">${k.label}</div>` +
            row(k[mode], 'Schools', fmt(counts[ps[0].dataIndex])) +
            `<div style="color:${c.ink2};margin-top:4px">${pct(counts[ps[0].dataIndex], total)} of schools in scope</div>`;
        },
      },
      xAxis: {
        type: 'category', data: GAP_CLASSES.map((k) => k.label), ...axisStyle(mode),
        axisLabel: { ...axisStyle(mode).axisLabel, interval: 0, fontSize: 10, color: c.ink2, lineHeight: 12,
          formatter: (v: string) => v.replace(' ', '\n') }, // '10+ short' on two lines so narrow cards don't overlap
      },
      yAxis: { type: 'value', ...axisStyle(mode), axisLine: { show: false }, splitNumber: 3 },
      series: [{
        type: 'bar', name: 'Schools', barMaxWidth: 28, barCategoryGap: '20%',
        data: counts.map((v, i) => ({ value: v, itemStyle: { color: GAP_CLASSES[i][mode], borderRadius: [4, 4, 0, 0] } })),
        label: { show: true, position: 'top', color: c.ink2, fontSize: 11, fontFamily: FONT, formatter: (p: { value: number }) => fmt(p.value) },
      }],
    };
  }, [gaps, mode]);
  return <EChart option={option} height={200} label="Number of schools by classroom gap" />;
}

/* ------------------------------------------------------------------ students by grade and year (cohorts), stacked */

export function CohortChart({ rows, years, baseYear, year, mode, onPick }: {
  rows: { grade: string; byYear: number[] }[];
  years: number[];
  baseYear: number;
  year: number;
  mode: Mode;
  onPick?: (year: string) => void;
}) {
  const option = useMemo(() => {
    const c = COLORS[mode];
    const colors = gradeColors(rows.length, mode);
    const totals = years.map((_, yi) => rows.reduce((s, r) => s + r.byYear[yi], 0));
    const dim = (yi: number) => (years[yi] === year ? 1 : 0.55);
    return {
      animationDuration: 300,
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      legend: {
        top: 0, left: 0, itemWidth: 10, itemHeight: 10, icon: 'roundRect', data: rows.map((r) => r.grade),
        textStyle: { color: c.ink2, fontFamily: FONT, fontSize: 12 },
      },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const yi = ps[0].dataIndex;
          const prev = yi > 0 ? totals[yi - 1] : null;
          return `<div style="font-weight:600;margin-bottom:4px">${years[yi]}${years[yi] === baseYear ? ' (actual)' : ''}</div>` +
            [...rows].reverse().map((r) => row(colors[rows.indexOf(r)], r.grade, fmt(r.byYear[yi]))).join('') +
            `<div style="border-top:1px solid ${c.grid};margin:4px 0"></div>` +
            row('transparent', 'Total students', fmt(totals[yi])) +
            (prev !== null ? `<div style="color:${c.ink2};margin-top:2px">${fmtGap(totals[yi] - prev)} vs ${years[yi - 1]}</div>` : '') +
            (onPick ? `<div style="color:${c.muted};margin-top:2px">Click to show this year</div>` : '');
        },
      },
      xAxis: { type: 'category', data: years.map((y) => (y === baseYear ? `${y}*` : String(y))), ...axisStyle(mode) },
      yAxis: {
        type: 'value', ...axisStyle(mode), axisLine: { show: false },
        axisLabel: { ...axisStyle(mode).axisLabel, formatter: (v: number) => (v >= 1e6 ? `${v / 1e6}M` : v >= 1e3 ? `${v / 1e3}k` : String(v)) },
      },
      series: [
        ...rows.map((r, k) => ({
          type: 'bar', name: r.grade, stack: 'grades', barMaxWidth: 44, cursor: onPick ? 'pointer' : 'default',
          itemStyle: { color: colors[k] },
          data: r.byYear.map((v, yi) => ({
            value: v,
            itemStyle: { color: colors[k], opacity: dim(yi), borderColor: c.surface, borderWidth: 1,
              borderRadius: k === rows.length - 1 ? [4, 4, 0, 0] : 0 },
          })),
        })),
        {
          type: 'bar', name: 'Total', stack: 'grades', data: years.map(() => 0), silent: true,
          label: { show: true, position: 'top', color: c.ink2, fontSize: 11, fontFamily: FONT,
            formatter: (p: { dataIndex: number }) => fmt(totals[p.dataIndex]) },
        },
      ],
    };
  }, [rows, years, baseYear, year, mode, onPick]);
  // ECharts reports the category label ("2026*"); strip the actual-year mark before passing it on
  const pick = useMemo(() => (onPick ? (name: string) => onPick(name.replace('*', '')) : undefined), [onPick]);
  return <EChart option={option} height={300} onClick={pick} label="Students by grade and year" />;
}

/* ------------------------------------------------------------------ new entrants per year */

export function EntrantsChart({ grade, years, baseYear, base, plan, defaults, defaultLabel = 'Default', mode }: {
  grade: string;
  years: number[]; // base year first
  baseYear: number;
  /** Students of the entry grade in the base year (enrolled, incl. repeaters). */
  base: number;
  /** New students per projected year (years[1..]). */
  plan: number[];
  /** Default-plan new students per projected year, drawn as markers when the plan differs. */
  defaults?: number[];
  /** Name of the default plan in the legend. */
  defaultLabel?: string;
  mode: Mode;
}) {
  const custom = !!defaults && defaults.some((v, i) => v !== plan[i]);
  const option = useMemo(() => {
    const c = COLORS[mode];
    const values = [base, ...plan];
    return {
      animationDuration: 300,
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      legend: {
        top: 0, left: 0, itemWidth: 10, itemHeight: 10,
        textStyle: { color: c.ink2, fontFamily: FONT, fontSize: 12 },
        data: [`${grade} enrolled ${baseYear}`, `New ${grade}`, ...(custom ? [defaultLabel] : [])],
      },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const yi = ps[0].dataIndex;
          if (yi === 0) {
            return `<div style="font-weight:600;margin-bottom:4px">${baseYear} (actual)</div>` +
              row(c.muted, `${grade} students enrolled`, fmt(base)) +
              `<div style="color:${c.ink2};margin-top:4px">All ${grade} pupils, including repeaters</div>`;
          }
          return `<div style="font-weight:600;margin-bottom:4px">${years[yi]}</div>` +
            row(c.available, `New ${grade}`, fmt(plan[yi - 1])) +
            (custom ? row(c.required, defaultLabel, fmt(defaults![yi - 1])) : '') +
            (yi > 1 ? `<div style="color:${c.ink2};margin-top:4px">${fmtGap(plan[yi - 1] - plan[yi - 2])} vs ${years[yi - 1]}</div>` : '');
        },
      },
      xAxis: { type: 'category', data: years.map((y) => (y === baseYear ? `${y}*` : String(y))), ...axisStyle(mode) },
      yAxis: {
        type: 'value', ...axisStyle(mode), axisLine: { show: false },
        axisLabel: { ...axisStyle(mode).axisLabel, formatter: (v: number) => (v >= 1e6 ? `${v / 1e6}M` : v >= 1e3 ? `${v / 1e3}k` : String(v)) },
      },
      series: [
        { type: 'bar', name: `${grade} enrolled ${baseYear}`, stack: 'v', barMaxWidth: 40, itemStyle: { color: c.muted },
          data: values.map((v, i) => (i === 0 ? { value: v, itemStyle: { color: c.muted, borderRadius: [4, 4, 0, 0] } } : 0)),
          label: { show: true, position: 'top', color: c.ink2, fontSize: 11, fontFamily: FONT,
            formatter: (p: { dataIndex: number; value: number }) => (p.dataIndex === 0 ? fmt(p.value) : '') } },
        { type: 'bar', name: `New ${grade}`, stack: 'v', barMaxWidth: 40, itemStyle: { color: c.available },
          data: values.map((v, i) => (i === 0 ? 0 : { value: v, itemStyle: { color: c.available, borderRadius: [4, 4, 0, 0] } })),
          label: { show: true, position: 'top', color: c.ink2, fontSize: 11, fontFamily: FONT,
            formatter: (p: { dataIndex: number; value: number }) => (p.dataIndex === 0 ? '' : fmt(p.value)) } },
        ...(custom ? [{
          type: 'line', name: defaultLabel, data: [null, ...defaults!], symbol: 'circle', symbolSize: 8,
          lineStyle: { width: 0 }, itemStyle: { color: c.required, borderColor: c.surface, borderWidth: 2 }, z: 5,
        }] : []),
      ],
    };
  }, [grade, years, baseYear, base, plan, defaults, defaultLabel, custom, mode]);
  return <EChart option={option} height={260} label={`New ${grade} students per year`} />;
}

/* ------------------------------------------------------------------ double-shift share by area */

export function DoubleShiftByArea({ data, mode, areaLabel, fullDay = false }: {
  data: [string, Totals][]; mode: Mode; areaLabel: string; fullDay?: boolean;
}) {
  const shareName = fullDay ? 'Share without a room' : 'Double-shift share';
  const option = useMemo(() => {
    const c = COLORS[mode];
    const share = (t: Totals) => (t.classGroups ? t.doubleShift / t.classGroups : 0);
    const sorted = [...data].sort((a, b) => share(a[1]) - share(b[1]));
    return {
      animationDuration: 300,
      grid: { left: 8, right: 52, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const [name, t] = sorted[ps[0].dataIndex];
          return `<div style="font-weight:600;margin-bottom:4px">${name}</div>` +
            row(c.doubleShift, shareName, pct(t.doubleShift, t.classGroups)) +
            `<div style="color:${c.ink2};margin-top:4px">${fmt(t.doubleShift)} of ${fmt(t.classGroups)} class groups ${
              fullDay ? 'have no room of their own' : 'share a room'}</div>`;
        },
      },
      xAxis: {
        type: 'value', ...axisStyle(mode), axisLine: { show: false },
        axisLabel: { ...axisStyle(mode).axisLabel, formatter: (v: number) => `${Math.round(v * 100)}%` },
      },
      yAxis: {
        type: 'category', data: sorted.map(([n]) => n), ...axisStyle(mode),
        axisLabel: { ...axisStyle(mode).axisLabel, color: c.ink2 },
      },
      series: [{
        type: 'bar', name: shareName, data: sorted.map(([, t]) => share(t)), barMaxWidth: 14,
        itemStyle: { color: c.doubleShift, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', color: c.ink2, fontSize: 11, fontFamily: FONT,
          formatter: (p: { value: number }) => `${(p.value * 100).toFixed(0)}%` },
      }],
    };
  }, [data, mode, fullDay, shareName]);
  const height = Math.max(220, data.length * 22 + 24);
  return <EChart option={option} height={height}
    label={`Share of class groups ${fullDay ? 'without a room' : 'on double shift'} by ${areaLabel}`} />;
}

/* ------------------------------------------------------------------ projection trend by year */

export function YearTrend({
  data, mode, year, baseYear, onPick, fullDay = false,
}: {
  data: YearTotals[];
  mode: Mode;
  year: number;
  baseYear: number;
  onPick?: (year: string) => void;
  fullDay?: boolean;
}) {
  const option = useMemo(() => {
    const c = COLORS[mode];
    const base = data.find((d) => d.year === baseYear);
    return {
      animationDuration: 300,
      grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
      legend: {
        top: 0, left: 0, itemWidth: 10, itemHeight: 10,
        textStyle: { color: c.ink2, fontFamily: FONT, fontSize: 12 },
      },
      tooltip: {
        ...tooltipBase(mode),
        formatter: (ps: { dataIndex: number }[]) => {
          const d = data[ps[0].dataIndex];
          return `<div style="font-weight:600;margin-bottom:4px">${d.year}${d.year === baseYear ? ' (actual)' : ''}</div>` +
            row(c.deficit, 'Classrooms short', fmt(d.short)) +
            row(c.doubleShift, dsName(fullDay), fmt(d.doubleShift)) +
            (base && d.year !== baseYear
              ? `<div style="color:${c.ink2};margin-top:4px">${fmtGap(d.short - base.short)} classrooms short vs ${baseYear}</div>`
              : '') +
            `<div style="color:${c.ink2};margin-top:2px">${fmt(d.students)} students · ${fmt(d.deficitSchools)} schools in deficit</div>` +
            (onPick ? `<div style="color:${c.muted};margin-top:2px">Click to show this year</div>` : '');
        },
      },
      xAxis: { type: 'category', data: data.map((d) => String(d.year)), ...axisStyle(mode) },
      yAxis: { type: 'value', ...axisStyle(mode), axisLine: { show: false } },
      series: [
        {
          type: 'bar', name: 'Classrooms short', barMaxWidth: 36, cursor: onPick ? 'pointer' : 'default',
          itemStyle: { color: c.deficit }, // legend swatch; per-bar styles below dim the other years
          data: data.map((d) => ({
            value: d.short,
            itemStyle: { color: c.deficit, opacity: d.year === year ? 1 : 0.45, borderRadius: [4, 4, 0, 0] },
          })),
          label: { show: true, position: 'top', color: c.ink2, fontSize: 11, fontFamily: FONT, formatter: (p: { value: number }) => fmt(p.value) },
        },
        {
          type: 'line', name: dsName(fullDay), data: data.map((d) => d.doubleShift),
          symbol: 'circle', symbolSize: 7, lineStyle: { color: c.doubleShift, width: 2 }, itemStyle: { color: c.doubleShift },
        },
      ],
    };
  }, [data, mode, year, baseYear, onPick, fullDay]);
  return <EChart option={option} height={280} onClick={onPick} label={`Classrooms short and ${dsName(fullDay).toLowerCase()} by year`} />;
}

/* ------------------------------------------------------------------ school status split (HTML) */

export function StatusSplit({ t, mode }: { t: Totals; mode: Mode }) {
  const parts = [
    { key: 'Deficit' as const, n: t.deficitSchools, note: 'not enough rooms' },
    { key: 'Exact fit' as const, n: t.exactSchools, note: 'exactly enough' },
    { key: 'Surplus' as const, n: t.surplusSchools, note: 'spare rooms' },
  ];
  return (
    <div>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded" role="img"
        aria-label={parts.map((p) => `${p.key}: ${p.n} schools`).join(', ')}>
        {parts.map((p) =>
          p.n > 0 ? (
            <div key={p.key} title={`${p.key}: ${fmt(p.n)} schools (${pct(p.n, t.schools)})`}
              style={{ flexGrow: p.n, background: STATUS_COLORS[mode][p.key] }} />
          ) : null,
        )}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        {parts.map((p) => (
          <div key={p.key}>
            <div className="flex items-center gap-1.5 text-ink2">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: STATUS_COLORS[mode][p.key] }} />
              {p.key}
            </div>
            <div className="mt-0.5 text-lg font-semibold text-ink">{fmt(p.n)}</div>
            <div className="text-muted">{pct(p.n, t.schools)} · {p.note}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
