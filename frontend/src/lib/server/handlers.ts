/**
 * Framework-free cores of the session + proxy route handlers (Task 8.4). The `route.ts` files are thin adapters, so
 * every security decision lives here where it can be unit-tested.
 */
import { isSessionRole, SessionRole } from "../session";
import { callUpstream, FetchLike, needsRefresh, refreshTokens, Tokens, upstreamHeaders } from "./upstream";

// ---------- request hygiene ----------

/** Endpoints that return raw tokens must never be reachable from browser JS through the generic proxy. */
const BLOCKED_PROXY_PATHS = ["auth/token/", "auth/token/refresh/", "auth/logout/"];
const SAFE_METHODS = ["GET", "HEAD", "OPTIONS"];
export const MAX_BODY_BYTES = 2 * 1024 * 1024;

/** `['teachers','abc']` -> `teachers/abc/`; null when the path could escape or smuggle anything. */
export function normalizeProxyPath(segments: string[] | undefined): string | null {
  if (!segments || segments.length === 0 || segments.length > 12) return null;
  for (const seg of segments) {
    if (!/^[A-Za-z0-9._~-]{1,128}$/.test(seg) || seg === "." || seg === "..") return null;
  }
  const path = segments.join("/") + "/"; // Django routes all end with a slash; POSTs can't survive APPEND_SLASH redirects
  if (BLOCKED_PROXY_PATHS.includes(path)) return null;
  return path;
}

/**
 * CSRF defence in depth on top of SameSite=Lax: a state-changing request must demonstrably come from our own origin.
 * `allowedHosts` are the host[:port] values this app is served on (Host, X-Forwarded-Host, NEXT_PUBLIC_APP_URL).
 */
export function isSameOriginRequest(method: string, headers: Headers, allowedHosts: string[]): boolean {
  if (SAFE_METHODS.includes(method.toUpperCase())) return true;
  const origin = headers.get("origin");
  if (origin) {
    try {
      return allowedHosts.includes(new URL(origin).host);
    } catch {
      return false;
    }
  }
  return headers.get("sec-fetch-site") === "same-origin";
}

export function allowedHostsFrom(headers: Headers): string[] {
  const hosts = [headers.get("host"), headers.get("x-forwarded-host")];
  if (process.env.NEXT_PUBLIC_APP_URL) {
    try {
      hosts.push(new URL(process.env.NEXT_PUBLIC_APP_URL).host);
    } catch {
      /* ignore malformed config */
    }
  }
  return hosts.filter((h): h is string => !!h);
}

// ---------- generic authenticated proxy ----------

export interface ProxyInput {
  method: string;
  segments: string[] | undefined;
  search: string; // includes leading "?" or ""
  headers: Headers;
  body: ArrayBuffer | null;
  access?: string;
  refresh?: string;
  ip?: string | null;
}

export interface ProxyOutput {
  status: number;
  body: ArrayBuffer | string | null;
  contentType?: string;
  retryAfter?: string;
  /** Present when tokens were rotated during this request: the route must Set-Cookie them. */
  newTokens?: Tokens;
  /** The session is dead: the route must clear all auth cookies. */
  clear?: boolean;
}

function problem(status: number, detail: string, extra: Partial<ProxyOutput> = {}): ProxyOutput {
  return { status, body: JSON.stringify({ detail }), contentType: "application/json", ...extra };
}

export async function proxyRequest(input: ProxyInput, fetchImpl: FetchLike): Promise<ProxyOutput> {
  const path = normalizeProxyPath(input.segments);
  if (!path) return problem(404, "Not found.");
  if (input.body && input.body.byteLength > MAX_BODY_BYTES) return problem(413, "Request body too large.");

  let access = input.access;
  let refresh = input.refresh;
  let rotated: Tokens | undefined;

  // Refresh early (expired/missing/about to expire) rather than burning a request on a guaranteed 401.
  if (refresh && needsRefresh(access)) {
    const fresh = await refreshTokens(refresh, fetchImpl);
    if (!fresh) return problem(401, "Your session has expired. Please sign in again.", { clear: true });
    rotated = fresh;
    access = fresh.access;
    refresh = fresh.refresh;
  }

  const send = (token: string | undefined) =>
    callUpstream(fetchImpl, `/${path}${input.search}`, {
      method: input.method,
      headers: upstreamHeaders({
        access: token,
        ip: input.ip,
        contentType: input.headers.get("content-type"),
        accept: input.headers.get("accept"),
        acceptLanguage: input.headers.get("accept-language"),
      }),
      body: SAFE_METHODS.includes(input.method.toUpperCase()) ? undefined : input.body ?? undefined,
    });

  let res: Response;
  try {
    res = await send(access);
    if (res.status === 401 && refresh && !rotated) {
      const fresh = await refreshTokens(refresh, fetchImpl);
      if (!fresh) return problem(401, "Your session has expired. Please sign in again.", { clear: true });
      rotated = fresh;
      res = await send(fresh.access);
    }
  } catch (err) {
    const timedOut = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
    return problem(timedOut ? 504 : 502, timedOut ? "The server took too long to respond." : "The server is unavailable.", {
      newTokens: rotated,
    });
  }

  const sessionDead = res.status === 401 && !!input.refresh;
  return {
    status: res.status,
    body: res.status === 204 || res.status === 205 ? null : await res.arrayBuffer(),
    contentType: res.headers.get("content-type") || undefined,
    retryAfter: res.headers.get("retry-after") || undefined,
    newTokens: rotated,
    clear: sessionDead,
  };
}

// ---------- login / renew / logout ----------

export interface SessionUser {
  id: string;
  role: SessionRole;
  [key: string]: unknown;
}

export type LoginOutput =
  | { ok: true; user: SessionUser; tokens: Tokens }
  | { ok: false; status: number; body: unknown; retryAfter?: string };

async function fetchMe(access: string, ip: string | null | undefined, fetchImpl: FetchLike): Promise<SessionUser | null> {
  const res = await callUpstream(fetchImpl, "/auth/me/", { method: "GET", headers: upstreamHeaders({ access, ip }) });
  if (!res.ok) return null;
  const user = await res.json();
  return user && typeof user.id === "string" && isSessionRole(user.role) ? (user as SessionUser) : null;
}

export async function loginRequest(
  input: { username: unknown; password: unknown; ip?: string | null },
  fetchImpl: FetchLike
): Promise<LoginOutput> {
  const { username, password } = input;
  if (typeof username !== "string" || typeof password !== "string" || !username || !password || username.length > 150 || password.length > 256) {
    return { ok: false, status: 400, body: { detail: "Username and password are required." } };
  }
  try {
    const res = await callUpstream(fetchImpl, "/auth/token/", {
      method: "POST",
      headers: upstreamHeaders({ contentType: "application/json", ip: input.ip }),
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { ok: false, status: res.status, body: data, retryAfter: res.headers.get("retry-after") || undefined };
    }
    if (!data?.access || !data?.refresh) return { ok: false, status: 502, body: { detail: "Unexpected response from the server." } };
    const user = await fetchMe(data.access, input.ip, fetchImpl);
    if (!user) return { ok: false, status: 502, body: { detail: "Could not load your profile. Please try again." } };
    return { ok: true, user, tokens: { access: data.access, refresh: data.refresh } };
  } catch {
    return { ok: false, status: 502, body: { detail: "The server is unavailable." } };
  }
}

/** Silent renewal: new tokens + a fresh role straight from Django. Null when the refresh token is no longer valid. */
export async function renewSession(
  refresh: string | undefined,
  ip: string | null | undefined,
  fetchImpl: FetchLike
): Promise<{ user: SessionUser; tokens: Tokens } | { error: "invalid" | "unavailable" }> {
  if (!refresh) return { error: "invalid" };
  try {
    const tokens = await refreshTokens(refresh, fetchImpl);
    if (!tokens) return { error: "invalid" };
    const user = await fetchMe(tokens.access, ip, fetchImpl);
    return user ? { user, tokens } : { error: "invalid" };
  } catch {
    return { error: "unavailable" };
  }
}

/** Best-effort server-side revoke; the caller clears cookies regardless of the outcome. */
export async function revokeRefreshToken(refresh: string | undefined, ip: string | null | undefined, fetchImpl: FetchLike): Promise<boolean> {
  if (!refresh) return false;
  try {
    const res = await callUpstream(fetchImpl, "/auth/logout/", {
      method: "POST",
      headers: upstreamHeaders({ contentType: "application/json", ip }),
      body: JSON.stringify({ refresh }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
