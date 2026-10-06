"use client";

import Link from "next/link";
import {
  ArrowLeft,
  DollarSign,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  ArrowRight,
  ShieldCheck,
  CreditCard,
  Download,
} from "lucide-react";
import { api } from "@/lib/api";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";
import { EarningsBreakdownCard } from "@/components/teacher/EarningsBreakdownCard";
import { StatementButton } from "@/components/teacher/StatementButton";

export default function TeacherWalletPage() {
  const { data: wallet, error, loading, reload } = useApiData(() => api.getTeacherWallet(), []);

  if (loading) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center py-20">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-cocoa border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-bold text-ink-muted">Loading earnings and payout ledger...</p>
        </div>
      </div>
    );
  }

  if (error || !wallet) {
    return (
      <div className="min-h-screen bg-cream py-20">
        <div className="max-w-xl mx-auto px-4 space-y-4">
          <ErrorState error={error ?? "No wallet data returned."} title="We couldn't load your earnings wallet" onRetry={reload} />
          <div className="text-center">
            <Link href="/teacher/dashboard" className="min-h-11 inline-flex items-center text-sm font-bold text-cocoa hover:underline">
              Return to dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

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
                <span className="text-xs font-mono font-bold text-success-hover bg-success-surface px-2 py-0.5 rounded-md">
                  ZAR CLEARING LEDGER
                </span>
                <span className="text-xs font-bold text-ink-muted">Tutor Financial Center</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
                Earnings &amp; Payout Wallet
              </h1>
            </div>
          </div>

          <div className="flex flex-wrap items-start gap-2.5 self-start sm:self-auto">
            <StatementButton />
            <Link
              href="/teacher/wallet/payout-settings"
              className="min-h-11 px-5 py-2.5 bg-white hover:bg-cream-surface text-ink text-xs font-bold rounded-xl border border-divider shadow-xs flex items-center gap-2 transition-all"
            >
              <Building2 className="w-4 h-4 text-cocoa" />
              <span>Manage EFT Payout Bank</span>
              <ArrowRight className="w-3.5 h-3.5 text-ink-muted" />
            </Link>
          </div>
        </div>

        {/* Earnings Metric Cards & Fair Revenue Callout */}
        <EarningsBreakdownCard wallet={wallet} />

        {/* Registered Payout Bank Summary */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-2xl bg-cocoa/10 text-cocoa flex items-center justify-center shrink-0">
              <Building2 className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-wider text-ink-muted block">
                Direct EFT Payout Account
              </span>
              {wallet.payout_bank_account ? (
                <>
                  <h3 className="text-lg font-black text-ink font-serif">
                    {wallet.payout_bank_account.bank_name} · {wallet.payout_bank_account.account_number_masked}
                  </h3>
                  <p className="text-sm text-ink-muted">
                    Branch Code: <span className="font-mono font-bold text-ink">{wallet.payout_bank_account.branch_code}</span> ·{" "}
                    Account Type: <span className="capitalize">{wallet.payout_bank_account.account_type}</span>
                  </p>
                </>
              ) : (
                <>
                  <h3 className="text-lg font-black text-ink font-serif">No payout account on file</h3>
                  <p className="text-sm text-ink-muted">Add your bank details to receive payouts.</p>
                </>
              )}
            </div>
          </div>

          {wallet.payout_bank_account && (
            <div className="flex items-center gap-3">
              <span className="text-xs text-success-hover bg-success-surface border border-success-border px-3 py-1.5 rounded-xl font-bold flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-success" />
                <span>Account Configured</span>
              </span>
            </div>
          )}
        </div>

        {/* Transaction History Ledger */}
        <div className="bg-white rounded-3xl border border-divider shadow-card p-6 sm:p-8 space-y-6">
          <div className="flex items-center justify-between border-b border-divider pb-4">
            <div>
              <h3 className="text-lg font-black text-ink font-serif">Lesson Clearing Ledger</h3>
              <p className="text-sm text-ink-muted">Transparent breakdown of gross USD fees and net ZAR settlement</p>
            </div>
            <span className="text-xs font-bold text-ink-muted">Showing {wallet.transactions.length} entries</span>
          </div>

          {wallet.transactions.length === 0 ? (
            <p className="text-sm text-ink-muted text-center py-6">No transactions yet.</p>
          ) : (
          <div className="overflow-x-auto rounded-2xl border border-divider">
            <table className="w-full min-w-[700px] border-collapse text-xs">
              <thead>
                <tr className="bg-cream-surface border-b border-divider text-ink-muted uppercase font-bold tracking-wider text-left">
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Booking Ref</th>
                  <th className="py-3 px-4">Session / Event</th>
                  <th className="py-3 px-4">Captured</th>
                  <th className="py-3 px-4">Net ZAR (80%)</th>
                  <th className="py-3 px-4">Clearing Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-divider bg-white">
                {wallet.transactions.map((tx) => (
                  <tr key={tx.id} className="hover:bg-cream-surface/40 transition-colors">
                    <td className="py-3 px-4 font-medium text-ink-muted">{tx.date}</td>
                    <td className="py-3 px-4 font-mono font-bold text-cocoa">{tx.booking_ref}</td>
                    <td className="py-3 px-4 font-bold text-ink">{tx.student_name}</td>
                    <td className="py-3 px-4 font-medium text-ink-muted">{tx.gross_amount.toFixed(2)} {tx.currency}</td>
                    <td className="py-3 px-4 font-extrabold text-ink font-serif text-sm">
                      R{tx.net_zar.toFixed(2)}
                    </td>
                    <td className="py-3 px-4">
                      {tx.status === "cleared" ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-success-surface text-success-hover text-xs font-bold border border-success-border">
                          <CheckCircle2 className="w-3 h-3 text-success" /> Cleared
                        </span>
                      ) : tx.status === "pending" ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-warning-surface text-warning-hover text-xs font-bold border border-warning-border">
                          <Clock className="w-3 h-3 text-warning" /> In 24h Escrow
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-cocoa/10 text-cocoa text-xs font-bold border border-cocoa/20">
                          <CheckCircle2 className="w-3 h-3 text-cocoa" /> Paid to Bank
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
    </div>
  );
}
