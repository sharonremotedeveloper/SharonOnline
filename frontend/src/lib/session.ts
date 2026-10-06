/**
 * Session primitives shared by the Edge middleware and the Node route handlers (Web Crypto only, no Node APIs).
 *
 * Model (Task 8.4):
 *  - The Django JWTs live ONLY in HttpOnly cookies set by our route handlers; browser JS never sees them.
 *  - `sharon_session` is a short-lived cookie signed with SESSION_SECRET (a secret only the Next server holds - never
 *    Django's SECRET_KEY). It carries just {uid, role, exp}. The middleware verifies it locally (no network call) and
 *    uses the role for routing. It is minted ONLY after Django has authenticated the user, and re-minted from Django's
 *    answer on every renew, so the role can be at most SESSION_TTL_SECONDS stale. The backend remains the real
 *    security boundary - it re-checks the role from the database on every API request.
 */

export const SESSION_COOKIE = "sharon_session";
export const ACCESS_COOKIE = "sharon_access";
export const REFRESH_COOKIE = "sharon_refresh";

export const SESSION_TTL_SECONDS = 15 * 60;
export const ACCESS_TTL_SECONDS = 15 * 60;
export const REFRESH_TTL_SECONDS = 14 * 24 * 60 * 60;

/** Cookies that the previous (JS-readable) implementation set; removed on first load after upgrade. */
export const LEGACY_COOKIES = ["sharon_access_token", "sharon_refresh_token", "sharon_user_role"];

export type SessionRole = "student" | "teacher" | "admin";
const ROLES: SessionRole[] = ["student", "teacher", "admin"];

export interface SessionClaims {
  uid: string;
  role: SessionRole;
  tutor_status?: string | null;
  /** Expiry, seconds since epoch. */
  exp: number;
}

const DEV_SECRET = "dev-only-session-secret-not-for-production-0123456789";
const encoder = new TextEncoder();

export function getSessionSecret(): string {
  const configured = process.env.SESSION_SECRET;
  if (configured && configured.length >= 32) return configured;
  if (process.env.NODE_ENV !== "production") return DEV_SECRET;
  throw new Error("SESSION_SECRET (at least 32 characters) must be set in production.");
}

function toB64Url(bytes: Uint8Array): string {
  let bin = "";
  bytes.forEach((b) => {
    bin += String.fromCharCode(b);
  });
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64Url(value: string): Uint8Array {
  const pad = value.length % 4 ? "=".repeat(4 - (value.length % 4)) : "";
  const bin = atob(value.replace(/-/g, "+").replace(/_/g, "/") + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function hmacKey(): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", encoder.encode(getSessionSecret()), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);
}

export async function signSession(claims: SessionClaims): Promise<string> {
  const payload = toB64Url(encoder.encode(JSON.stringify(claims)));
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(), encoder.encode(payload));
  return `${payload}.${toB64Url(new Uint8Array(sig))}`;
}

/** Returns the claims if the cookie is authentic, well-formed and unexpired; otherwise null. */
export async function verifySession(token: string | undefined | null, nowSeconds = Date.now() / 1000): Promise<SessionClaims | null> {
  if (!token || token.length > 2048) return null;
  const parts = token.split(".");
  if (parts.length !== 2) return null;
  try {
    const ok = await crypto.subtle.verify(
      "HMAC",
      await hmacKey(),
      fromB64Url(parts[1]) as BufferSource,
      encoder.encode(parts[0])
    );
    if (!ok) return null;
    const claims = JSON.parse(new TextDecoder().decode(fromB64Url(parts[0])));
    if (
      typeof claims?.uid !== "string" ||
      !ROLES.includes(claims?.role) ||
      typeof claims?.exp !== "number" ||
      claims.exp <= nowSeconds
    ) {
      return null;
    }
    return { uid: claims.uid, role: claims.role, ...(typeof claims.tutor_status === "string" ? { tutor_status: claims.tutor_status } : {}), exp: claims.exp };
  } catch {
    return null;
  }
}

export function newSessionClaims(uid: string, role: SessionRole, nowSeconds = Date.now() / 1000, tutorStatus?: string | null): SessionClaims {
  return { uid, role, ...(tutorStatus ? { tutor_status: tutorStatus } : {}), exp: Math.floor(nowSeconds) + SESSION_TTL_SECONDS };
}

export function isSessionRole(value: unknown): value is SessionRole {
  return typeof value === "string" && (ROLES as string[]).includes(value);
}

export interface CookieSpec {
  name: string;
  value: string;
  httpOnly: true;
  sameSite: "lax";
  secure: boolean;
  path: string;
  maxAge: number;
}

function secureCookies(): boolean {
  if (process.env.SESSION_COOKIE_SECURE === "false") return false;
  return process.env.NODE_ENV === "production";
}

/** Tokens are only ever sent to our own /api routes; the session cookie is needed by page navigations. */
export function buildCookies(input: { access: string; refresh: string; session: string }): CookieSpec[] {
  const base = { httpOnly: true as const, sameSite: "lax" as const, secure: secureCookies() };
  return [
    { ...base, name: ACCESS_COOKIE, value: input.access, path: "/api", maxAge: ACCESS_TTL_SECONDS },
    { ...base, name: REFRESH_COOKIE, value: input.refresh, path: "/api", maxAge: REFRESH_TTL_SECONDS },
    { ...base, name: SESSION_COOKIE, value: input.session, path: "/", maxAge: SESSION_TTL_SECONDS },
  ];
}

const COOKIE_VALUE = /^[A-Za-z0-9._~-]*$/;

/**
 * Serialise one Set-Cookie header value ourselves. We deliberately do NOT use Next's `response.cookies.set()`: it also
 * mirrors every cookie into an `x-middleware-set-cookie` response header, which browser JS can read - that would hand
 * the refresh token to any XSS and defeat HttpOnly.
 */
export function serializeCookie(c: CookieSpec): string {
  if (!COOKIE_VALUE.test(c.value)) throw new Error(`Refusing to serialise cookie ${c.name}: unexpected characters in value`);
  const parts = [`${c.name}=${c.value}`, `Path=${c.path}`, `Max-Age=${c.maxAge}`];
  if (c.maxAge <= 0) parts.push("Expires=Thu, 01 Jan 1970 00:00:00 GMT");
  parts.push("HttpOnly", "SameSite=Lax");
  if (c.secure) parts.push("Secure");
  return parts.join("; ");
}

export function expiredCookies(): CookieSpec[] {
  return buildCookies({ access: "", refresh: "", session: "" }).map((c) => ({ ...c, maxAge: 0 }));
}

/** Same-site relative paths only ("/x"). Rejects "//host", "/\\host", absolute URLs, control chars and API paths. */
export function safeNext(value: string | null | undefined, fallback = "/"): string {
  if (!value || value.length > 512) return fallback;
  if (!/^\/(?![/\\])/.test(value)) return fallback;
  if (/[\u0000-\u001f\u007f]/.test(value)) return fallback;
  if (value.startsWith("/api/")) return fallback;
  return value;
}

export function dashboardFor(role: SessionRole): string {
  return role === "admin" ? "/admin/dashboard" : role === "teacher" ? "/teacher/dashboard" : "/student/dashboard";
}

/** Read the `exp` claim of a JWT WITHOUT verifying it - only used to decide when to refresh early. */
export function decodeJwtExp(token: string | undefined | null): number | null {
  if (!token) return null;
  try {
    const payload = JSON.parse(new TextDecoder().decode(fromB64Url(token.split(".")[1] || "")));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}
