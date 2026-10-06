"use client";

import { DollarSign, ShieldCheck, TrendingUp, Info, Calendar } from "lucide-react";
import { TeacherWalletData } from "@/types/teacher";

interface EarningsBreakdownCardProps {
  wallet: TeacherWalletData;
  className?: string;
}

export function EarningsBreakdownCard({ wallet, className = "" }: EarningsBreakdownCardProps) {
  return (
    <div className={`space-y-6 ${className}`}>
      {/* 3 Metric Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Card 1: Cleared Balance ZAR */}
        <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-ink-muted">
            <span>Cleared for Payout</span>
            <span className="text-success-hover bg-success-surface px-2 py-0.5 rounded-full text-xs">
              Ready for EFT
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-success-hover font-serif">
            R{wallet.cleared_balance_zar.toLocaleString("en-ZA", { minimumFractionDigits: 2 })}
          </div>
          <p className="text-xs text-ink-muted">Derived from ledger account 2020.</p>
        </div>

        {/* Card 2: Pending Escrow */}
        <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-ink-muted">
            <span>In 24h Escrow</span>
            <span className="text-warning-hover bg-warning-surface px-2 py-0.5 rounded-full text-xs">
              Holding Buffer
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-ink font-serif">
            R{wallet.pending_escrow_zar.toFixed(2)}{" "}
            <span className="text-xs font-normal text-ink-muted">ZAR value</span>
          </div>
          <p className="text-xs text-ink-muted">
            Captured funding valued at each lesson&apos;s stored FX snapshot.
          </p>
        </div>

        {/* Card 3: Payout FX Rate */}
        <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-ink-muted">
            <span>Capture FX Context</span>
            <span className="text-cocoa bg-cocoa/10 px-2 py-0.5 rounded-full text-xs font-bold">
              Immutable snapshots
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-cocoa font-serif">
            {wallet.fx_context.length}
          </div>
          <p className="text-xs text-ink-muted">
            {wallet.fx_context.length ? wallet.fx_context.map((fx) => `${fx.currency} @ ${fx.fx_rate_to_zar}`).join(" · ") : "No funded lessons yet"}
          </p>
        </div>
      </div>

      {/* Revenue Transparency Callout */}
      <div className="p-5 rounded-2xl bg-cream-surface border border-divider space-y-2 text-xs text-ink leading-relaxed">
        <div className="flex items-center gap-2 font-bold text-cocoa">
          <Info className="w-4 h-4 shrink-0" />
          <span>Fair Payout Structure &amp; Escrow Guarantee</span>
        </div>
        <p className="text-xs text-ink-muted">
          Tutors receive an <strong>80% share of the amount actually captured</strong>, including the discount when a
          student used a lesson pack. Every row retains its transaction currency and capture-time ZAR valuation;
          escrow releases only after the verified settlement workflow completes.
        </p>
      </div>
    </div>
  );
}
