"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, CalendarDays, Home, Search, User, Users, Wallet } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { isTabActive, tabsFor, type AppTab } from "@/lib/appTabs";

const ICONS: Record<AppTab["icon"], typeof Home> = {
  home: Home, calendar: CalendarDays, search: Search, book: BookOpen, wallet: Wallet, users: Users, user: User,
};

/**
 * Phone/tablet bottom navigation for signed-in students and tutors (hidden from `lg`, where the desktop header and page
 * links stay as they are). The spacer keeps the footer and page end clear of the fixed bar.
 */
export function AppTabBar() {
  const pathname = usePathname() || "/";
  const { role } = useAuth();
  const tabs = tabsFor(pathname, role);
  if (tabs.length === 0) return null;

  return (
    <>
      <div aria-hidden="true" className="h-[calc(4rem+env(safe-area-inset-bottom))] lg:hidden" />
      <nav
        aria-label="App"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-divider bg-white pb-[env(safe-area-inset-bottom)] shadow-[0_-4px_16px_rgba(45,37,33,0.06)] print:hidden lg:hidden"
      >
        <ul className="mx-auto grid max-w-lg grid-cols-5">
          {tabs.map((tab) => {
            const Icon = ICONS[tab.icon];
            const active = isTabActive(tab, pathname);
            return (
              <li key={tab.href}>
                <Link
                  href={tab.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-16 flex-col items-center justify-center gap-0.5 text-xs font-semibold transition-colors ${
                    active ? "text-cocoa" : "text-ink-muted hover:text-ink"
                  }`}
                >
                  <span className={`flex h-7 w-12 items-center justify-center rounded-full ${active ? "bg-cocoa/10" : ""}`}>
                    <Icon className="h-5 w-5" aria-hidden="true" strokeWidth={active ? 2.4 : 2} />
                  </span>
                  {tab.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
