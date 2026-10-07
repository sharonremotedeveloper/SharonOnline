"use client";

import Link from "next/link";
import {
  ArrowLeft,
  FileSpreadsheet,
  CheckCircle2,
  Clock,
  DollarSign,
  ShieldCheck,
  Search,
  Download,
} from "lucide-react";
import { api } from "@/lib/api";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";

import { groupMoney, sumMoney } from "@/lib/moneyString";
export default function AdminLedgerPage() {
  const { data, error, loading, reload } = useApiData(() => api.getEscrowLedger(), []);
  const items = data ?? [];

  const totalHoldingUsd = sumMoney(items
    .filter((i) => i.escrow_status === "holding")
    .map((i) => i.amount_usd));

  const totalHoldingZar = sumMoney(items
    .filter((i) => i.escrow_status === "holding")
    .map((i) => i.amount_zar));

  const clearedCount = items.filter((i) => i.escrow_status !== "holding").length;
  const holdingCount = items.length - clearedCount;

  if (loading) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-cocoa border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm font-bold text-ink-muted">Loading escrow ledger...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="py-20">
        <ErrorState error={error ?? "No ledger data returned."} title="We could not load the escrow ledger" onRetry={reload} />
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
              <span className="text-xs font-mono font-bold text-cocoa bg-cocoa/10 px-2 py-0.5 rounded-md">
                DOUBLE-ENTRY JOURNAL
              </span>
              <span className="text-xs font-bold text-ink-muted">Multi-Currency Escrow Audit</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
              Escrow Liabilities &amp; Revenue Ledger
            </h1>
          </div>
        </div>

        <Link
          href="/admin/finance/payouts"
          className="min-h-11 inline-flex items-center px-5 py-2.5 bg-cocoa hover:bg-cocoa-hover text-white text-xs font-bold rounded-xl shadow-xs transition-colors self-start sm:self-auto"
        >
          View Bank Batch Payouts &rarr;
        </Link>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <span className="text-xs font-bold text-ink-muted">Total Escrow Liabilities</span>
          <div className="text-2xl sm:text-3xl font-black text-ink font-serif">
            ${groupMoney(totalHoldingUsd)} USD
          </div>
          <p className="text-sm text-ink-muted">R{groupMoney(totalHoldingZar)} ZAR in active holding buffer</p>
        </div>

        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <span className="text-xs font-bold text-ink-muted">Entries Holding in Escrow</span>
          <div className="text-2xl sm:text-3xl font-black text-cocoa font-serif">{holdingCount}</div>
          <p className="text-sm text-ink-muted">Awaiting the 24-hour clearance window</p>
        </div>

        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <span className="text-xs font-bold text-ink-muted">Entries Cleared for Payout</span>
          <div className="text-2xl sm:text-3xl font-black text-success-hover font-serif flex items-center gap-2">
            <ShieldCheck className="w-7 h-7 text-success" />
            <span>{clearedCount}</span>
          </div>
          <p className="text-sm text-ink-muted">Counted from the entries listed below</p>
        </div>
      </div>

      {/* Journal Ledger Table */}
      <div className="bg-white rounded-3xl border border-divider shadow-card overflow-hidden">
        <div className="p-6 border-b border-divider flex items-center justify-between">
          <div>
            <h3 className="text-lg font-black text-ink font-serif">Individual Escrow Ledger Entries</h3>
            <p className="text-sm text-ink-muted">24-hour automatic clearance lifecycle</p>
          </div>
          <span className="text-xs font-bold text-ink-muted">{items.length} Transactions</span>
        </div>

        {items.length === 0 ? (
          <p className="p-8 text-center text-sm text-ink-muted">No escrow ledger entries yet.</p>
        ) : (
        <div className="overflow-x-auto scroll-cue">
          <table className="w-full min-w-[750px] border-collapse text-xs">
            <thead>
              <tr className="bg-cream-surface border-b border-divider text-ink-muted uppercase font-bold tracking-wider text-left">
                <th className="py-3.5 px-6">Booking Ref</th>
                <th className="py-3.5 px-4">Student</th>
                <th className="py-3.5 px-4">Tutor</th>
                <th className="py-3.5 px-4">Gross USD</th>
                <th className="py-3.5 px-4">Tutor Share ZAR</th>
                <th className="py-3.5 px-4">Release Timestamp</th>
                <th className="py-3.5 px-6">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-divider bg-white">
              {items.map((entry) => (
                <tr key={entry.id} className="hover:bg-cream-surface/40 transition-colors">
                  <td className="py-4 px-6 font-mono font-bold text-cocoa">{entry.booking_ref}</td>
                  <td className="py-4 px-4 font-bold text-ink">{entry.student_name}</td>
                  <td className="py-4 px-4 text-ink-muted">{entry.teacher_name}</td>
                  <td className="py-4 px-4 font-bold text-ink">${entry.amount_usd}</td>
                  <td className="py-4 px-4 font-extrabold text-ink font-serif">
                    R{entry.teacher_net_zar}
                  </td>
                  <td className="py-4 px-4 text-ink-muted font-mono">{entry.release_date}</td>
                  <td className="py-4 px-6">
                    {entry.escrow_status === "holding" ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-warning-surface text-warning-hover text-xs font-bold border border-warning-border">
                        <Clock className="w-3 h-3 text-warning" /> In 24h Buffer
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-success-surface text-success-hover text-xs font-bold border border-success-border">
                        <CheckCircle2 className="w-3 h-3 text-success" /> Cleared for Payout
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
      </div>
    </div>
  );
}
