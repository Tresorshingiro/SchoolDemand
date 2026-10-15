import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { loadDataset, type Dataset } from './data';
import { ThemeToggle, useTheme } from './theme';
import { useAuth } from './auth';
import UserMenu from './UserMenu';
import { LogoMark } from './site/SiteChrome';
import ProjectionPage from './components/ProjectionPage';

/** The span of years the dashboard covers: the first actual school year to the last projected one. */
const yearSpan = (d: Dataset) =>
  `${d.meta.actualYears[0]}–${d.meta.projectionYears[d.meta.projectionYears.length - 1]}`;

/**
 * The dashboard (signed-in users): the actual school years and the four projected years after the newest, picked
 * with the Year control.
 */
export default function App() {
  const { mode } = useTheme();
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDataset().then(setData).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    if (!data) return;
    const previous = document.title;
    document.title = `Classroom Sufficiency ${yearSpan(data)}`;
    return () => {
      document.title = previous;
    };
  }, [data]);

  // Leave the dashboard first: once the user is cleared, its guard would send the page to the sign-in form instead
  const onSignOut = () => {
    navigate('/', { replace: true });
    void signOut();
  };

  if (error) {
    return <div className="p-8 text-sm text-ink2">Could not load the dashboard data: {error}</div>;
  }
  if (!data) {
    return <div className="grid min-h-screen place-items-center text-sm text-muted">Loading data…</div>;
  }

  return (
    <div className="print-frame min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <Link to="/" title="School Demand & Demographics — home" className="shrink-0 print:hidden">
            <LogoMark size={32} />
          </Link>
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-semibold text-ink sm:text-lg">Classroom Sufficiency {yearSpan(data)}</h1>
            <p className="hidden truncate text-xs text-muted sm:block print:block">
              Classrooms available and needed at every level, as cohorts move up and new children start school
            </p>
          </div>
          <ThemeToggle className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink2 hover:text-ink print:hidden" />
          <UserMenu onSignOut={onSignOut} />
        </div>
      </header>

      <ProjectionPage current={data} mode={mode} />
    </div>
  );
}
