"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Radio,
  ArrowLeft,
  Clock,
  Video,
  User,
  BookOpen,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";
import { api } from "@/lib/api";
import { LiveSessionRadarItem } from "@/types/admin";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

export default function AdminLiveSessionsPage() {
  const [sessions, setSessions] = useState<LiveSessionRadarItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [error, setError] = useState<unknown>(null);

  const fetchSessions = async () => {
    try {
      const data = await api.getLiveSessions();
      setSessions(data);
      setLastRefreshed(new Date());
      setError(null);
    } catch (e) {
      // Keep the last good snapshot on screen, but make the failure visible (it is stale, not live).
      console.error("Failed to load live sessions:", e);
      setError(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 15000); // 15s polling for radar
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-error border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm font-bold text-ink-muted">Loading live session radar...</p>
      </div>
    );
  }

  if (error && lastRefreshed === null) {
    return (
      <div className="py-20">
        <ErrorState
          error={error}
          title="We could not load the live session radar"
          onRetry={() => {
            setLoading(true);
            fetchSessions();
          }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/admin/dashboard"
            className="min-w-11 justify-center min-h-11 inline-flex items-center p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-error opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-error"></span>
              </span>
              <span className="text-xs font-mono font-bold text-error uppercase tracking-wider">
                LIVE ZOOM RADAR
              </span>
              <span className="text-xs font-bold text-ink-muted">· {sessions.length} Active Classes</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
              Real-Time Attendance &amp; Dwell Telemetry
            </h1>
          </div>
        </div>

        <button
          type="button"
          onClick={fetchSessions}
          className="min-h-11 px-4 py-2 bg-white hover:bg-cream-surface text-ink text-xs font-bold rounded-xl border border-divider shadow-xs flex items-center gap-2 transition-all self-start sm:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5 text-cocoa" />
          <span>{lastRefreshed ? `Updated ${lastRefreshed.toLocaleTimeString()}` : "Refresh"}</span>
        </button>
      </div>

      {error != null && (
        <InlineError error={`Live updates failed, so the cards below may be out of date. ${typeof error === "object" && error && "message" in error ? String((error as Error).message) : ""}`} />
      )}

      {sessions.length === 0 && (
        <div className="bg-white rounded-3xl p-10 border border-divider shadow-card text-center text-sm text-ink-muted">
          No classes are live right now.
        </div>
      )}

      {/* Radar Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sessions.map((sess) => {
          const isWrapUp = sess.status === "wrap_up";
          const isStaging = sess.status === "staging";

          return (
            <div
              key={sess.id}
              className={`bg-white rounded-3xl p-6 border shadow-card transition-all space-y-5 ${
                isWrapUp
                  ? "border-warning-border ring-2 ring-warning-surface"
                  : isStaging
                  ? "border-info-border"
                  : "border-divider"
              }`}
            >
              {/* Header Status Bar */}
              <div className="flex items-center justify-between border-b border-divider pb-3">
                <span className="font-mono text-xs font-bold text-cocoa bg-cocoa/10 px-2.5 py-0.5 rounded-full">
                  {sess.booking_ref}
                </span>

                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-black uppercase tracking-wider ${
                    isWrapUp
                      ? "bg-warning-surface text-warning-hover animate-pulse"
                      : isStaging
                      ? "bg-info-surface text-info-hover"
                      : "bg-success-surface text-success-hover"
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isWrapUp ? "bg-warning" : isStaging ? "bg-info" : "bg-success"
                    }`}
                  />
                  <span>
                    {isWrapUp
                      ? `Wrapping Up (${sess.elapsed_minutes}m/25m)`
                      : isStaging
                      ? "Staging Room"
                      : `Active Class (${sess.elapsed_minutes}m/25m)`}
                  </span>
                </span>
              </div>

              {/* Participants Details */}
              <div className="space-y-3 text-xs">
                {/* Tutor */}
                <div className="flex items-center justify-between p-2.5 rounded-xl bg-cream-surface border border-divider">
                  <div className="flex items-center gap-2">
                    <User className="w-4 h-4 text-cocoa" />
                    <div>
                      <span className="font-bold text-ink block">{sess.teacher_name}</span>
                      <span className="text-xs text-ink-muted">Native Educator (Host)</span>
                    </div>
                  </div>
                  <span className="text-success-hover font-bold flex items-center gap-1 text-xs">
                    <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                    {sess.teacher_joined_at ? "In Call" : "Awaiting Host"}
                  </span>
                </div>

                {/* Student */}
                <div className="flex items-center justify-between p-2.5 rounded-xl bg-cream-surface border border-divider">
                  <div className="flex items-center gap-2">
                    <User className="w-4 h-4 text-star" />
                    <div>
                      <span className="font-bold text-ink block">{sess.student_name}</span>
                      <span className="text-xs text-ink-muted">Enrolled Student</span>
                    </div>
                  </div>
                  <span className="text-success-hover font-bold flex items-center gap-1 text-xs">
                    <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                    {sess.student_joined_at ? "In Call" : "Connecting..."}
                  </span>
                </div>
              </div>

              {/* Curriculum in Use */}
              <div className="p-3 rounded-2xl bg-cream-surface/60 border border-divider space-y-1 text-xs">
                <span className="text-xs font-bold uppercase tracking-wider text-ink-muted flex items-center gap-1">
                  <BookOpen className="w-3 h-3 text-cocoa" /> Synchronized Material
                </span>
                <p className="font-bold text-ink truncate">{sess.material_title}</p>
              </div>

              {/* Dwell Progress Bar */}
              <div className="space-y-1.5 pt-1">
                <div className="flex justify-between text-xs font-bold text-ink-muted">
                  <span>Lesson Dwell Time</span>
                  <span className="text-ink font-mono">{sess.elapsed_minutes} / 25 mins</span>
                </div>
                <div className="w-full h-2.5 bg-cream-deep rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 rounded-full ${
                      isWrapUp ? "bg-warning" : isStaging ? "bg-info" : "bg-cocoa"
                    }`}
                    style={{ width: `${Math.min(100, (sess.elapsed_minutes / 25) * 100)}%` }}
                  />
                </div>
              </div>

              {/* Meeting ID & Telemetry Action */}
              <div className="flex items-center justify-between text-xs pt-2 border-t border-divider">
                <span className="text-ink-muted font-mono">Zoom ID: {sess.zoom_meeting_id}</span>
                <span className="text-cocoa font-bold flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5" /> S2S Webhook Monitored
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
