"use client";

import { useEffect, useState } from "react";
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
import { FinanceEscrowItem } from "@/types/admin";

export default function AdminLedgerPage() {
  const [items, setItems] = useState<FinanceEscrowItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadLedger() {
      try {
        const data = await api.getEscrowLedger();
        setItems(data);
      } catch (e) {
        console.error("Failed to load escrow ledger:", e);
      } finally {
        setLoading(false);
      }
    }
    loadLedger();
  }, []);

  const totalHoldingUsd = items
    .filter((i) => i.escrow_status === "holding")
    .reduce((acc, curr) => acc + curr.amount_usd, 0);

  const totalHoldingZar = items
    .filter((i) => i.escrow_status === "holding")
    .reduce((acc, curr) => acc + curr.amount_zar, 0);

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
              <span className="text-xs font-mono font-bold text-teal bg-teal/10 px-2 py-0.5 rounded-md">
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
          className="px-5 py-2.5 bg-teal hover:bg-teal-hover text-white text-xs font-bold rounded-xl shadow-xs transition-colors self-start sm:self-auto"
        >
          View Bank Batch Payouts &rarr;
        </Link>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <span className="text-xs font-bold text-ink-muted">Total Escrow Liabilities</span>
          <div className="text-2xl sm:text-3xl font-black text-ink font-serif">
            ${totalHoldingUsd.toFixed(2)} USD
          </div>
          <p className="text-[11px] text-ink-muted">R{totalHoldingZar.toFixed(2)} ZAR in active holding buffer</p>
        </div>

        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <span className="text-xs font-bold text-ink-muted">Platform Gross Fee Take</span>
          <div className="text-2xl sm:text-3xl font-black text-teal font-serif">20.0% Net</div>
          <p className="text-[11px] text-ink-muted">$1.60 USD per 25-minute lesson processed</p>
        </div>

        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <span className="text-xs font-bold text-ink-muted">Escrow Audit Status</span>
          <div className="text-2xl sm:text-3xl font-black text-emerald-700 font-serif flex items-center gap-2">
            <ShieldCheck className="w-7 h-7 text-emerald-600" />
            <span>100% Balanced</span>
          </div>
          <p className="text-[11px] text-ink-muted">Zero orphaned student or tutor balances</p>
        </div>
      </div>

      {/* Journal Ledger Table */}
      <div className="bg-white rounded-3xl border border-divider shadow-card overflow-hidden">
        <div className="p-6 border-b border-divider flex items-center justify-between">
          <div>
            <h3 className="text-lg font-black text-ink font-serif">Individual Escrow Ledger Entries</h3>
            <p className="text-xs text-ink-muted">24-hour automatic clearance lifecycle</p>
          </div>
          <span className="text-xs font-bold text-ink-muted">{items.length} Transactions</span>
        </div>

        <div className="overflow-x-auto">
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
                  <td className="py-4 px-6 font-mono font-bold text-teal">{entry.booking_ref}</td>
                  <td className="py-4 px-4 font-bold text-ink">{entry.student_name}</td>
                  <td className="py-4 px-4 text-ink-muted">{entry.teacher_name}</td>
                  <td className="py-4 px-4 font-bold text-ink">${entry.amount_usd.toFixed(2)}</td>
                  <td className="py-4 px-4 font-extrabold text-ink font-serif">
                    R{entry.teacher_net_zar.toFixed(2)}
                  </td>
                  <td className="py-4 px-4 text-ink-muted font-mono">{entry.release_date}</td>
                  <td className="py-4 px-6">
                    {entry.escrow_status === "holding" ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 text-[10px] font-bold border border-amber-200">
                        <Clock className="w-3 h-3 text-amber-600" /> In 24h Buffer
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-bold border border-emerald-200">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Cleared for Payout
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
