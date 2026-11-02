import { Component, StrictMode, Suspense, lazy, useEffect, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import './index.css';
import './site/site.css';
import { AuthProvider, RequireAdmin, RequireAuth } from './auth';
import { ThemeProvider } from './theme';
import LegalPage from './site/LegalPage';

// The dashboard (map, charts) loads only after sign-in, so the sign-in step and the legal pages stay light
const Dashboard = lazy(() => import('./App'));
const Admin = lazy(() => import('./admin/AdminApp'));

/** Public pages (legal) share the site layout (site.css), in the dashboard's theme. */
function SitePages() {
  return (
    <div className="site">
      <Outlet />
    </div>
  );
}

/** A new page starts at the top (except links to a landing-page section). */
function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) window.scrollTo(0, 0);
  }, [pathname, hash]);
  return null;
}

const loading = <div className="grid min-h-screen place-items-center text-sm text-muted">Loading the dashboard…</div>;

/**
 * The dashboard's code is loaded after sign-in. If that fails — usually because a new version was installed while this
 * page was open, so the files it asks for are gone — offer a reload instead of a blank page.
 */
class DashboardBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="grid min-h-screen place-items-center p-8 text-center text-sm text-ink2">
        <div>
          <p>The dashboard could not be loaded — the site may have been updated since this page was opened.</p>
          <button type="button" onClick={() => window.location.reload()}
            className="mt-3 h-8 rounded-md border border-line px-3 text-sm text-ink hover:bg-[var(--line)]">
            Reload
          </button>
        </div>
      </div>
    );
  }
}

// The site's home page is the dashboard (the portal's sign-in comes back to the site's base)
const dashboard = (
  <RequireAuth>
    <DashboardBoundary>
      <Suspense fallback={loading}>
        <Dashboard />
      </Suspense>
    </DashboardBoundary>
  </RequireAuth>
);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || '/'}>
      <ThemeProvider>
        <AuthProvider>
          <ScrollToTop />
          <Routes>
            <Route element={<SitePages />}>
              <Route path="/legal/:page" element={<LegalPage />} />
            </Route>
            <Route path="/" element={dashboard} />
            <Route path="/dashboard" element={dashboard} />
            <Route path="/admin/*" element={
              <RequireAuth>
                <RequireAdmin>
                  <DashboardBoundary>
                    <Suspense fallback={loading}>
                      <Admin />
                    </Suspense>
                  </DashboardBoundary>
                </RequireAdmin>
              </RequireAuth>
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);
