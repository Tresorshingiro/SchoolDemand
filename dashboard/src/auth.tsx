/**
 * Who is signed in. People sign in with their MINEDUC GIS portal account through the portal's own sign-in
 * (portalSignIn.ts); the session itself is an HttpOnly cookie set by the API (POST /api/auth/portal-token), so the page
 * never keeps a token: it asks /api/auth/me on load.
 *
 * On load: a session already open -> signed in. Otherwise, back from the portal with a token -> open the session with
 * it. Otherwise -> go to the portal's sign-in (once per tab: when the portal comes back without a token, the page says
 * so instead of looping). Signing out ends the session here and on the portal.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { AUTH_EXPIRED, ApiError, getJson, sendJson } from './api';
import { authorizeUrl, signOutUrl, takeReturn } from './portalSignIn';

export interface User {
  id: number;
  username: string; // MINEDUC GIS portal username
  email: string | null; // from the portal profile
  full_name: string | null; // from the portal profile
  role: 'admin' | 'viewer';
}

interface AuthState {
  user: User | null;
  checking: boolean; // the first /auth/me (or the portal token) has not answered yet
  problem: string | null; // why the user is not signed in, when it is not just "on the way to the portal"
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

// Read once, before the router or StrictMode can run anything twice: the address is cleaned straight away
const returned = takeReturn();
const REDIRECTED_KEY = 'school:portal-redirect'; // sessionStorage: this tab has been sent to the portal

const redirected = () => {
  try {
    return sessionStorage.getItem(REDIRECTED_KEY) === '1';
  } catch {
    return false;
  }
};
const setRedirected = (on: boolean) => {
  try {
    if (on) sessionStorage.setItem(REDIRECTED_KEY, '1');
    else sessionStorage.removeItem(REDIRECTED_KEY);
  } catch {
    /* storage unavailable */
  }
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const { token, error } = returned;
    const toPortal = () => {
      setRedirected(true);
      window.location.assign(authorizeUrl());
    };
    // true while the browser is leaving for the portal ("checking" stays on)
    const run = async (): Promise<boolean> => {
      try {
        setUser(await getJson<User>('/auth/me'));
        setRedirected(false);
        return false;
      } catch {
        /* not signed in */
      }
      if (error) {
        setProblem(`The portal did not sign you in: ${error}`);
        return false;
      }
      if (token) {
        try {
          setUser(await sendJson<User>('POST', '/auth/portal-token', { token, remember: false }));
          setRedirected(false);
        } catch (e) {
          setProblem(e instanceof ApiError ? e.message : 'The sign-in could not be completed.');
        }
        return false;
      }
      if (redirected()) {
        setProblem('The portal did not send a token back. Open the dashboard again to try once more.');
        setRedirected(false);
        return false;
      }
      toPortal();
      return true;
    };
    void run().then((leaving) => {
      if (!leaving) setChecking(false);
    });
    const expired = () => {
      setUser(null);
      setProblem('Your session has ended. Reload the page to sign in again.');
    };
    window.addEventListener(AUTH_EXPIRED, expired);
    return () => window.removeEventListener(AUTH_EXPIRED, expired);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await sendJson<void>('POST', '/auth/logout');
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    } finally {
      setUser(null);
      setRedirected(false);
      window.location.assign(signOutUrl()); // the portal's session too, then back to the site
    }
  }, []);

  const value = useMemo(() => ({ user, checking, problem, signOut }), [user, checking, problem, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}

/** The name to show for a user. */
export const displayName = (u: User) => u.full_name || u.username;

/** Admins manage accounts, data and saved plans; viewers read and try plans. */
export const isAdmin = (u: User | null) => u?.role === 'admin';

/** Only for signed-in users; others are on their way to the portal's sign-in (or told why they are not signed in). */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, checking, problem } = useAuth();
  if (checking) return <div className="grid min-h-screen place-items-center text-sm text-muted">Checking sign-in…</div>;
  if (user) return <>{children}</>;
  return (
    <div className="grid min-h-screen place-items-center p-8 text-center text-sm text-ink2">
      <div className="max-w-sm">
        <p className="text-base font-medium text-ink">School Demand &amp; Demographics</p>
        <p className="mt-2">{problem ?? 'Taking you to the portal to sign in…'}</p>
      </div>
    </div>
  );
}

/** Only for administrators (inside RequireAuth); viewers go to the dashboard. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!isAdmin(user)) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
