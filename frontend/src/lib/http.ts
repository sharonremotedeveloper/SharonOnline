/**
 * Browser/server HTTP client for the Django API.
 *
 * - In the browser every call goes to our own origin (`/api/proxy/...`). The proxy route handler holds the HttpOnly
 *   auth cookies, attaches the token, refreshes it when needed and forwards to Django - this code never sees a token.
 * - On the server (SSR of public pages) it calls Django directly, unauthenticated.
 * - Failures THROW a typed `ApiError`. It NEVER fabricates data. Fixtures are only reachable when
 *   `NEXT_PUBLIC_USE_MOCKS=true` (dev only; the production build refuses to start with it - see next.config.mjs).
 */
import { LEGACY_COOKIES } from "./session";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";

export const PROXY_BASE = "/api/proxy";

export const API_BASE =
  typeof window === "undefined"
    ? (process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "")
    : PROXY_BASE;

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

  /** True when the server could not be reached at all (status 0) or answered 502/504 from the proxy. */
  get isNetworkError(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 504;
  }
}

/** Human-readable message for any thrown value (for banners/toasts). */
export function errorMessage(err: unknown, fallback = "Something went wrong. Please try again."): string {
  if (err instanceof ApiError) {
    if (err.isNetworkError) return "We couldn't reach the server. Check your connection and try again.";
    if (err.status === 403) return "You don't have permission to do that.";
    if (err.status === 404) return "We couldn't find what you were looking for.";
    if (err.status === 429) return "Too many requests. Please wait a moment and try again.";
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

function endSession(): void {
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login?next=${next}`;
  }
}

/** One-time cleanup of the tokens/cookies the previous (JS-readable) implementation left in the browser. */
export function purgeLegacyBrowserSession(): void {
  if (typeof window === "undefined") return;
  try {
    for (const key of ["access_token", "refresh_token", "user_role", "user_profile"]) window.localStorage.removeItem(key);
  } catch {
    /* storage unavailable */
  }
  if (typeof document !== "undefined") {
    for (const name of LEGACY_COOKIES) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
  }
}

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
 * Next.js 308-redirects `/api/proxy/x/` to `/api/proxy/x`, which would double every API round trip. The browser therefore
 * asks the proxy for the slash-less form; the proxy handler re-adds the slash Django's routes require.
 */
export function stripProxyTrailingSlash(url: string): string {
  if (!url.startsWith(`${PROXY_BASE}/`)) return url;
  const q = url.indexOf("?");
  const path = q === -1 ? url : url.slice(0, q);
  const query = q === -1 ? "" : url.slice(q);
  return path.replace(/\/+$/, "") + query;
}

function resolve(url: string): string {
  if (/^https?:\/\//.test(url) || url.startsWith("/api/")) return stripProxyTrailingSlash(url);
  return stripProxyTrailingSlash(`${API_BASE}${url}`);
}

/**
 * Perform an API request. `url` may be absolute, an app route (`/api/session/...`), or start with "/" relative to the API.
 * Resolves with the parsed JSON body (null for 204/205), rejects with `ApiError`.
 * `skipAuth` marks calls where a 401 is an expected answer (login, session probe) rather than "your session died".
 */
export async function request<T = any>(url: string, init: RequestInit & { skipAuth?: boolean } = {}): Promise<T> {
  const { skipAuth, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (rest.body && !(rest.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(resolve(url), { ...rest, headers, credentials: "same-origin" });
  } catch (e) {
    throw new ApiError(0, "Network error", e);
  }

  const body = await readBody(res);
  if (!res.ok) {
    // The proxy already tried to refresh; a 401 here means the session is genuinely over (cookies were cleared).
    if (res.status === 401 && !skipAuth) {
      endSession();
      throw new ApiError(401, "Your session has expired. Please sign in again.", body);
    }
    const { message, fieldErrors } = parseDrfError(res.status, body);
    throw new ApiError(res.status, message, body, fieldErrors);
  }
  return body as T;
}

/**
 * Fetch a file (PDF, CSV) through the same proxy and hand it to the browser as a download. Rejects with `ApiError` exactly
 * like `request`, so a wrong password or a refused action shows the server's message instead of a broken file.
 */
export async function downloadFile(url: string, filename: string, init: RequestInit = {}): Promise<void> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(resolve(url), { ...init, headers, credentials: "same-origin" });
  } catch (e) {
    throw new ApiError(0, "Network error", e);
  }
  if (!res.ok) {
    const body = await readBody(res);
    if (res.status === 401) {
      endSession();
      throw new ApiError(401, "Your session has expired. Please sign in again.", body);
    }
    const { message, fieldErrors } = parseDrfError(res.status, body);
    throw new ApiError(res.status, message, body, fieldErrors);
  }
  const href = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(href);
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
