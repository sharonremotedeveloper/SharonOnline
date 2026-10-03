"use client";

import Link from "next/link";
import {
  TrendingUp,
  Radio,
  UserCheck,
  Scale,
  FileSpreadsheet,
  CreditCard,
  ArrowRight,
  ShieldCheck,
  Zap,
  Users,
  DollarSign,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";

import { groupMoney } from "@/lib/moneyString";
export default function AdminDashboardPage() {
  const { data: telemetry, error, loading, reload } = useApiData(() => api.getAdminTelemetry(), []);

  if (error || (!loading && !telemetry)) {
    return (
      <div className="py-20">
        <ErrorState error={error ?? "No telemetry returned."} title="We couldn't load platform telemetry" onRetry={reload} />
      </div>
    );
  }

  if (loading || !telemetry) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-teal border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm font-bold text-ink-muted">Loading executive command telemetry...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Hero Welcome */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-black text-ink font-serif tracking-tight">
            Executive Command Center
          </h1>
          <p className="text-xs sm:text-sm text-ink-muted mt-1">
            Real-time multi-currency telemetry, live Zoom classroom radar, and tutor audition pipeline.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Link
            href="/admin/sessions/live"
            className="px-4 py-2 bg-rose-500 hover:bg-rose-600 text-white text-xs font-black rounded-xl shadow-xs flex items-center gap-2 transition-colors animate-pulse"
          >
            <Radio className="w-4 h-4" />
            <span>{telemetry.active_zoom_sessions_count} Live Sessions Active</span>
          </Link>
        </div>
      </div>

      {/* Primary KPI Grid (4 Metrics) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1: GMV Today */}
        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-ink-muted">
            <span>Gross Volume Today</span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-ink font-serif">
            ${groupMoney(telemetry.gmv_today_usd)}
          </div>
          <p className="text-[11px] text-ink-muted">
            MTD: ${groupMoney(telemetry.gmv_month_usd)} USD
          </p>
        </div>

        {/* Metric 2: Escrow Liabilities */}
        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-ink-muted">
            <span>Escrow Holding Balance</span>
            <span className="text-teal bg-teal/10 px-2 py-0.5 rounded-full text-[10px] font-bold">
              24h Release Buffer
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-teal font-serif">
            R{groupMoney(telemetry.escrow_liability_zar)}
          </div>
          <p className="text-[11px] text-ink-muted">
            Equivalent to ${telemetry.escrow_liability_usd} USD in escrow
          </p>
        </div>

        {/* Metric 3: Pending Vetting */}
        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-ink-muted">
            <span>Tutor Auditions Queue</span>
            <span className="text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full text-[10px] font-bold">
              Action Required
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-amber-700 font-serif">
            {telemetry.pending_vetting_count} Applications
          </div>
          <p className="text-[11px] text-ink-muted">
            Video reels &amp; TEFL certificates awaiting review
          </p>
        </div>

        {/* Metric 4: Open Disputes */}
        <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-ink-muted">
            <span>Dispute Tribunal</span>
            <span className="text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full text-[10px] font-bold">
              Escrow Frozen
            </span>
          </div>
          <div className="text-2xl sm:text-3xl font-black text-rose-600 font-serif">
            {telemetry.open_disputes_count} Open Cases
          </div>
          <p className="text-[11px] text-ink-muted">
            Awaiting admin arbitration against Zoom logs
          </p>
        </div>
      </div>

      {/* Actionable Operations Radar (3 Strategic Cards) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: Vetting Studio */}
        <div className="bg-white rounded-3xl p-6 sm:p-7 border border-divider shadow-card flex flex-col justify-between space-y-6">
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-amber-100 text-amber-800 flex items-center justify-center font-bold">
              <UserCheck className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-black text-ink font-serif">Tutor Video Auditions</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              Review 60-second introduction videos, verify 120h TEFL certificates, and confirm municipal Eskom battery backup declarations.
            </p>
          </div>

          <Link
            href="/admin/teachers/vetting"
            className="w-full py-3 px-4 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow-xs"
          >
            <span>Review {telemetry.pending_vetting_count} Pending Application{telemetry.pending_vetting_count === 1 ? "" : "s"}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* Card 2: Dispute Tribunal */}
        <div className="bg-white rounded-3xl p-6 sm:p-7 border border-divider shadow-card flex flex-col justify-between space-y-6">
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-rose-100 text-rose-700 flex items-center justify-center font-bold">
              <Scale className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-black text-ink font-serif">Dispute Arbitration</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              Inspect student complaints side-by-side with tutor statements and authoritative Zoom webhook dwell-time logs. Execute 1-click refunds.
            </p>
          </div>

          <Link
            href="/admin/disputes"
            className="w-full py-3 px-4 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow-xs"
          >
            <span>Arbitrate {telemetry.open_disputes_count} Open Case{telemetry.open_disputes_count === 1 ? "" : "s"}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* Card 3: Batch Payout Orchestrator */}
        <div className="bg-white rounded-3xl p-6 sm:p-7 border border-divider shadow-card flex flex-col justify-between space-y-6">
          <div className="space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-teal/10 text-teal flex items-center justify-center font-bold">
              <CreditCard className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-black text-ink font-serif">South African EFT Payouts</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              Generate standardized ACB / EFT CSV batch files for cleared ZAR balances. Seamless transfer to Capitec, FNB, Standard Bank, and Nedbank.
            </p>
          </div>

          <Link
            href="/admin/finance/payouts"
            className="w-full py-3 px-4 rounded-xl bg-teal hover:bg-teal-hover text-white font-bold text-xs flex items-center justify-center gap-2 transition-colors shadow-xs"
          >
            <span>Open Payout Orchestrator</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}
