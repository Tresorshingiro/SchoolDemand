/**
 * Sign-in through the MINEDUC GIS portal (ArcGIS Enterprise, gh.space.gov.rw/portal): the portal's OAuth sign-in
 * (implicit grant) for the dashboard's registered app (client ID below).
 *
 * A page that needs a session sends the browser to the portal's oauth2/authorize. A user already signed in to the
 * portal comes straight back; others sign in on the portal's page. The portal returns to the site's base
 * (https://gh.space.gov.rw/school/, a redirect URL of the app) with a token in the address; the page removes it from the
 * address, the API checks it with the portal (POST /api/auth/portal-token) and opens our own session; the token is not
 * kept. Signing out ends our session and the portal's (oauth2/signout).
 */
export const PORTAL_URL = ((import.meta.env.VITE_PORTAL_URL as string | undefined) ?? 'https://gh.space.gov.rw/portal')
  .replace(/\/+$/, '');
// The "School Demand & Demographics" application item in the portal (not a secret)
const CLIENT_ID = (import.meta.env.VITE_PORTAL_CLIENT_ID as string | undefined) ?? 'zCxgnSvJJTL8iCD1';
const EXPIRATION = 60; // minutes the portal token is valid; it is only used once, to open our session

/** Where the portal sends the browser back: the site's base, registered in the app item. */
const redirectUri = () => new URL(import.meta.env.BASE_URL, window.location.origin).toString();

/** The portal's sign-in page for the dashboard. */
export function authorizeUrl(): string {
  const url = new URL(`${PORTAL_URL}/sharing/rest/oauth2/authorize`);
  url.searchParams.set('client_id', CLIENT_ID);
  url.searchParams.set('response_type', 'token');
  url.searchParams.set('expiration', String(EXPIRATION));
  url.searchParams.set('redirect_uri', redirectUri());
  return url.toString();
}

/** The portal's sign-out, coming back to the site. */
export function signOutUrl(): string {
  const url = new URL(`${PORTAL_URL}/sharing/rest/oauth2/signout`);
  url.searchParams.set('redirect_uri', redirectUri());
  url.searchParams.set('client_id', CLIENT_ID);
  return url.toString();
}

/**
 * Back from the portal: the token (or error) it put in the address, removed from the address so it is not kept in the
 * history or bookmarked. Both null on an ordinary visit.
 */
export function takeReturn(): { token: string | null; error: string | null } {
  const url = new URL(window.location.href);
  const hash = new URLSearchParams(url.hash.replace(/^#/, ''));
  const query = url.searchParams;
  const token = hash.get('access_token') ?? hash.get('token') ?? query.get('token');
  const error = hash.get('error_description') ?? hash.get('error') ?? query.get('error');
  if (!token && !error) return { token: null, error: null };
  for (const key of ['access_token', 'token', 'expires_in', 'username', 'ssl', 'persist', 'error', 'error_description']) {
    hash.delete(key);
    query.delete(key);
  }
  const rest = hash.toString();
  url.hash = rest ? `#${rest}` : '';
  window.history.replaceState(null, '', url.toString());
  return { token, error };
}
