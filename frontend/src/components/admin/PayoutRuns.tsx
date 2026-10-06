"use client";

import { useState } from "react";
import { CheckCircle2, Clock, Download, Plus, ShieldCheck, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { InlineError } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";
import type { PayoutRun, PayoutRunLine } from "@/types/admin";

const STATUS_LABEL: Record<string, string> = {
  pending: "Waiting for a second admin",
  approved: "Approved, ready for the bank file",
  exported: "Bank file downloaded, waiting for the bank run",
  processed: "Paid",
  cancelled: "Cancelled",
};

const SKIP_REASON: Record<string, string> = {
  bank_details_unreadable: "bank details could not be read",
  bank_details_changed_recently: "bank details changed in the last 72 hours",
  bank_details_changed: "bank details changed after the run was made",
  balance_insufficient: "balance no longer covers the amount",
};

function LineRow({ line, canReturn, onReturn }: { line: PayoutRunLine; canReturn: boolean; onReturn: (line: PayoutRunLine) => void }) {
  return (
    <tr className="border-t border-divider">
      <td className="py-2.5 px-4 font-bold text-ink">{line.teacher_name}</td>
      <td className="py-2.5 px-4 font-mono text-ink-muted">{line.account_last_four ? `****${line.account_last_four}` : "-"}</td>
      <td className="py-2.5 px-4 font-black text-emerald-800 font-serif">R{line.amount_zar}</td>
      <td className="py-2.5 px-4 text-ink-muted">
        {line.status}
        {line.skip_reason ? `: ${SKIP_REASON[line.skip_reason] ?? line.skip_reason}` : ""}
      </td>
      <td className="py-2.5 px-4 text-right">
        {canReturn && line.status === "paid" && (
          <button type="button" onClick={() => onReturn(line)} className="text-xs font-bold text-red-700 hover:underline">
            Mark returned by bank
          </button>
        )}
      </td>
    </tr>
  );
}

/** Payout runs (slices P1a-c): create, approve (a different admin), download the bank CSV, mark processed, record bank returns. */
export function PayoutRuns({ onChanged }: { onChanged?: () => void }) {
  const { data: runs, error, loading, reload } = useApiData(() => api.listPayoutRuns(), []);
  const [actionError, setActionError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [password, setPassword] = useState("");

  const act = async (key: string, work: () => Promise<unknown>) => {
    setActionError(null);
    setBusy(key);
    try {
      await work();
      reload();
      onChanged?.();
    } catch (err) {
      setActionError(err);
      reload();
    } finally {
      setBusy(null);
    }
  };

  const exportCsv = (run: PayoutRun) =>
    act(`export:${run.id}`, async () => {
      await api.downloadPayoutRunCsv(run.id, run.batch_reference, password);
      setExporting(null);
      setPassword("");
    });

  const markReturned = (line: PayoutRunLine) => {
    const reason = window.prompt("Why did the bank return this payment?");
    if (reason && reason.trim()) void act(`return:${line.id}`, () => api.returnPayoutLine(line.id, reason.trim()));
  };

  const cancel = (run: PayoutRun) => {
    const reason = window.prompt("Why are you cancelling this payout run?");
    if (reason && reason.trim()) void act(`cancel:${run.id}`, () => api.cancelPayoutRun(run.id, reason.trim()));
  };

  return (
    <section aria-labelledby="payout-runs-heading" className="bg-white rounded-3xl border border-divider shadow-card overflow-hidden">
      <div className="p-6 border-b border-divider flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 id="payout-runs-heading" className="text-lg font-black text-ink font-serif">Payout runs</h2>
          <p className="text-xs text-ink-muted">
            The admin who creates a run cannot approve it or mark it paid. Another admin must do both.
          </p>
        </div>
        <button
          type="button"
          disabled={busy === "create"}
          onClick={() => act("create", () => api.createPayoutRun())}
          className="px-4 py-2.5 bg-cocoa hover:bg-cocoa-hover text-white text-xs font-black rounded-xl flex items-center gap-2 self-start disabled:opacity-60"
        >
          <Plus className="w-4 h-4" />
          <span>{busy === "create" ? "Creating..." : "Create payout run"}</span>
        </button>
      </div>

      <div className="p-6 space-y-4">
        <InlineError error={error || actionError} />
        {loading && <p className="text-xs text-ink-muted">Loading payout runs...</p>}
        {!loading && runs && runs.length === 0 && <p className="text-xs text-ink-muted">No payout runs yet.</p>}

        {runs?.map((run) => (
          <article key={run.id} className="border border-divider rounded-2xl overflow-hidden">
            <header className="p-4 bg-cream-surface flex flex-col lg:flex-row lg:items-center justify-between gap-3">
              <div className="space-y-0.5">
                <div className="font-mono font-bold text-sm text-ink">{run.batch_reference}</div>
                <div className="text-xs text-ink-muted flex items-center gap-1.5">
                  {run.status === "processed" ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  ) : run.status === "cancelled" ? (
                    <XCircle className="w-3.5 h-3.5 text-red-600" />
                  ) : (
                    <Clock className="w-3.5 h-3.5 text-amber-600" />
                  )}
                  {STATUS_LABEL[run.status] ?? run.status} · {run.recipients_count} tutor{run.recipients_count === 1 ? "" : "s"} ·
                  R{run.total_payout_zar} · made by {run.created_by ?? "unknown"}
                  {run.approved_by ? ` · approved by ${run.approved_by}` : ""}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {run.status === "pending" && (
                  <button type="button" disabled={busy === `approve:${run.id}`} onClick={() => act(`approve:${run.id}`, () => api.approvePayoutRun(run.id))}
                    className="px-3.5 py-2 bg-white border border-divider rounded-xl text-xs font-bold text-ink flex items-center gap-1.5 disabled:opacity-60">
                    <ShieldCheck className="w-3.5 h-3.5 text-cocoa" /> Approve
                  </button>
                )}
                {(run.status === "approved" || run.status === "exported") && (
                  <button type="button" onClick={() => setExporting(exporting === run.id ? null : run.id)}
                    className="px-3.5 py-2 bg-white border border-divider rounded-xl text-xs font-bold text-ink flex items-center gap-1.5">
                    <Download className="w-3.5 h-3.5 text-cocoa" /> {run.status === "exported" ? "Download bank CSV again" : "Download bank CSV"}
                  </button>
                )}
                {run.status === "exported" && (
                  <button type="button" disabled={busy === `process:${run.id}`} onClick={() => act(`process:${run.id}`, () => api.processPayoutRun(run.id))}
                    className="px-3.5 py-2 bg-emerald-700 text-white rounded-xl text-xs font-black disabled:opacity-60">
                    Mark as paid (bank run done)
                  </button>
                )}
                {(run.status === "pending" || run.status === "approved") && (
                  <button type="button" onClick={() => cancel(run)} className="px-3.5 py-2 text-xs font-bold text-red-700 hover:underline">
                    Cancel run
                  </button>
                )}
              </div>
            </header>

            {exporting === run.id && (
              <form
                className="p-4 border-t border-divider flex flex-col sm:flex-row sm:items-end gap-3 bg-white"
                onSubmit={(e) => {
                  e.preventDefault();
                  void exportCsv(run);
                }}
              >
                <label className="text-xs font-bold text-ink flex-1">
                  Confirm your password to download bank details
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="mt-1 w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs"
                  />
                </label>
                <button type="submit" className="px-4 py-3 bg-cocoa text-white text-xs font-black rounded-xl">Download</button>
              </form>
            )}

            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-xs">
                <thead>
                  <tr className="text-left text-ink-muted uppercase tracking-wider font-bold">
                    <th className="py-2 px-4">Tutor</th>
                    <th className="py-2 px-4">Account</th>
                    <th className="py-2 px-4">Amount</th>
                    <th className="py-2 px-4">Status</th>
                    <th className="py-2 px-4" />
                  </tr>
                </thead>
                <tbody>
                  {run.lines.map((line) => (
                    <LineRow key={line.id} line={line} canReturn={run.status === "processed"} onReturn={markReturned} />
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
