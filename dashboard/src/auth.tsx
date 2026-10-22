/**
 * Who is signed in. People sign in with their MINEDUC GIS portal account (the API checks it with the portal); the
 * session itself is an HttpOnly cookie set by the API (POST /api/auth/login), so the page never sees a token: it asks
 * /api/auth/me on load and after sign-in / sign-out.
 *
 * On the portal's own site a page that needs a session goes through the portal's sign-in instead of the form
 * (portalSignIn.ts): someone already signed in to the portal comes straight back, signed in here too. Signing out turns
 * that off for the tab until the user asks for it on the sign-in page.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { AUTH_EXPIRED, ApiError, getJson, sendJson } from './api';
import {
  finishPortalSignIn, portalSignInOn, returningFromPortal, setPortalSignInOff, sitePath, startPortalSignIn,
} from './portalSignIn';

export interface User {
  id: number;
  username: string; // MINEDUC GIS portal username
  email: string | null; // from the portal profile
  full_name: string | null; // from the portal profile
  role: 'admin' | 'viewer';
}

interface AuthState {
  user: User | null;
  checking: boolean; // the first /auth/me has not answered yet (or the portal sign-in is being finished)
  signIn: (username: string, password: string, remember: boolean) => Promise<User>;
  /** Go through the portal's sign-in (portal site only), then to `next`. */
  signInWithPortal: (next: string) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

let finished: Promise<void> | null = null; // StrictMode runs effects twice: one session

/** Back from the portal's sign-in: open our session with its token, then show the page that was asked for. */
function finishFromPortal(): Promise<void> {
  finished ??= openPortalSession();
  return finished;
}

async function openPortalSession(): Promise<void> {
  const { token, next } = await finishPortalSignIn();
  let ok = false;
  if (token) {
    try {
      await sendJson<User>('POST', '/auth/portal-token', { token });
      ok = true;
    } catch {
      setPortalSignInOff(true); // refused here (account disabled …): the form says why when it is used
    }
  }
  // A fresh load of the page asked for, without the code in the address (the session cookie is set), or the form
  window.location.replace(sitePath(ok ? next : `/login?next=${encodeURIComponent(next)}`));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (returningFromPortal()) {
      void finishFromPortal(); // the page reloads when done; "checking" until then
      return;
    }
    getJson<User>('/auth/me')
      .then(setUser)
      .catch(() => setUser(null)) // 401: not signed in (or the API is unreachable — the sign-in page will say so)
      .finally(() => setChecking(false));
    const expired = () => setUser(null);
    window.addEventListener(AUTH_EXPIRED, expired);
    return () => window.removeEventListener(AUTH_EXPIRED, expired);
  }, []);

  const signIn = useCallback(async (username: string, password: string, remember: boolean) => {
    const u = await sendJson<User>('POST', '/auth/login', { username, password, remember });
    setPortalSignInOff(false);
    setUser(u);
    return u;
  }, []);

  const signInWithPortal = useCallback((next: string) => {
    setPortalSignInOff(false);
    void startPortalSignIn(next);
  }, []);

  const signOut = useCallback(async () => {
    setPortalSignInOff(true); // otherwise the next page would sign in again through the portal straight away
    try {
      await sendJson<void>('POST', '/auth/logout');
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(() => ({ user, checking, signIn, signInWithPortal, signOut }),
    [user, checking, signIn, signInWithPortal, signOut]);
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

/**
 * Only for signed-in users; others sign in (through the portal on its site, else the sign-in page) and come back here
 * afterwards.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  const viaPortal = !checking && !user && portalSignInOn();
  useEffect(() => {
    if (viaPortal) void startPortalSignIn(location.pathname + location.search);
  }, [viaPortal, location.pathname, location.search]);
  if (checking) return <div className="grid min-h-screen place-items-center text-sm text-muted">Checking sign-in…</div>;
  if (viaPortal) {
    return <div className="grid min-h-screen place-items-center text-sm text-muted">Signing in with the GIS portal…</div>;
  }
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

/** Only for administrators (inside RequireAuth); viewers go to the dashboard. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!isAdmin(user)) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

/** Where to go after sign-in: the page the user asked for (same site only), else the dashboard. */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/login') ? next : '/dashboard';
}
