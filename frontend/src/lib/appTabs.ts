/**
 * Mobile app chrome rules (docs/MOBILE_UX_AUDIT_AND_FIX_PLAN.md, Phase 1). Pure so they are unit-tested; the components
 * only render what these return.
 */
export type AppRole = "student" | "teacher" | "admin";

export interface AppTab {
  href: string;
  label: string;
  icon: "home" | "calendar" | "search" | "book" | "wallet" | "users" | "user";
  /** Extra path prefixes that also mark this tab active. */
  match?: string[];
}

const STUDENT_TABS: AppTab[] = [
  { href: "/student/dashboard", label: "Home", icon: "home" },
  { href: "/student/schedule", label: "Lessons", icon: "calendar", match: ["/student/history", "/student/bookings"] },
  { href: "/tutors", label: "Book", icon: "search", match: ["/student/book", "/student/favorites"] },
  { href: "/student/vocabulary", label: "Words", icon: "book" },
  { href: "/student/wallet", label: "Wallet", icon: "wallet" },
];

const TEACHER_TABS: AppTab[] = [
  { href: "/teacher/dashboard", label: "Home", icon: "home", match: ["/teacher/bookings"] },
  { href: "/teacher/schedule", label: "Hours", icon: "calendar" },
  { href: "/teacher/students", label: "Students", icon: "users" },
  { href: "/teacher/wallet", label: "Wallet", icon: "wallet" },
  { href: "/teacher/profile", label: "Profile", icon: "user", match: ["/teacher/training"] },
];

const under = (pathname: string, prefix: string) => pathname === prefix || pathname.startsWith(prefix + "/");

/** Signed-in areas and account pages get the compact footer on phones instead of the marketing footer. */
export function isCompactFooterArea(pathname: string): boolean {
  return ["/student", "/teacher", "/admin", "/login", "/register", "/forgot-password", "/reset-password", "/verify-email"]
    .some((p) => under(pathname, p));
}

/**
 * Bottom tabs for the signed-in role, or none. Never in the live classroom (the video needs the space) or on the tutor
 * application wizard (an applicant has no dashboard yet). Admins use desktop navigation.
 */
export function tabsFor(pathname: string, role: AppRole | null | undefined): AppTab[] {
  if (pathname.includes("/classroom/")) return [];
  if (role === "student" && (under(pathname, "/student") || under(pathname, "/tutors"))) return STUDENT_TABS;
  if (role === "teacher" && under(pathname, "/teacher") && !under(pathname, "/teacher/apply")) return TEACHER_TABS;
  return [];
}

export function isTabActive(tab: AppTab, pathname: string): boolean {
  return [tab.href, ...(tab.match ?? [])].some((p) => under(pathname, p));
}

/** Where a signed-in user who opens /login or /register should go instead (null: show the page). */
export function signedInAuthRedirect(pathname: string, role: AppRole | null | undefined): string | null {
  if (!role || !(pathname === "/login" || pathname === "/register")) return null;
  return role === "admin" ? "/admin/dashboard" : role === "teacher" ? "/teacher/dashboard" : "/student/dashboard";
}
