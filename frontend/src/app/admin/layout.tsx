"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { ExternalLink, Shield } from "lucide-react";
import { AdminSectionSheet, AdminSidebarNav, QUICK_PORTALS } from "@/components/admin/AdminNav";

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

          {/* Phones: a section button that opens a grouped bottom sheet (replaces the native <select> picker). */}
          <AdminSectionSheet pathname={pathname} />

          {/* Desktop sidebar: the same groups as the phone sheet. */}
          <AdminSidebarNav pathname={pathname} />
        </div>

        {/* Footer Navigation / Quick Switch */}
        <div className="hidden md:block p-6 border-t border-white/10 space-y-3">
          <div className="text-xs font-bold text-cream/70 uppercase tracking-wider">Quick Portals</div>
          <div className="flex flex-col gap-1.5 text-sm text-cream/80">
            {QUICK_PORTALS.map((portal) => (
              <Link
                key={portal.href}
                href={portal.href}
                className="min-h-11 flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-white/5 hover:text-white transition-colors"
              >
                <span>{portal.label}</span>
                <ExternalLink className="w-3 h-3 text-cream/75" aria-hidden="true" />
              </Link>
            ))}
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
              Sharon Ncube
            </span>
          </div>

          <div className="flex items-center gap-3">
          </div>
        </header>

        {/* Content Body */}
        <div className="p-4 sm:p-10 flex-1">{children}</div>
      </main>
    </div>
  );
}
