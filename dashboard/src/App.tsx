import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { loadDataset, type Dataset } from './data';
import { useTheme } from './theme';
import { displayName, useAuth } from './auth';
import { LogoMark } from './site/SiteChrome';
import ProjectionPage from './components/ProjectionPage';

/** The dashboard (signed-in users): 2026 actual and 2027–2030 projected, picked with the Year control. */
export default function App() {
  const { mode, toggle } = useTheme();
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDataset().then(setData).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    const previous = document.title;
    document.title = 'Classroom Sufficiency 2026–2030';
    return () => {
      document.title = previous;
    };
  }, []);

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
            <h1 className="text-base font-semibold text-ink sm:text-lg">Classroom Sufficiency 2026–2030</h1>
            <p className="hidden truncate text-xs text-muted sm:block print:block">
              Classrooms available and needed at every level, as cohorts move up and new children start school
            </p>
          </div>
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
          {user && (
            <div className="flex items-center gap-3 print:hidden">
              <span className="hidden max-w-[220px] truncate text-xs text-ink2 sm:inline" title={user.email}>
                {displayName(user)}
              </span>
              <button type="button" onClick={onSignOut}
                className="h-8 rounded-md border border-line px-2.5 text-xs text-ink2 hover:text-ink">
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      <ProjectionPage current={data} mode={mode} />
    </div>
  );
}
