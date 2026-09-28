import { StrictMode, Suspense, lazy, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/inter/800.css';
import './index.css';
import './site/site.css';
import { AuthProvider, RequireAuth } from './auth';
import LandingPage from './site/LandingPage';
import LoginPage from './site/LoginPage';
import LegalPage from './site/LegalPage';

// The dashboard (map, charts) loads only after sign-in, so the landing page stays light
const Dashboard = lazy(() => import('./App'));

/** Public pages share the site styles (site.css, always light). */
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || '/'}>
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
              <Suspense fallback={loading}>
                <Dashboard />
              </Suspense>
            </RequireAuth>
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
