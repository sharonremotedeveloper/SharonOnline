import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("sharon_access_token")?.value;
  const role = request.cookies.get("sharon_user_role")?.value;
  const { pathname } = request.nextUrl;

  const isStudentRoute = pathname.startsWith("/student");
  const isTeacherRoute = pathname.startsWith("/teacher");
  const isAdminRoute = pathname.startsWith("/admin");

  if (isStudentRoute || isTeacherRoute || isAdminRoute) {
    if (!token) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("next", pathname);
      return NextResponse.redirect(loginUrl);
    }

    // Role-Based Access Control checks
    if (isStudentRoute && role !== "student") {
      return NextResponse.redirect(
        new URL(role === "teacher" ? "/teacher/dashboard" : "/admin/dashboard", request.url)
      );
    }

    if (isTeacherRoute && role !== "teacher") {
      return NextResponse.redirect(
        new URL(role === "student" ? "/student/dashboard" : "/admin/dashboard", request.url)
      );
    }

    if (isAdminRoute && role !== "admin") {
      return NextResponse.redirect(
        new URL(role === "student" ? "/student/dashboard" : "/teacher/dashboard", request.url)
      );
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/student/:path*", "/teacher/:path*", "/admin/:path*"],
};
