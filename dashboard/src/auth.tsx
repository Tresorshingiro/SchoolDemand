/**
 * Who is signed in. The session itself is an HttpOnly cookie set by the API (POST /api/auth/login), so the page never
 * sees a token: it asks /api/auth/me on load and after sign-in / sign-out.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { AUTH_EXPIRED, ApiError, getJson, sendJson } from './api';

export interface User {
  id: number;
  email: string;
  full_name: string | null;
}

interface AuthState {
  user: User | null;
  checking: boolean; // the first /auth/me has not answered yet
  signIn: (email: string, password: string, remember: boolean) => Promise<User>;
  signOut: () => Promise<void>;
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
    window.addEventListener(AUTH_EXPIRED, expired);
    return () => window.removeEventListener(AUTH_EXPIRED, expired);
  }, []);

  const signIn = useCallback(async (email: string, password: string, remember: boolean) => {
    const u = await sendJson<User>('POST', '/auth/login', { email, password, remember });
    setUser(u);
    return u;
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

  const value = useMemo(() => ({ user, checking, signIn, signOut }), [user, checking, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}

/** The name to show for a user. */
export const displayName = (u: User) => u.full_name || u.email;

/** Only for signed-in users; others go to the sign-in page and come back here afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <div className="grid min-h-screen place-items-center text-sm text-muted">Checking sign-in…</div>;
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

/** Where to go after sign-in: the page the user asked for (same site only), else the dashboard. */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/login') ? next : '/dashboard';
}
