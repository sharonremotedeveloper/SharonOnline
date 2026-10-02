/**
 * HTTP core for the Django API.
 *
 * - Attaches the access token, parses DRF errors into a typed `ApiError`.
 * - On a 401 it refreshes the access token ONCE (single-flight, so N parallel calls share one refresh) and retries;
 *   if the refresh fails the session is cleared and the user is sent to /login.
 * - NEVER fabricates data. Fixtures are only reachable when `NEXT_PUBLIC_USE_MOCKS=true` (dev only; the production
 *   build refuses to start with it - see next.config.mjs).
 */
import { clearAuthSession, getStoredTokens, updateStoredTokens } from "./auth";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";

export const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

/** Sentinel returned by `liveRequest` in explicit mock mode when the live call failed. */
export const MOCK = Symbol("mock");

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  /** Per-field validation messages from DRF (`{field: ["msg"]}`), flattened. */
  readonly fieldErrors: Record<string, string[]>;

  constructor(status: number, message: string, body: unknown = null, fieldErrors: Record<string, string[]> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.fieldErrors = fieldErrors;
  }

  /** True when the backend could not be reached at all (status 0). */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

/** Human-readable message for any thrown value (for banners/toasts). */
export function errorMessage(err: unknown, fallback = "Something went wrong. Please try again."): string {
  if (err instanceof ApiError) {
    if (err.isNetworkError) return "We couldn't reach the server. Check your connection and try again.";
    if (err.status === 403) return "You don't have permission to do that.";
    if (err.status === 404) return "We couldn't find what you were looking for.";
    if (err.status >= 500) return "The server hit a problem. Please try again shortly.";
    return err.message || fallback;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** Turn a DRF error payload into a message plus per-field errors. */
export function parseDrfError(status: number, body: unknown): { message: string; fieldErrors: Record<string, string[]> } {
  const fieldErrors: Record<string, string[]> = {};
  let message = `Request failed (${status})`;

  if (typeof body === "string" && body.trim() && !body.trim().startsWith("<")) {
    message = body.trim().slice(0, 300);
  } else if (Array.isArray(body)) {
    message = body.map(String).join(" ");
  } else if (body && typeof body === "object") {
    const obj = body as Record<string, unknown>;
    const parts: string[] = [];
    for (const [key, value] of Object.entries(obj)) {
      const msgs = (Array.isArray(value) ? value : [value]).filter((v) => typeof v === "string") as string[];
      if (!msgs.length) continue;
      if (key === "detail" || key === "error" || key === "message" || key === "non_field_errors") {
        parts.push(...msgs);
      } else {
        fieldErrors[key] = msgs;
        parts.push(...msgs);
      }
    }
    if (parts.length) message = parts.join(" ");
  }
  return { message, fieldErrors };
}

let refreshInFlight: Promise<string | null> | null = null;

/** Exchange the refresh token for a new access token. Returns the new access token or null. */
export function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  const tokens = getStoredTokens();
  if (!tokens?.refresh) return Promise.resolve(null);

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/token/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: tokens.refresh }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      if (!data?.access) return null;
      // ROTATE_REFRESH_TOKENS: the old refresh token is blacklisted, so the new one MUST be stored.
      updateStoredTokens({ access: data.access, refresh: data.refresh || tokens.refresh });
      return data.access as string;
    } catch {
      return null;
    } finally {
      // Allow the next expiry to refresh again (set after the promise settles).
      setTimeout(() => {
        refreshInFlight = null;
      }, 0);
    }
  })();
  return refreshInFlight;
}

function endSession(): void {
  clearAuthSession();
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login?next=${next}`;
  }
}

const AUTH_ENDPOINTS = ["/auth/token/", "/auth/token/refresh/", "/auth/register/", "/auth/logout/"];

async function readBody(res: Response): Promise<unknown> {
  if (res.status === 204 || res.status === 205) return null;
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/**
 * Perform an API request. `url` may be absolute or start with "/" (relative to API_BASE).
 * Resolves with the parsed JSON body (null for 204/205), rejects with `ApiError`.
 */
export async function request<T = any>(url: string, init: RequestInit & { skipAuth?: boolean } = {}): Promise<T> {
  const target = url.startsWith("http") ? url : `${API_BASE}${url}`;
  const isAuthEndpoint = AUTH_ENDPOINTS.some((p) => target.includes(`/api/v1${p}`) || target.endsWith(p));
  const { skipAuth, ...rest } = init;

  const send = async (accessToken: string | null): Promise<Response> => {
    const headers = new Headers(rest.headers);
    if (rest.body && !(rest.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (accessToken && !skipAuth) headers.set("Authorization", `Bearer ${accessToken}`);
    try {
      return await fetch(target, { ...rest, headers });
    } catch (e) {
      throw new ApiError(0, "Network error", e);
    }
  };

  const tokens = getStoredTokens();
  let res = await send(tokens?.access ?? null);

  if (res.status === 401 && tokens?.refresh && !skipAuth && !isAuthEndpoint) {
    const fresh = await refreshAccessToken();
    if (fresh) {
      res = await send(fresh);
    }
    if (!fresh || res.status === 401) {
      endSession();
      throw new ApiError(401, "Your session has expired. Please sign in again.");
    }
  }

  const body = await readBody(res);
  if (!res.ok) {
    const { message, fieldErrors } = parseDrfError(res.status, body);
    throw new ApiError(res.status, message, body, fieldErrors);
  }
  return body as T;
}

/**
 * Live call used by the data layer. Failures THROW an `ApiError` - except in explicit mock mode, where it resolves
 * with the `MOCK` sentinel so the caller can return its dev fixture.
 */
export async function liveRequest(url: string, init: RequestInit & { skipAuth?: boolean } = {}): Promise<any> {
  try {
    return await request(url, init);
  } catch (err) {
    if (USE_MOCKS) {
      console.warn(`[mock mode] ${init.method || "GET"} ${url} failed; serving dev fixture`, err);
      return MOCK;
    }
    throw err;
  }
}
