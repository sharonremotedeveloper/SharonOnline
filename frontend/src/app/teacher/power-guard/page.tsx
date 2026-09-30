"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Zap,
  ShieldCheck,
  BatteryCharging,
  Radio,
  Check,
  AlertTriangle,
  MapPin,
  Clock,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { EskomStatus } from "@/types/teacher";

const SUBURBS = [
  "City of Johannesburg Block 3 - Rosebank/Sandton",
  "City of Johannesburg Block 7 - Randburg",
  "Cape Town City Bowl Area 7",
  "Cape Town Southern Suburbs Area 12",
  "Durban Central Block 1",
  "Pretoria East Area 4",
];

export default function TeacherPowerGuardPage() {
  const [status, setStatus] = useState<EskomStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedArea, setSelectedArea] = useState(SUBURBS[0]);
  const [hasInverter, setHasInverter] = useState(true);
  const [hasLte, setHasLte] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    async function loadData() {
      try {
        const s = await api.getEskomStatus();
        setStatus(s);
        setSelectedArea(s.area_name);
        setHasInverter(s.has_inverter_backup);
        setHasLte(s.has_lte_failover);
      } catch (e) {
        console.error("Failed to load Eskom status:", e);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleSaveCertification = async () => {
    setSaving(true);
    try {
      await api.updatePowerBackup({
        area_name: selectedArea,
        has_inverter_backup: hasInverter,
        has_lte_failover: hasLte,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      console.error("Failed to update power backup:", e);
    } finally {
      setSaving(false);
    }
  };

  if (loading || !status) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center py-20">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-bold text-ink-muted">Connecting to EskomSePush API telemetry...</p>
        </div>
      </div>
    );
  }

  const getStageColor = (stage: number) => {
    if (stage === 0) return "bg-emerald-500 text-white";
    if (stage <= 2) return "bg-amber-500 text-white";
    if (stage <= 4) return "bg-orange-500 text-white";
    return "bg-rose-600 text-white";
  };

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/teacher/dashboard"
              className="p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-md">
                  ESKOM POWER GUARD
                </span>
                <span className="text-xs font-bold text-ink-muted">Grid Resilience Console</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
                Municipal Load Shedding Protection
              </h1>
            </div>
          </div>

          <button
            type="button"
            onClick={handleSaveCertification}
            disabled={saving}
            className="px-6 py-2.5 bg-ink hover:bg-black text-white text-xs font-black rounded-xl shadow-sm flex items-center gap-2 transition-all self-start sm:self-auto"
          >
            {saved ? <Check className="w-4 h-4 text-accent" /> : <ShieldCheck className="w-4 h-4" />}
            <span>{saving ? "Saving..." : saved ? "Certification Saved!" : "Save Hardware Settings"}</span>
          </button>
        </div>

        {/* Live Grid Stage Monitor Card */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-6">
            <div className="space-y-1">
              <span className="text-xs font-bold text-ink-muted uppercase tracking-wider block">Live Eskom Status</span>
              <h2 className="text-xl font-black text-ink font-serif flex items-center gap-2">
                <Zap className="w-5 h-5 text-amber-500 fill-amber-500" />
                <span>Stage {status.stage} Currently Active</span>
              </h2>
              <p className="text-xs text-ink-muted">
                Feed from EskomSePush API · Suburb: <strong>{selectedArea}</strong>
              </p>
            </div>

            <div className="flex items-center gap-1.5 self-start sm:self-auto">
              {[0, 1, 2, 3, 4, 5, 6].map((stg) => (
                <div
                  key={stg}
                  className={`w-9 h-9 rounded-xl flex items-center justify-center text-xs font-black transition-all ${
                    stg === status.stage
                      ? `${getStageColor(stg)} ring-2 ring-black/10 scale-105 shadow-sm`
                      : "bg-cream-surface text-ink-muted border border-divider opacity-50"
                  }`}
                >
                  S{stg}
                </div>
              ))}
            </div>
          </div>

          {/* Suburb Selector */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-teal" />
                <span>Municipal Suburb &amp; Load Shedding Block</span>
              </label>
              <select
                value={selectedArea}
                onChange={(e) => setSelectedArea(e.target.value)}
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs text-ink font-semibold focus:outline-none focus:ring-2 focus:ring-teal/30"
              >
                {SUBURBS.map((sub) => (
                  <option key={sub} value={sub}>
                    {sub}
                  </option>
                ))}
              </select>
            </div>

            <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-1">
              <span className="text-xs font-bold text-ink flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-amber-600" />
                <span>Next Scheduled Outage Window</span>
              </span>
              <p className="text-sm font-extrabold text-ink font-mono">
                {status.next_outage_start || "18:00"} - {status.next_outage_end || "20:30"} SAST
              </p>
              <p className="text-[11px] text-ink-muted">
                Uncertified tutors have unbooked slots hidden during this block.
              </p>
            </div>
          </div>
        </div>

        {/* Hardware Certification Checklist */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
          <div className="border-b border-divider pb-4 space-y-1">
            <h3 className="text-lg font-black text-ink font-serif">Power &amp; Fiber Redundancy Certification</h3>
            <p className="text-xs text-ink-muted">
              Certify your backup hardware to display the &quot;Power Guard Certified&quot; badge and keep all your teaching
              slots visible even during Stage 4-6 outages.
            </p>
          </div>

          <div className="space-y-4">
            {/* Toggle 1: Inverter */}
            <div
              onClick={() => setHasInverter(!hasInverter)}
              className={`p-5 rounded-2xl border transition-all cursor-pointer flex items-start justify-between gap-4 ${
                hasInverter
                  ? "bg-emerald-50/70 border-emerald-300"
                  : "bg-cream-surface border-divider hover:border-gray-300"
              }`}
            >
              <div className="flex items-start gap-3.5">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                    hasInverter ? "bg-emerald-600 text-white" : "bg-cream-deep text-ink-muted"
                  }`}
                >
                  <BatteryCharging className="w-5 h-5" />
                </div>
                <div className="space-y-1">
                  <span className="text-sm font-extrabold text-ink block">
                    Inverter / Solar Lithium Battery Backup
                  </span>
                  <p className="text-xs text-ink-muted leading-relaxed">
                    I certify that my workstation is powered by an inverter, UPS, or solar setup capable of sustaining
                    at least <strong>4 continuous hours</strong> of laptop and Wi-Fi operation during municipal outages.
                  </p>
                </div>
              </div>

              <div
                className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 transition-colors border ${
                  hasInverter ? "bg-emerald-600 border-emerald-600 text-white" : "border-divider bg-white"
                }`}
              >
                {hasInverter && <Check className="w-4 h-4 stroke-[3]" />}
              </div>
            </div>

            {/* Toggle 2: LTE Failover */}
            <div
              onClick={() => setHasLte(!hasLte)}
              className={`p-5 rounded-2xl border transition-all cursor-pointer flex items-start justify-between gap-4 ${
                hasLte
                  ? "bg-teal/10 border-teal/30"
                  : "bg-cream-surface border-divider hover:border-gray-300"
              }`}
            >
              <div className="flex items-start gap-3.5">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                    hasLte ? "bg-teal text-white" : "bg-cream-deep text-ink-muted"
                  }`}
                >
                  <Radio className="w-5 h-5" />
                </div>
                <div className="space-y-1">
                  <span className="text-sm font-extrabold text-ink block">
                    Secondary Cellular LTE / 5G Failover Router
                  </span>
                  <p className="text-xs text-ink-muted leading-relaxed">
                    I maintain an active 4G/5G mobile data router or hotspot that auto-connects if the local fiber node
                    loses power during neighborhood load-shedding.
                  </p>
                </div>
              </div>

              <div
                className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 transition-colors border ${
                  hasLte ? "bg-teal border-teal text-white" : "border-divider bg-white"
                }`}
              >
                {hasLte && <Check className="w-4 h-4 stroke-[3]" />}
              </div>
            </div>
          </div>

          {/* Benefits Callout */}
          <div className="p-4 rounded-2xl bg-cream-surface border border-divider text-xs space-y-2">
            <span className="font-bold text-ink flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-accent" /> Tutor Guarantee &amp; Penalty Shield:
            </span>
            <ul className="text-[11px] text-ink-muted list-disc list-inside space-y-1">
              <li>
                <strong>Badge on Profile:</strong> Displays a green verified battery badge on your card in the student
                tutor directory.
              </li>
              <li>
                <strong>Zero Booking Restrictions:</strong> Your schedule is never blocked during load shedding stages.
              </li>
              <li>
                <strong>Escrow Interruption Shield:</strong> If a sudden catastrophic substation fault occurs, you are
                shielded from negative reviews and cancellation strikes.
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
