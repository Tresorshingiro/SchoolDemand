import { Component, StrictMode, Suspense, lazy, useEffect, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import './index.css';
import './site/site.css';
import { AuthProvider, RequireAuth } from './auth';
import { ThemeProvider } from './theme';
import LandingPage from './site/LandingPage';
import LoginPage from './site/LoginPage';
import LegalPage from './site/LegalPage';

// The dashboard (map, charts) loads only after sign-in, so the landing page stays light
const Dashboard = lazy(() => import('./App'));

/** Public pages share the site layout (site.css), in the dashboard's theme. */
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || '/'}>
      <ThemeProvider>
        <AuthProvider>
          <ScrollToTop />
          <Routes>
            <Route element={<SitePages />}>
              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/legal/:page" element={<LegalPage />} />
            </Route>
            <Route path="/dashboard" element={
              <RequireAuth>
                <DashboardBoundary>
                  <Suspense fallback={loading}>
                    <Dashboard />
                  </Suspense>
                </DashboardBoundary>
              </RequireAuth>
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);
