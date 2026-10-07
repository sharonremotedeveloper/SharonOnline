"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";
import { CurrencySwitcher } from "@/components/public/CurrencySwitcher";
import { AccountMenu } from "@/components/AccountMenu";
import { useAuth } from "@/context/AuthContext";

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
  const { user, isAuthenticated, isLoading, sessionError } = useAuth();
  const pathname = usePathname();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const signedIn = isAuthenticated && !!user;

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
    "inline-flex min-h-[40px] items-center whitespace-nowrap rounded-full px-3.5 text-sm font-semibold transition-colors";
  const drawerLink =
    "flex min-h-[48px] items-center rounded-xl px-3 text-base font-semibold text-ink hover:bg-cream-surface hover:text-primary";

  return (
    <header className="sticky top-0 z-50 border-b border-divider bg-cream/95 text-ink shadow-sm backdrop-blur supports-[backdrop-filter]:bg-cream/85">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-2 px-4 sm:gap-4 sm:px-6 lg:px-8">
        {/* Brand */}
        <Link href="/" className="flex min-h-[44px] shrink-0 items-center gap-2" aria-label="Sharon Online, home">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-cocoa font-serif text-lg font-bold text-sun shadow-sm">
            S
          </span>
          <span className="whitespace-nowrap font-serif text-lg font-extrabold sm:text-xl tracking-tight text-ink">
            Sharon<span className="text-primary">Online</span>
          </span>
        </Link>

        {/* Desktop links */}
        <nav aria-label="Main" className="on-dark hidden items-center gap-0.5 rounded-full bg-cocoa p-1 shadow-md xl:flex">
          {NAV_LINKS.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`${desktopLink} ${
                  active ? "bg-sun text-ink" : "text-cream hover:bg-white/10 hover:text-white"
                }`}
                aria-current={active ? "page" : undefined}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>

        {/* Right side. Signed in: one avatar menu at every size. Signed out: currency and the two calls to action. */}
        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          {isLoading ? (
            <div className="h-11 w-24 animate-pulse rounded-full bg-cocoa/10" role="status" aria-label="Checking session" />
          ) : signedIn ? (
            <AccountMenu />
          ) : (
            <div className="hidden items-center gap-2 xl:flex">
              <CurrencySwitcher variant="select" />
              {sessionError && (
                <span title={sessionError} className="rounded-lg border border-divider bg-white px-2 py-1 text-xs font-bold text-primary">
                  Session unavailable
                </span>
              )}
              <Link href="/login" className="inline-flex min-h-[44px] items-center whitespace-nowrap px-3 text-sm font-semibold text-ink hover:text-primary">
                Sign In
              </Link>
              <Link
                href="/tutors"
                className="inline-flex min-h-[44px] items-center whitespace-nowrap rounded-full bg-cocoa px-5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-cocoa-hover"
              >
                Book a Lesson
              </Link>
            </div>
          )}

          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMobileMenuOpen((open) => !open)}
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-menu"
            className="flex h-11 w-11 items-center justify-center rounded-xl text-ink hover:bg-cocoa/10 xl:hidden"
          >
            {mobileMenuOpen ? <X className="h-6 w-6" aria-hidden="true" /> : <Menu className="h-6 w-6" aria-hidden="true" />}
          </button>
        </div>
      </div>

      {/* Mobile and tablet drawer: site links only. Account things live in the avatar menu. */}
      {mobileMenuOpen && (
        <div
          id="mobile-menu"
          className="max-h-[calc(100dvh-4rem)] overflow-y-auto border-t border-divider bg-cream px-4 pb-6 pt-3 xl:hidden"
        >
          <nav aria-label="Mobile" className="space-y-1">
            {[...NAV_LINKS, ...MOBILE_EXTRA_LINKS].map((l) => (
              <Link key={l.href} href={l.href} className={drawerLink} aria-current={pathname === l.href ? "page" : undefined}>
                {l.label}
              </Link>
            ))}
          </nav>

          {!signedIn && !isLoading && (
            <>
              <div className="mt-3 flex items-center justify-between gap-3 rounded-2xl bg-white p-3 border border-divider">
                <span className="text-sm font-semibold text-ink">Show prices in</span>
                <CurrencySwitcher variant="select" />
              </div>
              <div className="mt-3 flex flex-col gap-2 border-t border-divider pt-3">
                <Link href="/tutors" className="flex min-h-[52px] items-center justify-center rounded-full bg-cocoa text-base font-bold text-white">
                  Book a Lesson
                </Link>
                <Link href="/login" className="min-h-11 flex min-h-[52px] items-center justify-center rounded-full border-2 border-cocoa/20 text-base font-semibold text-ink">
                  Sign In
                </Link>
              </div>
            </>
          )}
        </div>
      )}
    </header>
  );
}
