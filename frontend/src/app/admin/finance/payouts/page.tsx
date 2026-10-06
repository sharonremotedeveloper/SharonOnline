"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  Building2,
  ShieldCheck,
  FileText,
  Clock,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { PayoutBatchItem } from "@/types/admin";
import { PayoutRuns } from "@/components/admin/PayoutRuns";
import { ErrorState } from "@/components/ui/ErrorState";

import { groupMoney, sumMoney } from "@/lib/moneyString";
export default function AdminPayoutsPage() {
  const [batch, setBatch] = useState<PayoutBatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function loadBatch() {
      setLoading(true);
      setLoadError(null);
      try {
        const data = await api.getPayoutBatch();
        if (!cancelled) setBatch(data);
      } catch (e) {
        console.error("Failed to load payout batch:", e);
        if (!cancelled) {
          setBatch([]);
          setLoadError(e);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadBatch();
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  const totalPayoutZar = sumMoney(batch.map((b) => b.payout_amount_zar));

  if (loading) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-cocoa border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm font-bold text-ink-muted">Loading South African EFT batch orchestrator...</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="py-20">
        <ErrorState
          error={loadError}
          title="We could not load the payout batch"
          onRetry={() => setReloadTick((t) => t + 1)}
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
            className="p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-md">
                ACB / EFT ORCHESTRATOR
              </span>
              <span className="text-xs font-bold text-ink-muted">Preview of what is owed now</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
              Bank Batch Payout Orchestrator
            </h1>
          </div>
        </div>

      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
          <span className="text-xs font-bold text-ink-muted">Total Batch Settlement</span>
          <div className="text-2xl sm:text-3xl font-black text-emerald-800 font-serif">
            R{groupMoney(totalPayoutZar)} ZAR
          </div>
          <p className="text-xs text-ink-muted">Across {batch.length} tutor{batch.length === 1 ? "" : "s"}</p>
        </div>

        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
          <span className="text-xs font-bold text-ink-muted">Banking Rail</span>
          <div className="text-2xl sm:text-3xl font-black text-cocoa font-serif flex items-center gap-2">
            <Building2 className="w-6 h-6" />
            <span>SARB ACB</span>
          </div>
          <p className="text-xs text-ink-muted">Direct South African EFT inter-bank clearing</p>
        </div>

        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
          <span className="text-xs font-bold text-ink-muted">Settlement Schedule</span>
          <div className="text-2xl sm:text-3xl font-black text-ink font-serif">Manual</div>
          <p className="text-xs text-ink-muted">A person creates, approves and confirms every run</p>
        </div>
      </div>

      <PayoutRuns onChanged={() => setReloadTick((t) => t + 1)} />

      {/* Payout Batch Table */}
      <div className="bg-white rounded-3xl border border-divider shadow-card overflow-hidden">
        <div className="p-6 border-b border-divider flex items-center justify-between">
          <div>
            <h3 className="text-lg font-black text-ink font-serif">Owed now (preview)</h3>
            <p className="text-xs text-ink-muted">Cleared balances of tutors with a bank account. Create a payout run above to pay them.</p>
          </div>
          <span className="text-xs font-bold text-ink-muted">{batch.length} Accounts Queued</span>
        </div>

        {batch.length === 0 ? (
          <p className="p-8 text-center text-xs text-ink-muted">No cleared balances are waiting for payout.</p>
        ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[750px] border-collapse text-xs">
            <thead>
              <tr className="bg-cream-surface border-b border-divider text-ink-muted uppercase font-bold tracking-wider text-left">
                <th className="py-3.5 px-6">Tutor Recipient</th>
                <th className="py-3.5 px-4">Bank Institution</th>
                <th className="py-3.5 px-4">Branch Code</th>
                <th className="py-3.5 px-4">Masked Account</th>
                <th className="py-3.5 px-4">Cleared Classes</th>
                <th className="py-3.5 px-4">Payout Total</th>
                <th className="py-3.5 px-6">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-divider bg-white">
              {batch.map((b) => (
                <tr key={b.id} className="hover:bg-cream-surface/40 transition-colors">
                  <td className="py-4 px-6 font-extrabold text-ink">{b.teacher_name}</td>
                  <td className="py-4 px-4 font-semibold text-ink-muted">{b.bank_name}</td>
                  <td className="py-4 px-4 font-mono font-bold text-cocoa">{b.branch_code}</td>
                  <td className="py-4 px-4 font-mono text-ink-muted">{b.account_number_masked}</td>
                  <td className="py-4 px-4 font-bold text-ink">{b.cleared_lessons_count} Lessons</td>
                  <td className="py-4 px-4 font-black text-emerald-800 font-serif text-sm">
                    R{b.payout_amount_zar}
                  </td>
                  <td className="py-4 px-6">
                    {b.status === "processed" ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-xs font-bold border border-emerald-200">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Settled
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 text-xs font-bold border border-amber-200">
                        <Clock className="w-3 h-3 text-amber-600" /> Ready for EFT
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
