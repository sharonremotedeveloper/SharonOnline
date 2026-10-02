import { NextRequest, NextResponse } from "next/server";
import { ACCESS_COOKIE, buildCookies, CookieSpec, expiredCookies, newSessionClaims, REFRESH_COOKIE, serializeCookie, SESSION_COOKIE, signSession } from "../session";
import { allowedHostsFrom, isSameOriginRequest, SessionUser } from "./handlers";
import { clientIp, Tokens } from "./upstream";

/** Writes plain Set-Cookie headers (see serializeCookie for why not `res.cookies.set`). */
export function applyCookies(res: NextResponse, cookies: CookieSpec[]): NextResponse {
  for (const c of cookies) res.headers.append("Set-Cookie", serializeCookie(c));
  return res;
}

export async function setSession(res: NextResponse, tokens: Tokens, user: SessionUser): Promise<NextResponse> {
  const session = await signSession(newSessionClaims(user.id, user.role));
  return applyCookies(res, buildCookies({ access: tokens.access, refresh: tokens.refresh, session }));
}

export function clearSession(res: NextResponse): NextResponse {
  return applyCookies(res, expiredCookies());
}

export function readAuthCookies(req: NextRequest) {
  return {
    access: req.cookies.get(ACCESS_COOKIE)?.value,
    refresh: req.cookies.get(REFRESH_COOKIE)?.value,
    session: req.cookies.get(SESSION_COOKIE)?.value,
  };
}

export function requestIp(req: NextRequest): string | null {
  return clientIp(req.headers);
}

/** 403 unless an unsafe request demonstrably comes from our own origin. */
export function rejectCrossOrigin(req: NextRequest): NextResponse | null {
  if (isSameOriginRequest(req.method, req.headers, allowedHostsFrom(req.headers))) return null;
  return NextResponse.json({ detail: "Cross-origin request blocked." }, { status: 403 });
}

export function noStore(res: NextResponse): NextResponse {
  res.headers.set("Cache-Control", "no-store");
  // Defence in depth: never let Next's internal cookie-mirroring header (it carries token values) reach the browser.
  res.headers.delete("x-middleware-set-cookie");
  return res;
}
