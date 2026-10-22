/**
 * Single sign-on with the MINEDUC GIS portal (ArcGIS Enterprise, gh.space.gov.rw/portal), through the portal's OAuth
 * sign-in (authorization code with PKCE).
 *
 * When the dashboard is served from the portal's own site (https://gh.space.gov.rw/school/, also inside Education
 * Mapping's frame) a page that needs a session sends the browser to the portal's oauth2/authorize for the dashboard's
 * registered app (client ID below). A user already signed in to the portal comes straight back (the first time the
 * portal asks them to Allow the app, unless an administrator approved it for everyone); others sign in on the portal's
 * page. Back on https://gh.space.gov.rw/school/ (a redirect URL of the app) the one-time code is exchanged for a token,
 * the API checks that token with the portal (POST /api/auth/portal-token) and opens our own session; the token is not
 * kept. Anywhere else (gis.mineduc.gov.rw, development) the sign-in form is used.
 *
 * (The portal's oauth2/platformSelf, which would avoid the redirect, refuses this app: OAUTH_0068 "Invalid client_id".)
 */
export const PORTAL_URL = ((import.meta.env.VITE_PORTAL_URL as string | undefined) ?? 'https://gh.space.gov.rw/portal')
  .replace(/\/$/, '');
// The "School Demand & Demographics" application item in the portal (not a secret)
const CLIENT_ID = (import.meta.env.VITE_PORTAL_CLIENT_ID as string | undefined) ?? 'zCxgnSvJJTL8iCD1';
const REDIRECT_URI = () => `${window.location.origin}${import.meta.env.BASE_URL}`; // registered in the app item

// sessionStorage (this tab): the sign-in under way, and whether the portal sign-in is off or has failed
const PENDING_KEY = 'school-portal-sign-in';
const OFF_KEY = 'school-portal-sign-in-off'; // set by signing out, until the user asks for it again
const FAILED_KEY = 'school-portal-sign-in-failed'; // refused or cancelled: the form is shown instead

interface Pending {
  state: string;
  verifier: string;
  next: string; // the page asked for, inside the site ("/dashboard")
}

const read = (key: string): string | null => {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
};
const write = (key: string, value: string | null) => {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the sign-in form is used */
  }
};

/** Is the dashboard on the portal's site, where the portal's sign-in can be used? */
export function portalSignInAvailable(): boolean {
  try {
    return !!CLIENT_ID && new URL(PORTAL_URL).origin === window.location.origin && !!window.crypto?.subtle;
  } catch {
    return false;
  }
}

/** Should a page that needs a session go to the portal's sign-in (rather than the form)? */
export const portalSignInOn = () => portalSignInAvailable() && read(OFF_KEY) !== '1' && read(FAILED_KEY) !== '1';

export const portalSignInFailed = () => read(FAILED_KEY) === '1';

/** Signing out turns the portal sign-in off for this tab; the sign-in page's button turns it on again. */
export function setPortalSignInOff(off: boolean): void {
  write(OFF_KEY, off ? '1' : null);
  if (!off) write(FAILED_KEY, null);
}

const base64url = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const random = (n: number) => base64url(crypto.getRandomValues(new Uint8Array(n)));

let leaving = false; // StrictMode runs effects twice: one trip to the portal

/** Go to the portal's sign-in; the browser comes back to the site's base with a code (finishPortalSignIn). */
export async function startPortalSignIn(next: string): Promise<void> {
  if (leaving) return;
  leaving = true;
  const verifier = random(48);
  const challenge = base64url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  const pending: Pending = { state: random(16), verifier, next };
  write(PENDING_KEY, JSON.stringify(pending));
  const q = new URLSearchParams({
    client_id: CLIENT_ID, response_type: 'code', redirect_uri: REDIRECT_URI(), state: pending.state,
    code_challenge: challenge, code_challenge_method: 'S256', expiration: '20',
  });
  window.location.assign(`${PORTAL_URL}/sharing/rest/oauth2/authorize?${q}`);
}

/** Is this page the portal sending the browser back (code or error in the address)? */
export function returningFromPortal(): boolean {
  const q = new URLSearchParams(window.location.search);
  return !!read(PENDING_KEY) && (q.has('code') || q.has('error'));
}

let finishing: Promise<{ token: string | null; next: string }> | null = null;

/**
 * Back from the portal: the portal token for the code in the address (null when refused, cancelled or not ours), and
 * the page that was asked for. A failure turns the portal sign-in off for this tab, so the form is shown.
 */
export function finishPortalSignIn(): Promise<{ token: string | null; next: string }> {
  finishing ??= (async () => {
    const q = new URLSearchParams(window.location.search);
    let pending: Pending | null = null;
    try {
      pending = JSON.parse(read(PENDING_KEY) ?? 'null') as Pending | null;
    } catch {
      /* unreadable */
    }
    write(PENDING_KEY, null);
    const next = pending?.next ?? '/dashboard';
    const code = q.get('code');
    if (!pending || !code || q.get('state') !== pending.state) {
      write(FAILED_KEY, '1');
      return { token: null, next };
    }
    try {
      const res = await fetch(`${PORTAL_URL}/sharing/rest/oauth2/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: CLIENT_ID, grant_type: 'authorization_code', code, redirect_uri: REDIRECT_URI(),
          code_verifier: pending.verifier, f: 'json',
        }),
      });
      const body = (await res.json()) as { access_token?: unknown };
      if (typeof body.access_token === 'string' && body.access_token) return { token: body.access_token, next };
    } catch {
      /* portal unreachable */
    }
    write(FAILED_KEY, '1');
    return { token: null, next };
  })();
  return finishing;
}

/** The address of a page of the site ("/dashboard" -> "/school/dashboard"). */
export const sitePath = (next: string) => `${import.meta.env.BASE_URL}${next.replace(/^\//, '')}`;
