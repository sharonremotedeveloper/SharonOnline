"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CreditCard,
  Download,
  CheckCircle2,
  Building2,
  ShieldCheck,
  FileText,
  Clock,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { PayoutBatchItem } from "@/types/admin";
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

  // Generate and download verified South African ACB CSV
  const handleExportCsv = () => {
    if (batch.length === 0) return;
    const headers = "RecipientName,BankName,UniversalBranchCode,AccountNumberMasked,LessonCount,AmountZAR,BatchDate\n";
    const rows = batch
      .map(
        (b) =>
          `"${b.teacher_name}","${b.bank_name}","${b.branch_code}","${b.account_number_masked}",${b.cleared_lessons_count},${b.payout_amount_zar},"${new Date().toISOString().split("T")[0]}"`
      )
      .join("\n");

    const blob = new Blob([headers + rows], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `SHARON_ONLINE_ACB_BATCH_${new Date().toISOString().split("T")[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-teal border-t-transparent rounded-full animate-spin mx-auto" />
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
              <span className="text-xs font-bold text-ink-muted">Bi-Weekly Settlement Cycle</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
              Bank Batch Payout Orchestrator
            </h1>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 self-start sm:self-auto">
          <button
            type="button"
            onClick={handleExportCsv}
            className="px-4 py-2.5 bg-white hover:bg-cream-surface text-ink text-xs font-bold rounded-xl border border-divider shadow-xs flex items-center gap-2 transition-all"
          >
            <Download className="w-4 h-4 text-teal" />
            <span>Export Bank ACB CSV</span>
          </button>

          <button
            type="button"
            disabled
            title="Requires an approved banking rail and maker-checker workflow"
            className="px-5 py-2.5 bg-ink-muted text-white text-xs font-black rounded-xl shadow-sm flex items-center gap-2 opacity-60 cursor-not-allowed"
          >
            <CreditCard className="w-4 h-4" />
            <span>Payout execution unavailable</span>
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
          <span className="text-xs font-bold text-ink-muted">Total Batch Settlement</span>
          <div className="text-2xl sm:text-3xl font-black text-emerald-800 font-serif">
            R{groupMoney(totalPayoutZar)} ZAR
          </div>
          <p className="text-[11px] text-ink-muted">Across {batch.length} tutor{batch.length === 1 ? "" : "s"}</p>
        </div>

        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
          <span className="text-xs font-bold text-ink-muted">Banking Rail</span>
          <div className="text-2xl sm:text-3xl font-black text-teal font-serif flex items-center gap-2">
            <Building2 className="w-6 h-6" />
            <span>SARB ACB</span>
          </div>
          <p className="text-[11px] text-ink-muted">Direct South African EFT inter-bank clearing</p>
        </div>

        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
          <span className="text-xs font-bold text-ink-muted">Settlement Schedule</span>
          <div className="text-2xl sm:text-3xl font-black text-ink font-serif">1st &amp; 15th</div>
          <p className="text-[11px] text-ink-muted">Automated bi-weekly clearing window</p>
        </div>
      </div>

      {/* Payout Batch Table */}
      <div className="bg-white rounded-3xl border border-divider shadow-card overflow-hidden">
        <div className="p-6 border-b border-divider flex items-center justify-between">
          <div>
            <h3 className="text-lg font-black text-ink font-serif">Recipients Roster</h3>
            <p className="text-xs text-ink-muted">Verified 6-digit universal branch codes</p>
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
                  <td className="py-4 px-4 font-mono font-bold text-teal">{b.branch_code}</td>
                  <td className="py-4 px-4 font-mono text-ink-muted">{b.account_number_masked}</td>
                  <td className="py-4 px-4 font-bold text-ink">{b.cleared_lessons_count} Lessons</td>
                  <td className="py-4 px-4 font-black text-emerald-800 font-serif text-sm">
                    R{b.payout_amount_zar}
                  </td>
                  <td className="py-4 px-6">
                    {b.status === "processed" ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-bold border border-emerald-200">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Settled
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 text-[10px] font-bold border border-amber-200">
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
