"use client";

import Link from "next/link";
import { ArrowLeft, Calendar, Info, Clock, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { WeeklyScheduleGrid } from "@/components/teacher/WeeklyScheduleGrid";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/http";

export default function TeacherSchedulePage() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false); const [start, setStart] = useState(""); const [end, setEnd] = useState(""); const [reason, setReason] = useState(""); const [saving, setSaving] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const saveTimeOff = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); setError(""); setMessage(""); try { await api.createTeacherTimeOff({ start_utc: new Date(start).toISOString(), end_utc: new Date(end).toISOString(), reason }); setMessage("Time off added. Confirmed lessons remain visible and are never cancelled by an availability change."); setOpen(false); } catch (err) { setError(errorMessage(err, "Time off could not be added.")); } finally { setSaving(false); } };
  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/teacher/dashboard"
              className="min-w-11 justify-center min-h-11 inline-flex items-center p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-cocoa bg-cocoa/10 px-2 py-0.5 rounded-md">
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
            <Clock className="w-4 h-4 text-cocoa" />
            <span>Timezone: {user?.timezone || "UTC"}</span>
          </div>
        </div>

        {/* Global Synchronization Info Box */}
        <div className="p-4 sm:p-5 rounded-2xl bg-white border border-divider shadow-xs flex items-start gap-3.5 text-sm text-ink">
          <div className="w-9 h-9 rounded-xl bg-cocoa/10 text-cocoa flex items-center justify-center shrink-0 mt-0.5">
            <Info className="w-4 h-4" />
          </div>
          <div className="space-y-1 leading-relaxed">
            <strong className="text-ink font-black">You set your hours once, in your own time zone.</strong>
            <p className="text-ink-muted text-sm">
              We turn each open hour into 25-minute lessons and show them to students in their own time zone, for example
              Tokyo (7 hours ahead of you) or London. A short break is kept between lessons.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-black text-ink">Recurring availability</h2><p className="text-sm text-ink-muted">Set your weekly teaching windows in your own timezone.</p></div><button onClick={() => setOpen(true)} className="min-h-11 inline-flex items-center rounded-xl bg-cocoa px-4 py-2.5 text-sm font-bold text-white">Add time off</button></div>
        {message && <p className="rounded-xl bg-success-surface p-4 text-sm text-success-hover">{message}</p>}
        {error && <p className="rounded-xl bg-warning-surface p-4 text-sm text-warning-hover">{error}</p>}
        {open && <div className="min-w-11 justify-center min-h-11 rounded-3xl border border-strong bg-white p-6 shadow-card"><div className="mb-5 flex items-center justify-between"><div><h2 className="text-lg font-black text-ink">Add time off</h2><p className="text-base sm:text-sm text-ink-muted">Use your browser timezone fields to select the exact window.</p></div><button type="button" onClick={() => setOpen(false)} className="text-sm font-bold text-ink-muted">Cancel</button></div><form onSubmit={saveTimeOff} className="grid gap-4 sm:grid-cols-3"><label className="text-sm font-bold">Starts<input required type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="mt-2 w-full rounded-xl border border-strong p-3 text-sm" /></label><label className="text-sm font-bold">Ends<input required type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="mt-2 w-full rounded-xl border border-strong p-3 text-sm" /></label><label className="text-sm font-bold">Reason<input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} className="mt-2 w-full rounded-xl border border-strong p-3 text-sm" /></label><button disabled={saving} className="min-h-11 inline-flex items-center rounded-xl bg-cocoa px-4 py-3 text-sm font-bold text-white disabled:opacity-50 sm:col-start-3">{saving ? "Saving…" : "Save time off"}</button></form></div>}
        {/* Schedule Grid Component */}
        <WeeklyScheduleGrid />
      </div>
    </div>
  );
}
