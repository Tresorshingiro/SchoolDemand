/**
 * The backend (FastAPI, backend/app). In development Vite forwards /api to it (vite.config.ts); in production nginx
 * or IIS does. The API sits next to the site (<base>/api, see VITE_BASE in vite.config.ts); VITE_API_URL points
 * elsewhere when the API is on another host.
 *
 * Every call except sign-in needs the session cookie (sent by the browser). A 401 means the session has ended: the
 * AUTH_EXPIRED event lets the sign-in state (auth.tsx) send the user back to the sign-in page.
 */
export const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? `${import.meta.env.BASE_URL}api`;

export const AUTH_EXPIRED = 'auth:expired';
/** A temporary password must be changed first (403 password_change_required): auth.tsx sends the user to the form. */
export const PASSWORD_REQUIRED = 'auth:password-required';

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { credentials: 'include', ...init });
  } catch {
    throw new ApiError('The server could not be reached. Check that the API is running.', 0);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* not JSON */
    }
    if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event(AUTH_EXPIRED));
    if (res.status === 403 && detail === 'password_change_required') {
      window.dispatchEvent(new Event(PASSWORD_REQUIRED));
      detail = 'Please choose a new password first.';
    }
    throw new ApiError(detail, res.status);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const getJson = <T,>(path: string) => request<T>(path);

/** A multipart form (file upload); the browser sets the content type with its boundary. */
export const sendForm = <T,>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form });

export const sendJson = <T,>(method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown) =>
  request<T>(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
