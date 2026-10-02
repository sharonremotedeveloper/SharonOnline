import { NextRequest, NextResponse } from "next/server";
import { loginRequest } from "@/lib/server/handlers";
import { noStore, rejectCrossOrigin, requestIp, setSession } from "@/lib/server/next-helpers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Exchanges credentials for HttpOnly session cookies. The browser only ever receives the user profile. */
export async function POST(req: NextRequest) {
  const blocked = rejectCrossOrigin(req);
  if (blocked) return blocked;

  const body = await req.json().catch(() => null);
  const result = await loginRequest(
    { username: body?.username, password: body?.password, ip: requestIp(req) },
    fetch
  );

  if (!result.ok) {
    const res = NextResponse.json(result.body, { status: result.status });
    if (result.retryAfter) res.headers.set("Retry-After", result.retryAfter);
    return noStore(res);
  }
  return noStore(await setSession(NextResponse.json({ user: result.user }), result.tokens, result.user));
}
