/**
 * The backend (FastAPI, backend/app). In development Vite forwards /api to it (vite.config.ts); in production nginx
 * or IIS does. VITE_API_URL points elsewhere when the API is on another host.
 */
export const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api';

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
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
    throw new ApiError(detail, res.status);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const getJson = <T,>(path: string) => request<T>(path);

export const sendJson = <T,>(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown) =>
  request<T>(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
