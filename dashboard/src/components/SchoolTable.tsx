import { useEffect, useMemo, useState } from 'react';
import { fmt, fmtGap, statusOf, type SchoolLevel } from '../data';
import { STATUS_COLORS, type Mode } from '../theme';
import { usePrinting } from '../print';

type Key = 'n' | 'd' | 's' | 'st' | 'g' | 'ds' | 'a' | 'r' | 'gap';

const COLS: { key: Key; label: string; num?: boolean; hideSm?: boolean }[] = [
  { key: 'n', label: 'School' },
  { key: 'd', label: 'District', hideSm: true },
  { key: 's', label: 'Sector', hideSm: true },
  { key: 'st', label: 'Students', num: true },
  { key: 'g', label: 'Class groups', num: true, hideSm: true },
  { key: 'ds', label: 'Double shift', num: true, hideSm: true },
  { key: 'a', label: 'Available', num: true },
  { key: 'r', label: 'Required', num: true },
  { key: 'gap', label: 'Gap', num: true },
];

const PAGE = 10; // schools per page
const PRINT_ROWS = 25; // schools in the printed report

type Test = (r: SchoolLevel) => boolean;
interface Option { key: string; label: string; test: Test }

// Gap bands match the map legend.
const GAP_OPTIONS: Option[] = [
  { key: 'deficit', label: 'Deficit (any)', test: (r) => r.gap < 0 },
  { key: 'd10', label: '— 10+ classrooms short', test: (r) => r.gap <= -10 },
  { key: 'd4', label: '— 4–9 short', test: (r) => r.gap <= -4 && r.gap >= -9 },
  { key: 'd1', label: '— 1–3 short', test: (r) => r.gap <= -1 && r.gap >= -3 },
  { key: 'exact', label: 'Exact fit', test: (r) => r.gap === 0 },
  { key: 'surplus', label: 'Surplus', test: (r) => r.gap > 0 },
];
const SHIFT_OPTIONS: Option[] = [
  { key: 'yes', label: 'With double shift', test: (r) => r.ds > 0 },
  { key: 'no', label: 'No double shift', test: (r) => r.ds === 0 },
];
// Full-day levels (secondary, TVET, TTC): `ds` counts class groups without a room
const NO_ROOM_OPTIONS: Option[] = [
  { key: 'yes', label: 'Groups without a room', test: (r) => r.ds > 0 },
  { key: 'no', label: 'Every group has a room', test: (r) => r.ds === 0 },
];
const SIZE_OPTIONS: Option[] = [
  { key: 's1', label: 'Under 200 students', test: (r) => r.st < 200 },
  { key: 's2', label: '200–499', test: (r) => r.st >= 200 && r.st < 500 },
  { key: 's3', label: '500–999', test: (r) => r.st >= 500 && r.st < 1000 },
  { key: 's4', label: '1,000–1,999', test: (r) => r.st >= 1000 && r.st < 2000 },
  { key: 's5', label: '2,000 or more', test: (r) => r.st >= 2000 },
];

interface Props {
  rows: SchoolLevel[];
  mode: Mode;
  selected: number | null;
  onSelect: (code: number) => void;
  /** Full-day level: the double-shift column counts class groups without a room. */
  fullDay: boolean;
}

type FilterKey = 'gap' | 'shift' | 'size';
const NO_FILTERS: Record<FilterKey, string> = { gap: '', shift: '', size: '' };

function FilterSelect({ label, value, all, options, counts, onChange }: {
  label: string; value: string; all: string; options: Option[]; counts: Map<string, number>; onChange: (v: string) => void;
}) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
      className={`h-9 px-2 text-sm ${value ? 'border-accent text-accent' : ''}`}>
      <option value="">{all}</option>
      {options.map((o) => (
        <option key={o.key} value={o.key}>{o.label} ({fmt(counts.get(o.key) ?? 0)})</option>
      ))}
    </select>
  );
}

export default function SchoolTable({ rows, mode, selected, onSelect, fullDay }: Props) {
  const shiftOptions = fullDay ? NO_ROOM_OPTIONS : SHIFT_OPTIONS;
  const colLabel = (c: (typeof COLS)[number]) => (c.key === 'ds' && fullDay ? 'No room' : c.label);
  const [sort, setSort] = useState<{ key: Key; asc: boolean }>({ key: 'gap', asc: true });
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState(NO_FILTERS);
  const [page, setPage] = useState(0);
  const printing = usePrinting();

  const groups = useMemo<Record<FilterKey, Option[]>>(
    () => ({ gap: GAP_OPTIONS, shift: shiftOptions, size: SIZE_OPTIONS }),
    [shiftOptions],
  );
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const opts of Object.values(groups)) for (const o of opts) m.set(o.key, rows.filter(o.test).length);
    return m;
  }, [rows, groups]);
  const active = (Object.keys(filters) as FilterKey[]).filter((k) => filters[k]);
  const setFilter = (k: FilterKey, v: string) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(0);
  };

  const view = useMemo(() => {
    const q = query.trim().toLowerCase();
    const tests = (Object.keys(filters) as FilterKey[])
      .filter((k) => filters[k])
      .map((k) => groups[k].find((o) => o.key === filters[k])!.test);
    const filtered = rows.filter((r) =>
      (!q || r.n.toLowerCase().includes(q) || String(r.c).includes(q)) && tests.every((t) => t(r)));
    const dir = sort.asc ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const x = a[sort.key];
      const y = b[sort.key];
      const cmp = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
      return cmp * dir || a.n.localeCompare(b.n);
    });
  }, [rows, sort, query, filters, groups]);

  const pages = Math.max(1, Math.ceil(view.length / PAGE));
  const current = Math.min(page, pages - 1); // the rows can shrink under the page (level or area filter)
  const shown = printing ? view.slice(0, PRINT_ROWS) : view.slice(current * PAGE, current * PAGE + PAGE);

  // A school picked on the map: show the page it is on
  useEffect(() => {
    if (selected === null) return;
    const i = view.findIndex((r) => r.c === selected);
    if (i >= 0) setPage(Math.floor(i / PAGE));
  }, [selected, view]);

  const toggleSort = (key: Key) => {
    setPage(0);
    setSort((s) => (s.key === key ? { key, asc: !s.asc } : { key, asc: key === 'gap' || !COLS.find((c) => c.key === key)?.num }));
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 px-4 pb-3 print:hidden">
        <input
          type="search"
          placeholder="Search school name or code"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          className="h-9 w-full max-w-xs px-3 text-sm"
          aria-label="Search schools"
        />
        <FilterSelect label="Classroom gap" value={filters.gap} all="Any gap" options={GAP_OPTIONS} counts={counts}
          onChange={(v) => setFilter('gap', v)} />
        <FilterSelect label="Double shift" value={filters.shift} all={fullDay ? 'Any room situation' : 'Any double shift'}
          options={shiftOptions} counts={counts}
          onChange={(v) => setFilter('shift', v)} />
        <FilterSelect label="School size" value={filters.size} all="Any size" options={SIZE_OPTIONS} counts={counts}
          onChange={(v) => setFilter('size', v)} />
        {(active.length > 0 || query) && (
          <button type="button" className="text-sm text-accent hover:underline"
            onClick={() => {
              setFilters(NO_FILTERS);
              setQuery('');
              setPage(0);
            }}>
            Clear filters
          </button>
        )}
        <span className="text-xs text-muted">
          {view.length === rows.length ? fmt(rows.length) : `${fmt(view.length)} of ${fmt(rows.length)}`} schools · sorted by{' '}
          {colLabel(COLS.find((c) => c.key === sort.key)!).toLowerCase()}
          {sort.asc ? ' (ascending)' : ' (descending)'}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-y border-line text-left text-xs text-muted">
              {COLS.map((c) => (
                <th key={c.key} scope="col"
                  className={`whitespace-nowrap px-3 py-2 font-medium ${c.num ? 'text-right' : ''} ${c.hideSm ? 'print-cell hidden md:table-cell' : ''}`}
                  aria-sort={sort.key === c.key ? (sort.asc ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" onClick={() => toggleSort(c.key)} className="hover:text-ink">
                    {colLabel(c)}
                    {sort.key === c.key ? (sort.asc ? ' ↑' : ' ↓') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const status = statusOf(r.gap);
              return (
                <tr key={r.c} tabIndex={0}
                  onClick={() => onSelect(r.c)}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect(r.c))}
                  className={`cursor-pointer border-b border-line hover:bg-[var(--line)] ${selected === r.c ? 'bg-[var(--line)]' : ''}`}>
                  <td className="px-3 py-2">
                    <div className="font-medium text-ink">{r.n}</div>
                    <div className="text-xs text-muted">{r.c}{r.x === null ? ' · not on map' : ''}</div>
                  </td>
                  <td className="print-cell hidden px-3 py-2 text-ink2 md:table-cell">{r.d}</td>
                  <td className="print-cell hidden px-3 py-2 text-ink2 md:table-cell">{r.s}</td>
                  <td className="num px-3 py-2 text-right">{fmt(r.st)}</td>
                  <td className="print-cell num hidden px-3 py-2 text-right md:table-cell">{fmt(r.g)}</td>
                  <td className="print-cell num hidden px-3 py-2 text-right md:table-cell">{fmt(r.ds)}</td>
                  <td className="num px-3 py-2 text-right">{fmt(r.a)}</td>
                  <td className="num px-3 py-2 text-right">{fmt(r.r)}</td>
                  <td className="num whitespace-nowrap px-3 py-2 text-right font-semibold">
                    <span className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle"
                      style={{ background: STATUS_COLORS[mode][status] }} aria-hidden />
                    {fmtGap(r.gap)}
                    <span className="sr-only"> ({status})</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {printing ? (
        <p className="px-4 py-2 text-xs text-muted">
          First {fmt(Math.min(PRINT_ROWS, view.length))} of {fmt(view.length)} schools, sorted by{' '}
          {colLabel(COLS.find((c) => c.key === sort.key)!).toLowerCase()}. The full list is in the dashboard and the Excel workbook.
        </p>
      ) : (
        <Pager page={current} pages={pages} total={view.length} onChange={setPage} />
      )}
    </div>
  );
}

/** Page numbers around the current page, with the first and last always shown ("…" for the gaps). */
function pageList(page: number, pages: number): (number | null)[] {
  const keep = new Set([0, pages - 1, page - 1, page, page + 1].filter((p) => p >= 0 && p < pages));
  const out: (number | null)[] = [];
  [...keep].sort((a, b) => a - b).forEach((p, i, all) => {
    if (i > 0 && p - all[i - 1] > 1) out.push(null);
    out.push(p);
  });
  return out;
}

function Pager({ page, pages, total, onChange }: { page: number; pages: number; total: number; onChange: (p: number) => void }) {
  if (!total) return <div className="p-4 text-center text-sm text-muted">No schools match these filters.</div>;
  const btn = 'h-8 min-w-8 rounded-md px-2 text-sm disabled:opacity-40';
  const idle = `${btn} border border-line text-ink2 hover:text-ink disabled:hover:text-ink2`;
  return (
    <nav className="flex flex-wrap items-center gap-3 px-4 py-3" aria-label="Schools table pages">
      <span className="text-xs text-muted">
        Showing {fmt(page * PAGE + 1)}–{fmt(Math.min(total, (page + 1) * PAGE))} of {fmt(total)} schools
      </span>
      <div className="ml-auto flex flex-wrap items-center gap-1">
        <button type="button" className={idle} disabled={page === 0} onClick={() => onChange(page - 1)} aria-label="Previous page">
          ‹ Prev
        </button>
        {pageList(page, pages).map((p, i) =>
          p === null ? (
            <span key={`gap${i}`} className="px-1 text-sm text-muted" aria-hidden>…</span>
          ) : (
            <button key={p} type="button" onClick={() => onChange(p)} aria-current={p === page ? 'page' : undefined}
              aria-label={`Page ${p + 1}`}
              className={p === page ? `${btn} num bg-accent text-white` : `${idle} num`}>
              {fmt(p + 1)}
            </button>
          ),
        )}
        <button type="button" className={idle} disabled={page >= pages - 1} onClick={() => onChange(page + 1)} aria-label="Next page">
          Next ›
        </button>
      </div>
    </nav>
  );
}
