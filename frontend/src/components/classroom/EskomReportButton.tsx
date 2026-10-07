"use client";

import { useState } from "react";
import { Zap, AlertTriangle, ShieldCheck, X, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { InlineError } from "@/components/ui/ErrorState";

interface EskomReportButtonProps {
  bookingId: string;
  isInterrupted?: boolean;
  onReported?: () => void;
  className?: string;
}

export function EskomReportButton({
  bookingId,
  isInterrupted = false,
  onReported,
  className = "",
}: EskomReportButtonProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [reported, setReported] = useState(isInterrupted);
  const [reportError, setReportError] = useState<unknown>(null);
  const [reportNote, setReportNote] = useState("Sudden municipal load shedding / power trip");

  const handleConfirmReport = async () => {
    setSubmitting(true);
    setReportError(null);
    try {
      await api.reportPowerOutage(bookingId, reportNote);
      setReported(true);
      setModalOpen(false);
      if (onReported) onReported();
    } catch (e) {
      console.error("Failed to report outage:", e);
      setReportError(e);
    } finally {
      setSubmitting(false);
    }
  };

  if (reported) {
    return (
      <div className={`p-4 rounded-2xl bg-warning-surface border border-warning-border text-warning-hover flex items-start gap-3 ${className}`}>
        <ShieldCheck className="w-5 h-5 text-warning shrink-0 mt-0.5" />
        <div className="space-y-1 text-xs">
          <p className="font-extrabold text-warning-hover">Eskom Power Outage Recorded</p>
          <p className="text-sm text-warning-hover leading-relaxed">
            Lesson marked as interrupted. 1 full lesson credit has been automatically credited back to the student, and tutor ratings are shielded under Eskom Power Guard.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setModalOpen(true)}
        className={`min-h-11 px-3.5 py-2 rounded-xl bg-warning-surface hover:bg-warning-surface text-warning-hover border border-warning-border text-xs font-bold flex items-center gap-2 transition-colors ${className}`}
        title="Report Eskom power or fiber outage"
      >
        <Zap className="w-4 h-4 text-warning fill-warning" />
        <span>Eskom Outage Panic Button</span>
      </button>

      {/* Confirmation Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full border border-divider shadow-2xl p-6 space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div className="w-12 h-12 rounded-2xl bg-warning-surface text-warning-hover flex items-center justify-center shrink-0">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <button
                onClick={() => setModalOpen(false)}
                className="min-w-11 justify-center min-h-11 inline-flex items-center p-1 rounded-lg text-ink-muted hover:text-ink"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-2">
              <h3 className="text-xl font-black text-ink font-serif">Report Sudden Power Interruption</h3>
              <p className="text-sm text-ink-muted leading-relaxed">
                Did sudden municipal load-shedding, battery depletion, or fiber loss disrupt this synchronous session?
              </p>
            </div>

            <div className="p-3.5 rounded-2xl bg-cream-surface border border-divider text-xs space-y-1.5">
              <span className="font-bold text-ink flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-cocoa" /> Eskom Power Guard Protection:
              </span>
              <ul className="text-xs text-ink-muted list-disc list-inside space-y-0.5">
                <li>Immediate 1-credit refund credited to student wallet</li>
                <li>Zero penalty rating or cancellation strike on tutor profile</li>
                <li>Session logs flagged as &apos;INTERRUPTED_POWER&apos;</li>
              </ul>
            </div>

            <div className="space-y-2">
              <label htmlFor="f-outage-context-details" className="text-xs font-bold uppercase tracking-wider text-ink-muted block">
                Outage Context / Details
              </label>
              <input id="f-outage-context-details"
                type="text"
                value={reportNote}
                onChange={(e) => setReportNote(e.target.value)}
                placeholder="e.g. Stage 4 load shedding sudden trip, inverter empty..."
                className="min-h-11 w-full px-3.5 py-2.5 rounded-xl bg-cream-surface border border-strong text-base sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-warning"
              />
            </div>

            <InlineError error={reportError} />

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="min-h-11 inline-flex items-center px-4 py-2 rounded-xl text-xs font-bold text-ink-muted hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={handleConfirmReport}
                className="min-h-11 px-5 py-2.5 rounded-xl bg-cocoa hover:bg-cocoa-hover text-white text-xs font-black flex items-center gap-2 transition-colors shadow-sm"
              >
                <Zap className="w-4 h-4 fill-white" />
                <span>{submitting ? "Reporting..." : "Confirm & Report Outage"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
