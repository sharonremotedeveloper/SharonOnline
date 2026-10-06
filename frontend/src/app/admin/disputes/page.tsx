"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Scale,
  CheckCircle2,
  AlertTriangle,
  User,
  Clock,
  ShieldAlert,
  Radio,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";
import { DisputeCase } from "@/types/admin";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

export default function AdminDisputesPage() {
  type ResolveAction = "full_refund_student" | "release_tutor" | "split_50_50";
  const ACTION_LABELS: Record<ResolveAction, string> = {
    full_refund_student: "100% refund to the student",
    split_50_50: "a 50/50 goodwill split",
    release_tutor: "release 100% to the tutor",
  };

  const [disputes, setDisputes] = useState<DisputeCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [successNote, setSuccessNote] = useState<string | null>(null);
  const [resolveError, setResolveError] = useState<{ caseId: string; error: unknown } | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<{ caseId: string; action: ResolveAction } | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadDisputes() {
      setLoading(true);
      setLoadError(null);
      try {
        const list = await api.getDisputes();
        if (!cancelled) setDisputes(list);
      } catch (e) {
        console.error("Failed to load disputes:", e);
        if (!cancelled) {
          setDisputes([]);
          setLoadError(e);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadDisputes();
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  // Money action: runs only after the admin explicitly confirmed; local state changes only after the server accepted it.
  const handleResolve = async (caseId: string, action: ResolveAction) => {
    setResolvingId(caseId);
    setSuccessNote(null);
    setResolveError(null);
    try {
      await api.resolveDispute(caseId, action);
      setSuccessNote(
        `Dispute ${caseId} resolved with action [${action}]. Escrow ledger updated atomically.`
      );
      setDisputes((prev) =>
        prev.map((d) => (d.id === caseId ? { ...d, status: "resolved", resolution: action } : d))
      );
      setPendingConfirm(null);
    } catch (e) {
      console.error("Failed to resolve dispute:", e);
      setResolveError({ caseId, error: e });
    } finally {
      setResolvingId(null);
    }
  };

  if (loading) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-rose-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm font-bold text-ink-muted">Loading frozen escrow arbitration tribunal...</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="py-20">
        <ErrorState
          error={loadError}
          title="We couldn't load the dispute tribunal"
          onRetry={() => setReloadTick((t) => t + 1)}
        />
      </div>
    );
  }

  const openCases = disputes.filter((d) => d.status === "open");

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/admin/dashboard"
            className="p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold text-rose-700 bg-rose-100 px-2 py-0.5 rounded-md">
                ESCROW ARBITRATION
              </span>
              <span className="text-xs font-bold text-ink-muted">{openCases.length} Cases Requiring Decision</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
              Dispute Adjudication Tribunal
            </h1>
          </div>
        </div>
      </div>

      {successNote && (
        <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-300 text-xs font-bold text-emerald-950 flex items-center gap-2.5">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successNote}</span>
        </div>
      )}

      {/* Disputes List */}
      {disputes.length === 0 && (
        <div className="bg-white rounded-3xl p-10 border border-divider shadow-card text-center text-sm text-ink-muted">
          No disputes to review.
        </div>
      )}
      <div className="space-y-6">
        {disputes.map((c) => {
          const isResolved = c.status === "resolved";

          return (
            <div
              key={c.id}
              className={`bg-white rounded-3xl p-6 sm:p-8 border shadow-card space-y-6 transition-all ${
                isResolved ? "opacity-75 border-divider" : "border-rose-300 ring-2 ring-rose-50"
              }`}
            >
              {/* Case Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold text-cocoa bg-cocoa/10 px-2.5 py-0.5 rounded-full">
                      CASE: {c.booking_ref}
                    </span>
                    <span className="text-xs text-ink-muted">{c.lesson_date}</span>
                  </div>
                  <h3 className="text-lg font-black text-ink font-serif">
                    {c.student_name} vs. {c.teacher_name}
                  </h3>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <span className="text-xs uppercase font-bold text-ink-muted block">Frozen Amount</span>
                    <span className="text-base font-black text-ink">
                      ${c.amount_usd} USD (R{c.amount_zar})
                    </span>
                  </div>

                  <span
                    className={`px-3 py-1 rounded-full text-xs font-bold ${
                      isResolved
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-rose-100 text-rose-800 animate-pulse"
                    }`}
                  >
                    {isResolved ? `Resolved (${c.resolution})` : "Arbitration Open"}
                  </span>
                </div>
              </div>

              {/* 3-Column Evidence Comparison */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                {/* 1. Student Complaint */}
                <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-2">
                  <div className="flex items-center gap-2 text-ink font-bold">
                    <User className="w-4 h-4 text-gold-bright" />
                    <span>Student Complaint Statement</span>
                  </div>
                  <p className="text-ink-muted leading-relaxed font-sans italic bg-white p-3 rounded-xl border border-divider">
                    &ldquo;{c.student_statement}&rdquo;
                  </p>
                </div>

                {/* 2. Tutor Defense */}
                <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-2">
                  <div className="flex items-center gap-2 text-ink font-bold">
                    <User className="w-4 h-4 text-cocoa" />
                    <span>Tutor Defense Statement</span>
                  </div>
                  <p className="text-ink-muted leading-relaxed font-sans italic bg-white p-3 rounded-xl border border-divider">
                    &ldquo;{c.teacher_statement}&rdquo;
                  </p>
                </div>

                {/* 3. Authoritative Zoom Webhook Telemetry */}
                <div className="p-4 rounded-2xl bg-[#201A17] text-cream border border-white/10 space-y-2">
                  <div className="flex items-center gap-2 font-bold text-gold-bright">
                    <Radio className="w-4 h-4" />
                    <span>Zoom Server Dwell Logs</span>
                  </div>
                  <div className="space-y-1.5 text-xs font-mono">
                    <div className="flex justify-between">
                      <span className="text-cream/60">Student Dwell:</span>
                      <strong className="text-white">{c.zoom_telemetry.student_dwell_minutes} mins</strong>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-cream/60">Tutor Dwell:</span>
                      <strong className="text-white">{c.zoom_telemetry.teacher_dwell_minutes} mins</strong>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-cream/60">Audio Connected:</span>
                      <strong className={c.zoom_telemetry.call_connected ? "text-emerald-400" : "text-rose-400"}>
                        {c.zoom_telemetry.call_connected ? "Yes" : "Failed / Dropped"}
                      </strong>
                    </div>
                    {c.zoom_telemetry.interrupted_reason && (
                      <p className="text-xs text-sun-soft pt-1 border-t border-white/10">
                        {c.zoom_telemetry.interrupted_reason}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Adjudication Decision Bar */}
              {resolveError?.caseId === c.id && <InlineError error={resolveError.error} />}
              {!isResolved && (
                <div className="pt-4 border-t border-divider flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="text-xs text-ink-muted">
                    Executing an adjudication decision atomically credits/debits the double-entry escrow ledger.
                  </div>

                  {pendingConfirm?.caseId === c.id ? (
                    <div className="flex flex-wrap items-center gap-2 bg-rose-50 border border-rose-200 rounded-xl px-3 py-2">
                      <span className="text-xs font-bold text-rose-900">
                        Confirm {ACTION_LABELS[pendingConfirm.action]} for {c.booking_ref}? This moves money and cannot be undone.
                      </span>
                      <button
                        type="button"
                        disabled={resolvingId === c.id}
                        onClick={() => handleResolve(c.id, pendingConfirm.action)}
                        className="px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-bold hover:bg-rose-700 disabled:opacity-50"
                      >
                        {resolvingId === c.id ? "Executing..." : "Confirm & execute"}
                      </button>
                      <button
                        type="button"
                        disabled={resolvingId === c.id}
                        onClick={() => setPendingConfirm(null)}
                        className="px-3 py-1.5 rounded-lg bg-white border border-divider text-xs font-bold text-ink disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={resolvingId === c.id || pendingConfirm?.caseId === c.id}
                      onClick={() => setPendingConfirm({ caseId: c.id, action: "full_refund_student" })}
                      className="px-4 py-2 rounded-xl bg-cocoa text-white text-xs font-bold hover:bg-cocoa-hover transition-colors shadow-xs"
                    >
                      100% Refund to Student
                    </button>

                    <button
                      type="button"
                      disabled={resolvingId === c.id || pendingConfirm?.caseId === c.id}
                      onClick={() => setPendingConfirm({ caseId: c.id, action: "split_50_50" })}
                      className="px-4 py-2 rounded-xl bg-amber-600 text-white text-xs font-bold hover:bg-amber-700 transition-colors shadow-xs"
                    >
                      Split 50/50 Goodwill
                    </button>

                    <button
                      type="button"
                      disabled={resolvingId === c.id || pendingConfirm?.caseId === c.id}
                      onClick={() => setPendingConfirm({ caseId: c.id, action: "release_tutor" })}
                      className="px-4 py-2 rounded-xl bg-ink text-white text-xs font-bold hover:bg-black transition-colors shadow-xs"
                    >
                      Release 100% to Tutor
                    </button>
                  </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
