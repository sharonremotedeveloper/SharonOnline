"use client";

import Link from "next/link";
import { ArrowLeft, Calendar, Info, Clock, ShieldCheck } from "lucide-react";
import { WeeklyScheduleGrid } from "@/components/teacher/WeeklyScheduleGrid";

export default function TeacherSchedulePage() {
  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/teacher/dashboard"
              className="p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-teal bg-teal/10 px-2 py-0.5 rounded-md">
                  AVAILABILITY PLANNER
                </span>
                <span className="text-xs font-bold text-ink-muted">Recurring Weekly Matrix</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
                Manage Weekly Teaching Hours
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold text-ink-muted bg-white px-3.5 py-2 rounded-xl border border-divider shadow-xs">
            <Clock className="w-4 h-4 text-teal" />
            <span>Timezone: Africa/Johannesburg (SAST / UTC+2)</span>
          </div>
        </div>

        {/* Global Synchronization Info Box */}
        <div className="p-4 sm:p-5 rounded-2xl bg-white border border-divider shadow-xs flex items-start gap-3.5 text-xs text-ink">
          <div className="w-9 h-9 rounded-xl bg-teal/10 text-teal flex items-center justify-center shrink-0 mt-0.5">
            <Info className="w-4 h-4" />
          </div>
          <div className="space-y-1 leading-relaxed">
            <strong className="text-ink font-black">Zero-Drift Global Timezone Engine:</strong>
            <p className="text-ink-muted text-[11px]">
              When you activate an hour in SAST (UTC+2), our Redlock availability engine automatically projects
              25-minute bookable slots into student viewer timezones across Tokyo (+7h), Seoul (+7h), London (-1h),
              and New York (-6h) with automatic 5-minute breather buffers.
            </p>
          </div>
        </div>

        {/* Schedule Grid Component */}
        <WeeklyScheduleGrid />
      </div>
    </div>
  );
}
