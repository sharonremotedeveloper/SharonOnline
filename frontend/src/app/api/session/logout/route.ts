import { NextRequest, NextResponse } from "next/server";
import { revokeRefreshToken } from "@/lib/server/handlers";
import { clearSession, noStore, readAuthCookies, rejectCrossOrigin, requestIp } from "@/lib/server/next-helpers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Revokes the refresh token at Django and clears every auth cookie - the user is logged out locally even if Django is down. */
export async function POST(req: NextRequest) {
  const blocked = rejectCrossOrigin(req);
  if (blocked) return blocked;

  const { refresh } = readAuthCookies(req);
  const revoked = await revokeRefreshToken(refresh, requestIp(req), fetch);
  if (refresh && !revoked) console.warn("Logout: refresh token could not be revoked at the API; cookies were cleared anyway.");
  return noStore(clearSession(NextResponse.json({ ok: true })));
}
