/**
 * Server-side access to the Django API for the session/proxy route handlers.
 * Everything takes an injectable `fetch` so it can be unit-tested without a network.
 */
import { decodeJwtExp } from "../session";

export interface Tokens {
  access: string;
  refresh: string;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

const UPSTREAM_TIMEOUT_MS = 25_000;

export function upstreamBase(): string {
  return (process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");
}

/**
 * The real client IP, so Django's per-IP throttles (login, register...) key on the user and not on this server.
 * Only the entry added by the Nth trusted proxy from the right can be believed; with TRUSTED_PROXY_COUNT=0 (default,
 * e.g. local dev) we don't claim to know.
 */
export function clientIp(headers: Headers, trusted: number = Number(process.env.TRUSTED_PROXY_COUNT || 0)): string | null {
  if (!trusted || trusted < 1) return null;
  const chain = (headers.get("x-forwarded-for") || "")
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  if (chain.length === 0) return null;
  return chain[Math.max(chain.length - trusted, 0)] || null;
}

export function upstreamHeaders(opts: { access?: string | null; ip?: string | null; contentType?: string | null; accept?: string | null; acceptLanguage?: string | null }): Headers {
  const h = new Headers();
  h.set("Accept", opts.accept || "application/json");
  if (opts.contentType) h.set("Content-Type", opts.contentType);
  if (opts.acceptLanguage) h.set("Accept-Language", opts.acceptLanguage);
  if (opts.access) h.set("Authorization", `Bearer ${opts.access}`);
  // A single, trusted value: Django (THROTTLE_NUM_PROXIES=1) reads it as the client address.
  if (opts.ip) h.set("X-Forwarded-For", opts.ip);
  return h;
}

export async function callUpstream(fetchImpl: FetchLike, path: string, init: RequestInit): Promise<Response> {
  const signal = typeof AbortSignal !== "undefined" && "timeout" in AbortSignal ? AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) : undefined;
  return fetchImpl(`${upstreamBase()}${path}`, { ...init, signal, redirect: "manual", cache: "no-store" } as RequestInit);
}

// ---- refresh (single-flight, with a short memory of the result) ----
// ROTATE_REFRESH_TOKENS blacklists the old refresh token on use, so N parallel requests that each tried to refresh with
// the same cookie would make N-1 of them fail and log the user out. Share one refresh per refresh token, and remember the
// outcome briefly so requests that were already in flight with the OLD cookie get the NEW pair instead of an error.
const RESULT_MEMORY_MS = 10_000;
const refreshes = new Map<string, Promise<Tokens | null>>();

export function refreshTokens(refresh: string, fetchImpl: FetchLike = fetch as FetchLike): Promise<Tokens | null> {
  const existing = refreshes.get(refresh);
  if (existing) return existing;

  const attempt = (async (): Promise<Tokens | null> => {
    try {
      const res = await callUpstream(fetchImpl, "/auth/token/refresh/", {
        method: "POST",
        headers: upstreamHeaders({ contentType: "application/json" }),
        body: JSON.stringify({ refresh }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      if (!data?.access) return null;
      return { access: data.access, refresh: data.refresh || refresh };
    } catch {
      return null;
    }
  })();

  refreshes.set(refresh, attempt);
  void attempt.then((result) => {
    // Failures are forgotten at once (so a retry can happen); successes are remembered for the race window.
    const timer = setTimeout(() => refreshes.delete(refresh), result ? RESULT_MEMORY_MS : 0) as unknown as { unref?: () => void };
    timer.unref?.();
  });
  return attempt;
}

/** Test hook. */
export function _resetRefreshState() {
  refreshes.clear();
}

/** True when there is no usable access token or it expires within `skewSeconds`. */
export function needsRefresh(access: string | undefined | null, skewSeconds = 30, nowSeconds = Date.now() / 1000): boolean {
  if (!access) return true;
  const exp = decodeJwtExp(access);
  return exp === null || exp - nowSeconds <= skewSeconds;
}
