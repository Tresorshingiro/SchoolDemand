import { useEffect, useState } from 'react';
import { fmt, loadDataset, type Dataset } from './data';
import { useTheme } from './theme';
import Overview from './components/Overview';
import ProjectionPage from './components/ProjectionPage';

type Page = 'current' | 'projection';
const PAGES: { key: Page; label: string; hash: string }[] = [
  { key: 'current', label: 'Current 2026', hash: '#/' },
  { key: 'projection', label: 'Projection 2027–30', hash: '#/projection' },
];

const pageFromHash = (): Page => (window.location.hash.startsWith('#/projection') ? 'projection' : 'current');

export default function App() {
  const { mode, toggle } = useTheme();
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<Page>(pageFromHash);

  useEffect(() => {
    loadDataset().then(setData).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  if (error) {
    return <div className="p-8 text-sm text-ink2">Could not load the dashboard data: {error}</div>;
  }
  if (!data) {
    return <div className="grid min-h-screen place-items-center text-sm text-muted">Loading data…</div>;
  }

  const { meta } = data;

  return (
    <div className="print-frame min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-semibold text-ink sm:text-lg">Classroom Sufficiency</h1>
            <p className="hidden truncate text-xs text-muted sm:block print:block">
              {page === 'current'
                ? 'Enough classrooms to seat every student at 45 per room?'
                : 'Classrooms short as cohorts move up and new children start school'}
            </p>
          </div>
          <nav className="flex gap-5 print:hidden" aria-label="Pages">
            {PAGES.map((p) => (
              <a key={p.key} href={p.hash} aria-current={page === p.key ? 'page' : undefined}
                className={`border-b-2 py-1 text-sm ${page === p.key
                  ? 'border-accent font-medium text-ink' : 'border-transparent text-ink2 hover:text-ink'}`}>
                {p.label}
              </a>
            ))}
          </nav>
          <button type="button" onClick={toggle} title={mode === 'dark' ? 'Light theme' : 'Dark theme'}
            className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink2 hover:text-ink print:hidden"
            aria-label={`Switch to ${mode === 'dark' ? 'light' : 'dark'} theme`}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {mode === 'dark'
                ? <path d="M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
                : <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8" />}
            </svg>
          </button>
        </div>
      </header>

      {page === 'projection' ? (
        <ProjectionPage current={data} mode={mode} />
      ) : (
        <Overview
          key="current"
          data={data}
          mode={mode}
          showLevels
          notes={{
            available: 'distinct physical rooms',
            gradeChart: 'Rooms are counted within each grade, so a room shared by two grades appears in both.',
          }}
          footer={(capacity) => (
            <>
              <p>
                <b className="text-ink2">Definitions.</b> Class groups = Total Classrooms (one roster row each). Double-shift sessions =
                class groups sharing a room with another group. Rooms available = distinct physical rooms. Rooms required =
                students ÷ {capacity}, rounded up. Gap = available − required (negative = deficit). Classrooms short adds up
                the deficits of schools in deficit only, since spare rooms cannot seat pupils from another school.
              </p>
              <p>
                <b className="text-ink2">Secondary, TVET and TTC</b> study full day, so there is no double shift: every class group
                needs its own room and different combinations never share. Rooms required = for each grade and combination, the
                larger of its class groups and its students ÷ {capacity} (rounded up), added up. A class group that shares a room
                ID with another group in the roster has no room of its own; it is counted under "class groups without a room"
                and in the gap.
              </p>
              <p>
                Source: {meta.source} ({fmt(meta.roster.rows)} class groups, {fmt(meta.roster.schools)} schools). Built {meta.built}.
                {' '}{fmt(meta.unmapped)} schools have missing or out-of-country coordinates and are listed in the table but not on the map.
                Full figures and the data-quality list are in School_Classroom_Analysis_2026.xlsx.
              </p>
            </>
          )}
        />
      )}
    </div>
  );
}
