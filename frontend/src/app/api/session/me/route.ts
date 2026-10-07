import { NextRequest, NextResponse } from "next/server";
import { proxyRequest } from "@/lib/server/handlers";
import { clearSession, noStore, readAuthCookies, requestIp, setSession } from "@/lib/server/next-helpers";
import { isSessionRole } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Current user from Django (auto-refreshing the tokens) and a re-minted session cookie carrying the fresh role. */
export async function GET(req: NextRequest) {
  const { access, refresh } = readAuthCookies(req);
  // Anonymous visitors are a normal state, not an error: answer 200 with no user so the browser console stays clean.
  if (!access && !refresh) return noStore(NextResponse.json({ user: null }));

  const out = await proxyRequest(
    { method: "GET", segments: ["auth", "me"], search: "", headers: req.headers, body: null, access, refresh, ip: requestIp(req) },
    fetch
  );

  if (out.status !== 200 || out.body === null) {
    const res = NextResponse.json(
      out.status === 401 ? { detail: "Not signed in." } : { detail: "Could not load your session." },
      { status: out.status === 200 ? 502 : out.status }
    );
    return noStore(out.clear ? clearSession(res) : res);
  }

  const text = typeof out.body === "string" ? out.body : new TextDecoder().decode(out.body);
  const user = JSON.parse(text);
  if (!user?.id || !isSessionRole(user.role)) {
    return noStore(NextResponse.json({ detail: "Could not load your session." }, { status: 502 }));
  }
  const res = NextResponse.json({ user });
  const tokens = out.newTokens ?? { access: access!, refresh: refresh! };
  return noStore(await setSession(res, tokens, user));
}
