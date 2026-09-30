/**
 * Who is signed in. The session itself is an HttpOnly cookie set by the API (POST /api/auth/login), so the page never
 * sees a token: it asks /api/auth/me on load and after sign-in / sign-out.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { AUTH_EXPIRED, ApiError, PASSWORD_REQUIRED, getJson, sendJson } from './api';

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  role: 'admin' | 'viewer';
  must_change_password: boolean; // a temporary password set by an admin: the user must choose their own first
}

interface AuthState {
  user: User | null;
  checking: boolean; // the first /auth/me has not answered yet
  signIn: (email: string, password: string, remember: boolean) => Promise<User>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>; // re-read /auth/me (after a password change)
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    getJson<User>('/auth/me')
      .then(setUser)
      .catch(() => setUser(null)) // 401: not signed in (or the API is unreachable — the sign-in page will say so)
      .finally(() => setChecking(false));
    const expired = () => setUser(null);
    const mustChange = () => setUser((u) => (u ? { ...u, must_change_password: true } : u));
    window.addEventListener(AUTH_EXPIRED, expired);
    window.addEventListener(PASSWORD_REQUIRED, mustChange);
    return () => {
      window.removeEventListener(AUTH_EXPIRED, expired);
      window.removeEventListener(PASSWORD_REQUIRED, mustChange);
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string, remember: boolean) => {
    const u = await sendJson<User>('POST', '/auth/login', { email, password, remember });
    setUser(u);
    return u;
  }, []);

  const refresh = useCallback(async () => {
    setUser(await getJson<User>('/auth/me'));
  }, []);

  const signOut = useCallback(async () => {
    try {
      await sendJson<void>('POST', '/auth/logout');
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(() => ({ user, checking, signIn, signOut, refresh }), [user, checking, signIn, signOut, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}

/** The name to show for a user. */
export const displayName = (u: User) => u.full_name || u.email;

/** Admins manage accounts and saved plans; viewers read and try plans. */
export const isAdmin = (u: User | null) => u?.role === 'admin';

export const PASSWORD_PAGE = '/account/password';

/**
 * Only for signed-in users; others go to the sign-in page and come back here afterwards. A user with a temporary
 * password is sent to the password page first.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <div className="grid min-h-screen place-items-center text-sm text-muted">Checking sign-in…</div>;
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (user.must_change_password && location.pathname !== PASSWORD_PAGE) return <Navigate to={PASSWORD_PAGE} replace />;
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
