# Phase 8 - Task 8.4: HttpOnly cookie sessions (reference)

**Date:** 2026-10-02 · **Status:** implemented and verified live (dev + production build) · **Replaces:** JWTs in `localStorage` + JS-set cookies + a client-controlled `sharon_user_role` cookie.

## 1. Model

```
Browser  ──cookies (HttpOnly)──►  Next.js server  ──Authorization: Bearer──►  Django API
 JS sees:  user profile only      /api/session/*  login, logout, me, renew
           (never a token)        /api/proxy/*    authenticated pass-through
                                  proxy.ts        verifies signed session cookie
```

| Cookie | Holds | Path | Lifetime | Who reads it |
| :--- | :--- | :--- | :--- | :--- |
| `sharon_access` | Django access JWT | `/api` | 15 min | proxy only |
| `sharon_refresh` | Django refresh JWT | `/api` | 14 days | proxy + session routes only |
| `sharon_session` | `{uid, role, exp}` signed with `SESSION_SECRET` (HMAC-SHA256) | `/` | 15 min | `proxy.ts` (was `middleware.ts`) |

All: `HttpOnly`, `SameSite=Lax`, `Secure` in production (`SESSION_COOKIE_SECURE=false` only for plain-http staging).

**Why a separate signed session cookie?** The middleware needs the role on every page navigation without a network call and without sharing Django's `SECRET_KEY` with the frontend. The cookie is minted only after Django has authenticated the user (role copied from `/auth/me/`), and re-minted from Django's answer by `/api/session/renew`, so role staleness is bounded by 15 minutes. It is routing UX only: Django re-checks the role from the database on every request.

## 2. Flows

- **Login** `POST /api/session/login` → Django `/auth/token/` + `/auth/me/` → sets the three cookies → returns `{user}` (no tokens in body or headers).
- **Page navigation** (`/student|teacher|admin/*`): middleware verifies `sharon_session`; missing/expired/forged → `/api/session/renew?next=…` → silent re-auth from the refresh cookie (rotating it) and redirect back, or `/login?next=…`. Wrong role → own dashboard.
- **API calls**: browser → `/api/proxy/<path>` (no trailing slash; the proxy re-adds it for Django). Proxy attaches the token, refreshes early if it expires within 30 s, retries once on 401, passes through status/`Retry-After`. Dead refresh token → 401 + cookies cleared → client redirects to `/login?next=`.
- **Logout** `POST /api/session/logout` → Django blacklists the refresh token (authenticated by the token itself) → cookies cleared.

## 3. Security properties and where they are enforced / tested

| Property | Enforced in | Tests |
| :--- | :--- | :--- |
| Browser JS never sees a token (cookies HttpOnly; none in bodies/headers) | `session.ts` `serializeCookie`, route handlers | `session.test.ts`; manual: no `eyJ` outside `Set-Cookie` on a `next start` build |
| Forged / tampered / expired role cookie rejected | `verifySession` | `session.test.ts` (tamper, bad sig, other secret, bad role, expiry) |
| Token-issuing endpoints unreachable via proxy | `normalizeProxyPath` | `handlers.test.ts` |
| Path traversal / smuggling in proxy path | `normalizeProxyPath` | `handlers.test.ts` |
| CSRF on state-changing calls (on top of SameSite=Lax) | `isSameOriginRequest` | `handlers.test.ts`; live: foreign/no Origin → 403 |
| Client's own `Authorization`/`Cookie`/`Host`/`X-Forwarded-For` never forwarded | `upstreamHeaders` | `handlers.test.ts` |
| Concurrent refreshes don't burn the rotated token | `refreshTokens` single-flight + 10 s result memory | `handlers.test.ts` |
| Open redirects via `next` | `safeNext` (login page, renew route) | `session.test.ts`; live |
| Real client IP reaches Django's throttles | `clientIp` + `TRUSTED_PROXY_COUNT` | `handlers.test.ts` |
| Production refuses a missing/weak `SESSION_SECRET` | `getSessionSecret` | `session.test.ts` |
| Legacy tokens removed from `localStorage`/JS cookies on first load | `purgeLegacyBrowserSession` | `http.test.ts` |

Mutation-checked: removing signature verification, unblocking the token endpoints, and accepting any Origin each make tests fail.

## 4. Configuration

| Var | Where | Meaning |
| :--- | :--- | :--- |
| `SESSION_SECRET` | Next.js server | **Required in production**, ≥ 32 chars, never Django's key |
| `TRUSTED_PROXY_COUNT` | Next.js server | Proxies in front of Next; `0` = client IP unknown → Django sees Next's IP (all users share one login throttle) |
| `THROTTLE_NUM_PROXIES=1` | Django | Next.js is the proxy in front of Django (the production guard already requires ≥ 1) |
| `SESSION_COOKIE_SECURE=false` | Next.js server | Plain-http staging only |
| `INTERNAL_API_URL` | Next.js server | Django base URL for the proxy (container network) |

Django: `ACCESS_TOKEN_LIFETIME` is now 15 minutes (the Task 7.7 follow-up).

## 5. Known limits

- **Refresh race across instances.** Single-flight is per Node process. With several Next instances, two simultaneous refreshes of the same token can still collide (the second hits the blacklist → user bounced to login). Mitigations if it shows up: sticky sessions, or a shared (Redis) single-flight lock.
- **Role staleness** ≤ 15 min in the UI (the API is always current).
- **Mock mode** (`NEXT_PUBLIC_USE_MOCKS`) no longer provides fake logins: protected pages need a real backend. Public pages still use fixtures.
- **Rate limiting of `/api/session/*` and `/api/proxy/*`** itself is delegated to Django's throttles (the proxy forwards the real IP). Add edge/WAF limits at deploy time.
- The Next.js server is now a hard dependency of every API call (previously the browser could reach Django directly): deploy it with health checks and ≥ 2 instances.
- `sharon_refresh` cookie `Max-Age` slides forward on `/api/session/me`; the JWT inside still expires at its absolute 14 days.

## 6. Bug found during verification (ERR-009)

Next's `NextResponse.cookies.set()` mirrors cookies into an `x-middleware-set-cookie` response header readable by JS - including in production builds. Replaced with our own `Set-Cookie` serialisation; verified absent on a rebuilt `next start`. Always check raw response headers, not only the browser's cookie jar.


> **Next 16 note (Task 8.9):** `middleware.ts` became `src/proxy.ts` (exported `proxy`), which runs on the Node.js runtime; `verifySession` uses the global Web Crypto `crypto.subtle`, available in both runtimes. Route-handler `params` are now a Promise.
