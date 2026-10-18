"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  BookOpen, ChevronDown, Coins, CreditCard, ExternalLink, FileSpreadsheet, GraduationCap, LayoutDashboard, Radio,
  RotateCcw, Scale, Shield, UserCheck, Users, X, type LucideIcon,
} from "lucide-react";
import { Portal } from "@/components/ui/Portal";
import { useDialog } from "@/hooks/useDialog";

type NavItem = { href: string; label: string; icon: LucideIcon; pulse?: boolean };

/** Admin sections in four groups (UI/UX nav-hierarchy: grouped, icon + label, current one highlighted). */
export const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Overview",
    items: [
      { href: "/admin/dashboard", label: "Executive Dashboard", icon: LayoutDashboard },
      { href: "/admin/sessions/live", label: "Live Attendance Radar", icon: Radio, pulse: true },
    ],
  },
  {
    title: "Tutors",
    items: [
      { href: "/admin/teachers/vetting", label: "Tutor Vetting Studio", icon: UserCheck },
      { href: "/admin/teachers", label: "Tutor Directory & Roster", icon: Users },
      { href: "/admin/training", label: "Tutor Training", icon: GraduationCap },
    ],
  },
  {
    title: "Lessons & content",
    items: [
      { href: "/admin/materials", label: "Lesson Materials", icon: BookOpen },
      { href: "/admin/disputes", label: "Dispute Tribunal", icon: Scale },
    ],
  },
  {
    title: "Money",
    items: [
      { href: "/admin/finance/ledger", label: "Escrow Ledger Audit", icon: FileSpreadsheet },
      { href: "/admin/finance/refunds", label: "Student Refunds", icon: RotateCcw },
      { href: "/admin/finance/payouts", label: "Batch Bank Payouts", icon: CreditCard },
      { href: "/admin/finance/fx-rates", label: "FX Rates (EUR/JPY)", icon: Coins },
    ],
  },
];

const ALL_ITEMS = NAV_GROUPS.flatMap((g) => g.items);

export const QUICK_PORTALS = [
  { href: "/teacher/dashboard", label: "Tutor Cockpit" },
  { href: "/", label: "Public Storefront" },
];

/** The section the path belongs to: the longest matching prefix wins (/admin/teachers/vetting is not the roster). */
export function activeItem(pathname: string): NavItem | undefined {
  return [...ALL_ITEMS]
    .sort((a, b) => b.href.length - a.href.length)
    .find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));
}

function Pulse() {
  return (
    <span className="relative flex h-2 w-2" aria-hidden="true">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sun opacity-75 motion-reduce:animate-none" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-sun" />
    </span>
  );
}

/** Desktop sidebar (md and up): the same groups as the phone sheet. */
export function AdminSidebarNav({ pathname }: { pathname: string }) {
  const current = activeItem(pathname);
  return (
    <nav aria-label="Admin" className="hidden space-y-5 md:block">
      {NAV_GROUPS.map((group) => (
        <div key={group.title}>
          <p className="px-4 pb-1.5 text-[11px] font-bold uppercase tracking-[.14em] text-cream/55">{group.title}</p>
          <ul className="space-y-1">
            {group.items.map((item) => {
              const Icon = item.icon;
              const isActive = current?.href === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={`flex min-h-11 items-center justify-between gap-3 rounded-xl px-4 py-2.5 text-sm font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sun ${
                      isActive ? "bg-white/10 text-white shadow-[inset_3px_0_0_0_theme(colors.sun.DEFAULT)]" : "text-cream/70 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    <span className="flex items-center gap-3">
                      <Icon className="h-4 w-4 opacity-80" aria-hidden="true" />
                      {item.label}
                    </span>
                    {item.pulse && <Pulse />}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/**
 * Phones (below md): a button naming the current section opens a bottom sheet with every section, grouped, with icons.
 * Replaces the native <select>, whose Android picker showed a plain grey radio list. Escape, the close button, a tap on
 * the backdrop, the phone's Back button and choosing a section all close it; focus is trapped while open and returns to
 * the button (useDialog).
 *
 * Back closes the sheet instead of leaving the page (UI/UX back-behavior): opening pushes one history entry that Back
 * pops; closing from the sheet pops it too; choosing a section replaces it, so history keeps one entry per page.
 */
export function AdminSectionSheet({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const current = activeItem(pathname);
  const CurrentIcon = current?.icon ?? Shield;
  const openSheet = () => {
    window.history.pushState({ ...window.history.state, adminSheet: true }, "");
    setOpen(true);
  };
  // Close from inside the sheet: step back over our own entry (the popstate below then closes it).
  const closeSheet = () => {
    if (window.history.state?.adminSheet) window.history.back();
    else setOpen(false);
  };
  useDialog(sheetRef, open, closeSheet);

  useEffect(() => {
    if (!open) return;
    const onPop = () => setOpen(false);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [open]);

  // Arriving on another section (the chosen link replaced our history entry) closes the sheet.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        type="button"
        onClick={openSheet}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="flex min-h-14 w-full items-center gap-3 rounded-2xl border border-white/15 bg-white/10 px-3 text-left text-white transition-colors hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sun"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-sun text-ink">
          <CurrentIcon className="h-[18px] w-[18px]" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] font-bold uppercase tracking-[.14em] text-cream/60">Admin section</span>
          <span className="block truncate text-base font-bold">{current?.label ?? "Choose a section"}</span>
        </span>
        <ChevronDown className="h-5 w-5 shrink-0 text-cream/70" aria-hidden="true" />
      </button>

      {open && (
        <Portal>
          <div className="fixed inset-0 z-50 flex items-end bg-ink/50 backdrop-blur-sm motion-safe:animate-[fade-in_150ms_ease-out]" onClick={closeSheet}>
            <div
              ref={sheetRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="admin-sheet-title"
              tabIndex={-1}
              onClick={(e) => e.stopPropagation()}
              className="max-h-[85dvh] w-full overflow-y-auto rounded-t-3xl bg-cocoa pb-[max(1rem,env(safe-area-inset-bottom))] text-white shadow-2xl focus:outline-none motion-safe:animate-[sheet-up_220ms_cubic-bezier(.2,.8,.2,1)]"
            >
              <div className="sticky top-0 z-10 bg-cocoa px-5 pb-3 pt-2.5">
                <div className="mx-auto mb-2 h-1.5 w-10 rounded-full bg-white/25" aria-hidden="true" />
                <div className="flex items-center justify-between">
                  <h2 id="admin-sheet-title" className="font-serif text-xl font-black text-cream">
                    Admin sections
                  </h2>
                  <button
                    type="button"
                    onClick={closeSheet}
                    aria-label="Close admin sections"
                    className="flex h-11 w-11 items-center justify-center rounded-xl text-cream/80 hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sun"
                  >
                    <X className="h-5 w-5" aria-hidden="true" />
                  </button>
                </div>
              </div>

              <nav aria-label="Admin" className="space-y-4 px-3">
                {NAV_GROUPS.map((group) => (
                  <div key={group.title}>
                    <p className="px-3 pb-1 text-[11px] font-bold uppercase tracking-[.14em] text-cream/55">{group.title}</p>
                    <ul className="space-y-1">
                      {group.items.map((item) => {
                        const Icon = item.icon;
                        const isActive = current?.href === item.href;
                        return (
                          <li key={item.href}>
                            <Link
                              href={item.href}
                              replace
                              aria-current={isActive ? "page" : undefined}
                              className={`flex min-h-12 items-center gap-3 rounded-2xl px-3 py-2 text-[15px] font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sun ${
                                isActive ? "bg-sun text-ink" : "text-cream/90 hover:bg-white/10"
                              }`}
                            >
                              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${isActive ? "bg-ink/10" : "bg-white/10"}`}>
                                <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
                              </span>
                              <span className="min-w-0 flex-1">{item.label}</span>
                              {isActive ? (
                                <span className="shrink-0 rounded-full bg-ink/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider">Here</span>
                              ) : (
                                item.pulse && <Pulse />
                              )}
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </nav>

              <div className="mx-5 mt-5 border-t border-white/10 pt-4">
                <p className="pb-1 text-[11px] font-bold uppercase tracking-[.14em] text-cream/55">Quick portals</p>
                <div className="grid grid-cols-2 gap-2">
                  {QUICK_PORTALS.map((portal) => (
                    <Link
                      key={portal.href}
                      href={portal.href}
                      replace
                      className="flex min-h-11 items-center justify-between gap-2 rounded-xl bg-white/5 px-3 text-sm font-bold text-cream/85 hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sun"
                    >
                      {portal.label}
                      <ExternalLink className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden="true" />
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Portal>
      )}
    </div>
  );
}
