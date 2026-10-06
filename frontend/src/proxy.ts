import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { dashboardFor, SESSION_COOKIE, verifySession } from "@/lib/session";

/**
 * Route guard (Next 16 `proxy`, formerly `middleware`) for /student, /teacher and /admin (UI routing only - the Django API re-checks the role from the
 * database on every request and is the real security boundary).
 *
 * The role comes from `sharon_session`, an HttpOnly cookie signed with SESSION_SECRET that we only mint after Django
 * has authenticated the user. A user can no longer promote themselves by editing a cookie: a forged or tampered value
 * fails verification. When the short-lived session is missing/expired we bounce through /api/session/renew, which
 * silently re-authenticates from the refresh cookie or lands on /login.
 */
export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const claims = await verifySession(request.cookies.get(SESSION_COOKIE)?.value);

  if (!claims) {
    const renew = request.nextUrl.clone();
    renew.pathname = "/api/session/renew";
    renew.search = "";
    renew.searchParams.set("next", pathname + search);
    return NextResponse.redirect(renew);
  }

  const wanted = pathname.startsWith("/admin") ? "admin" : pathname.startsWith("/teacher") ? "teacher" : "student";
  if (claims.role !== wanted) {
    const home = request.nextUrl.clone();
    home.pathname = dashboardFor(claims.role);
    home.search = "";
    return NextResponse.redirect(home);
  }

  if (
    claims.role === "teacher" &&
    (claims.tutor_status === "applied" || claims.tutor_status === "changes_requested") &&
    pathname !== "/teacher/apply" &&
    !pathname.startsWith("/teacher/apply/")
  ) {
    const apply = request.nextUrl.clone();
    apply.pathname = "/teacher/apply";
    apply.search = "";
    return NextResponse.redirect(apply);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/student/:path*", "/teacher/:path*", "/admin/:path*"],
};
