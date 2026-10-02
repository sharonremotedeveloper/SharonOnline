import { NextRequest, NextResponse } from "next/server";
import { MAX_BODY_BYTES, proxyRequest } from "@/lib/server/handlers";
import { applyCookies, clearSession, noStore, readAuthCookies, rejectCrossOrigin, requestIp } from "@/lib/server/next-helpers";
import { buildCookies, SESSION_COOKIE } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Ctx = { params: { path: string[] } };

/**
 * Authenticated pass-through to the Django API. The browser never holds a token: this handler reads the HttpOnly
 * cookies, attaches `Authorization`, refreshes when needed and forwards. Token-issuing endpoints are not reachable here.
 */
async function handle(req: NextRequest, { params }: Ctx): Promise<NextResponse> {
  const blocked = rejectCrossOrigin(req);
  if (blocked) return blocked;

  const declared = Number(req.headers.get("content-length") || 0);
  if (declared > MAX_BODY_BYTES) return NextResponse.json({ detail: "Request body too large." }, { status: 413 });
  const body = ["GET", "HEAD"].includes(req.method) ? null : await req.arrayBuffer();

  const { access, refresh } = readAuthCookies(req);
  const out = await proxyRequest(
    { method: req.method, segments: params.path, search: req.nextUrl.search, headers: req.headers, body, access, refresh, ip: requestIp(req) },
    fetch
  );

  const res = new NextResponse(out.body as BodyInit | null, { status: out.status });
  if (out.contentType) res.headers.set("Content-Type", out.contentType);
  if (out.retryAfter) res.headers.set("Retry-After", out.retryAfter);

  if (out.clear) return noStore(clearSession(res));
  if (out.newTokens) {
    // Only the tokens rotated. The signed session cookie keeps its own short lifetime and is re-minted (with a fresh
    // role from Django) by /api/session/renew, so it is deliberately left alone here.
    applyCookies(
      res,
      buildCookies({ access: out.newTokens.access, refresh: out.newTokens.refresh, session: "" }).filter((c) => c.name !== SESSION_COOKIE)
    );
  }
  return noStore(res);
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
