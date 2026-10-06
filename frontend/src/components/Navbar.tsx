"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Menu, X, LogOut, Coins } from "lucide-react";
import { CurrencySwitcher } from "@/components/public/CurrencySwitcher";
import { useAuth } from "@/context/AuthContext";
import { Avatar } from "@/components/ui/Avatar";
import { NotificationBell } from "@/components/notifications";

// Five labels, one line each. Everything else lives in the footer.
const NAV_LINKS = [
  { href: "/tutors", label: "Find Tutors" },
  { href: "/how-it-works", label: "How It Works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/materials", label: "Lessons & Levels" },
  { href: "/teach", label: "Teach With Us" },
];

const MOBILE_EXTRA_LINKS = [
  { href: "/trust-safety", label: "Trust & Safety" },
  { href: "/support", label: "Help & FAQ" },
];

export function Navbar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { user, isAuthenticated, logout, role, isLoading, sessionError } = useAuth();
  const pathname = usePathname();
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  const getDashboardLink = () => {
    if (role === "admin") return "/admin/dashboard";
    if (role === "teacher") return "/teacher/dashboard";
    return "/student/dashboard";
  };

  // Close the drawer on navigation and on Escape (returning focus to the button that opened it).
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileMenuOpen]);

  const desktopLink =
    "relative inline-flex min-h-[44px] items-center whitespace-nowrap text-sm font-semibold text-white/90 transition-colors hover:text-gold-bright";
  const drawerLink =
    "flex min-h-[48px] items-center rounded-xl px-3 text-base font-semibold text-white/90 hover:bg-white/10 hover:text-gold-bright";

  return (
    <header className="on-dark sticky top-0 z-50 border-b border-white/10 bg-teal text-white shadow-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        {/* Brand */}
        <Link href="/" className="flex min-h-[44px] shrink-0 items-center gap-2" aria-label="Sharon Online, home">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gold font-serif text-lg font-bold text-teal shadow-sm">
            S
          </span>
          <span className="whitespace-nowrap font-serif text-xl font-extrabold tracking-tight text-white">
            Sharon<span className="text-gold-bright">Online</span>
          </span>
        </Link>

        {/* Desktop links */}
        <nav aria-label="Main" className="hidden items-center gap-6 xl:flex">
          {NAV_LINKS.map((l) => (
            <Link key={l.href} href={l.href} className={desktopLink} aria-current={pathname === l.href ? "page" : undefined}>
              {l.label}
              {pathname === l.href && (
                <span className="absolute inset-x-0 bottom-1.5 h-0.5 rounded-full bg-gold-bright" aria-hidden="true" />
              )}
            </Link>
          ))}
        </nav>

        {/* Desktop actions */}
        <div className="hidden shrink-0 items-center gap-3 xl:flex">
          <CurrencySwitcher variant="select" />

          {isLoading ? (
            <div className="h-10 w-28 animate-pulse rounded-xl bg-white/10" role="status" aria-label="Checking session" />
          ) : isAuthenticated && user ? (
            <div className="flex items-center gap-3 border-l border-white/20 pl-3">
              {role === "student" && user.credits !== undefined && (
                <div
                  className="flex items-center gap-1.5 whitespace-nowrap rounded-xl border border-white/15 bg-white/10 px-3 py-1.5 text-sm font-bold text-gold-bright"
                  title="Lesson credits"
                >
                  <Coins className="h-4 w-4" aria-hidden="true" />
                  <span>{user.credits}</span>
                  <span className="sr-only">lesson credits</span>
                </div>
              )}
              <NotificationBell />
              <Link
                href={getDashboardLink()}
                className="flex min-h-[44px] items-center gap-2 rounded-xl px-1 hover:opacity-90"
                aria-label={`Go to your ${role} dashboard`}
              >
                <Avatar src={user.avatar_url} name={`${user.first_name} ${user.last_name}`} size="sm" />
                <span className="hidden text-left leading-tight 2xl:block">
                  <span className="block whitespace-nowrap text-sm font-bold text-white">{user.first_name || user.username}</span>
                  <span className="block text-xs capitalize text-white/75">{role}</span>
                </span>
              </Link>
              <button
                type="button"
                onClick={logout}
                aria-label="Sign out"
                className="flex h-11 w-11 items-center justify-center rounded-xl text-white/75 transition-colors hover:bg-white/10 hover:text-white"
              >
                <LogOut className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              {sessionError && (
                <span title={sessionError} className="rounded-lg border border-white/20 bg-white/10 px-2 py-1 text-xs font-bold text-gold-bright">
                  Session unavailable
                </span>
              )}
              <Link href="/login" className="inline-flex min-h-[44px] items-center whitespace-nowrap px-3 text-sm font-semibold text-white hover:text-gold-bright">
                Sign In
              </Link>
              <Link
                href="/tutors"
                className="inline-flex min-h-[44px] items-center whitespace-nowrap rounded-xl bg-primary px-5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-primary-hover"
              >
                Book a Lesson
              </Link>
            </div>
          )}
        </div>

        {/* Mobile controls */}
        <div className="flex items-center gap-1 xl:hidden">
          {isAuthenticated && user && <NotificationBell />}
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMobileMenuOpen((open) => !open)}
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-menu"
            className="flex h-11 w-11 items-center justify-center rounded-xl text-white/90 hover:bg-white/10 hover:text-white"
          >
            {mobileMenuOpen ? <X className="h-6 w-6" aria-hidden="true" /> : <Menu className="h-6 w-6" aria-hidden="true" />}
          </button>
        </div>
      </div>

      {/* Mobile drawer: scrolls on its own so a short phone never traps the last links off-screen */}
      {mobileMenuOpen && (
        <div
          id="mobile-menu"
          className="max-h-[calc(100dvh-4rem)] overflow-y-auto border-t border-white/10 bg-teal-hover px-4 pb-6 pt-3 xl:hidden"
        >
          {isAuthenticated && user && (
            <div className="mb-3 flex items-center justify-between rounded-2xl bg-white/10 p-3">
              <div className="flex items-center gap-3">
                <Avatar src={user.avatar_url} name={`${user.first_name} ${user.last_name}`} size="sm" />
                <div>
                  <div className="text-sm font-bold text-white">{user.first_name} {user.last_name}</div>
                  <div className="text-xs capitalize text-white/75">{role} account</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setMobileMenuOpen(false);
                  logout();
                }}
                className="min-h-[44px] rounded-xl bg-white/10 px-3 text-sm font-bold text-white hover:bg-white/20"
              >
                Sign Out
              </button>
            </div>
          )}

          <nav aria-label="Mobile" className="space-y-1">
            {[...NAV_LINKS, ...MOBILE_EXTRA_LINKS].map((l) => (
              <Link key={l.href} href={l.href} className={drawerLink} aria-current={pathname === l.href ? "page" : undefined}>
                {l.label}
              </Link>
            ))}
          </nav>

          <div className="mt-3 flex items-center justify-between gap-3 rounded-2xl bg-white/10 p-3">
            <span className="text-sm font-semibold text-white/85">Show prices in</span>
            <CurrencySwitcher variant="select" />
          </div>

          <div className="mt-3 flex flex-col gap-2 border-t border-white/10 pt-3">
            {isAuthenticated ? (
              <Link href={getDashboardLink()} className="flex min-h-[48px] items-center justify-center rounded-xl bg-primary text-base font-bold text-white">
                Go to my dashboard
              </Link>
            ) : (
              <>
                <Link href="/tutors" className="flex min-h-[48px] items-center justify-center rounded-xl bg-primary text-base font-bold text-white">
                  Book a Lesson
                </Link>
                <Link href="/login" className="flex min-h-[48px] items-center justify-center rounded-xl bg-white/10 text-base font-semibold text-white">
                  Sign In
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
