import { NextRequest, NextResponse } from "next/server";
import { renewSession } from "@/lib/server/handlers";
import { clearSession, noStore, readAuthCookies, requestIp, setSession } from "@/lib/server/next-helpers";
import { dashboardFor, safeNext } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function redirectTo(req: NextRequest, path: string) {
  // Build from the public host (not the internal one) so redirects work behind a proxy.
  const proto = req.headers.get("x-forwarded-proto") || req.nextUrl.protocol.replace(":", "");
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || req.nextUrl.host;
  return NextResponse.redirect(`${proto}://${host}${path}`, 302);
}

/**
 * The middleware sends page navigations here when the short-lived `sharon_session` cookie is missing/expired.
 * We silently re-authenticate from the refresh cookie (the role is re-read from Django) and bounce back, or
 * fall through to /login. Safe to be a GET: it only ever redirects, to a validated same-site path.
 */
export async function GET(req: NextRequest) {
  const next = safeNext(req.nextUrl.searchParams.get("next"), "");
  const { refresh } = readAuthCookies(req);
  const result = await renewSession(refresh, requestIp(req), fetch);

  if ("error" in result) {
    const login = `/login${next ? `?next=${encodeURIComponent(next)}` : ""}`;
    const res = redirectTo(req, login);
    // Only forget the session when the refresh token is genuinely dead, not when the API is merely down.
    return noStore(result.error === "invalid" ? clearSession(res) : res);
  }
  return noStore(await setSession(redirectTo(req, next || dashboardFor(result.user.role)), result.tokens, result.user));
}
