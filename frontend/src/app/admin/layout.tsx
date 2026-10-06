"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  UserCheck,
  Users,
  Radio,
  Scale,
  FileSpreadsheet,
  CreditCard,
  Coins,
  Shield,
  ExternalLink,
  ChevronRight,
  Sparkles,
  Zap,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/admin/dashboard", label: "Executive Dashboard", icon: LayoutDashboard },
  { href: "/admin/teachers/vetting", label: "Tutor Vetting Studio", icon: UserCheck, badge: "3" },
  { href: "/admin/teachers", label: "Tutor Directory & Roster", icon: Users },
  { href: "/admin/sessions/live", label: "Live Attendance Radar", icon: Radio, pulse: true },
  { href: "/admin/disputes", label: "Dispute Tribunal", icon: Scale, badge: "2", badgeColor: "bg-error text-white" },
  { href: "/admin/finance/ledger", label: "Escrow Ledger Audit", icon: FileSpreadsheet },
  { href: "/admin/finance/payouts", label: "Batch Bank Payouts", icon: CreditCard },
  { href: "/admin/finance/fx-rates", label: "FX Rates (EUR/JPY)", icon: Coins },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-cream flex flex-col md:flex-row">
      {/* Sidebar Navigation */}
      <aside className="w-full md:w-64 bg-cocoa text-white flex flex-col justify-between shrink-0 border-r border-white/10 md:min-h-screen">
        <div className="p-4 md:p-6 space-y-4 md:space-y-8">
          {/* Logo & Platform Badge */}
          <div className="space-y-2">
            <Link href="/admin/dashboard" className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-gold flex items-center justify-center font-black text-ink shadow-sm">
                <Shield className="w-5 h-5 text-ink" />
              </div>
              <div>
                <span className="font-serif font-black text-lg text-cream tracking-tight block">
                  Sharon Online
                </span>
                <span className="text-xs font-mono tracking-widest uppercase text-gold-bright font-bold">
                  Command Center
                </span>
              </div>
            </Link>

            <div className="hidden md:flex items-center gap-2 pt-1 text-sm text-cream/70">
              <span className="w-2 h-2 rounded-full bg-sun animate-pulse"></span>
              <span>Platform Core Online</span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav aria-label="Admin" className="flex gap-2 overflow-x-auto pb-1 md:block md:space-y-1.5 md:overflow-visible md:pb-0">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href || (item.href !== "/admin/dashboard" && pathname.startsWith(item.href));

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex min-h-[44px] shrink-0 items-center justify-between gap-3 whitespace-nowrap px-4 py-2.5 rounded-full md:rounded-xl text-sm font-bold transition-all ${
                    isActive
                      ? "bg-cocoa text-white shadow-sm"
                      : "text-cream/70 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className="w-4 h-4 opacity-80" />
                    <span>{item.label}</span>
                  </div>

                  {item.badge && (
                    <span
                      className={`text-xs font-mono px-2 py-0.5 rounded-full font-black ${
                        item.badgeColor || "bg-accent text-ink"
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}

                  {item.pulse && (
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sun opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-sun"></span>
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Footer Navigation / Quick Switch */}
        <div className="hidden md:block p-6 border-t border-white/10 space-y-3">
          <div className="text-xs font-bold text-cream/70 uppercase tracking-wider">Quick Portals</div>
          <div className="flex flex-col gap-1.5 text-sm text-cream/80">
            <Link
              href="/teacher/dashboard"
              className="min-h-11 flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-white/5 hover:text-white transition-colors"
            >
              <span>Tutor Cockpit</span>
              <ExternalLink className="w-3 h-3 text-cream/75" />
            </Link>
            <Link
              href="/"
              className="min-h-11 flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-white/5 hover:text-white transition-colors"
            >
              <span>Public Storefront</span>
              <ExternalLink className="w-3 h-3 text-cream/75" />
            </Link>
          </div>
        </div>
      </aside>

      {/* Main Content Pane */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Top Header Bar */}
        <header className="bg-white border-b border-divider px-6 py-4 flex items-center justify-between gap-4 sticky top-0 z-30 shadow-2xs">
          <div className="flex items-center gap-3">
            <span className="px-2.5 py-1 rounded-md bg-cocoa text-cream text-xs font-mono font-bold tracking-wider uppercase">
              Admin Mode
            </span>
            <span className="text-xs text-ink-muted hidden sm:inline">
              Sharon Mupesa &middot; Chief Operating Executive
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-success-surface text-success-hover border border-success-border text-xs font-bold">
              <Zap className="w-3.5 h-3.5 text-success fill-success" />
              <span>Power Guard monitoring enabled</span>
            </div>
          </div>
        </header>

        {/* Content Body */}
        <div className="p-6 sm:p-10 flex-1">{children}</div>
      </main>
    </div>
  );
}
