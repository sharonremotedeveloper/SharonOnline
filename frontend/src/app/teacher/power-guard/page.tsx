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
import { ErrorState, InlineError } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";

export default function TeacherPowerGuardPage() {
  const { data: status, error: loadError, loading, reload } = useApiData(() => api.getEskomStatus(), []);
  const [hasInverter, setHasInverter] = useState(false);
  const [hasLte, setHasLte] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);

  useEffect(() => {
    if (status) {
      setHasInverter(status.has_inverter_backup);
      setHasLte(status.has_lte_failover);
    }
  }, [status]);

  const handleSaveCertification = async () => {
    setSaving(true);
    setSaved(false);
    setSaveError(null);
    try {
      await api.updatePowerBackup({
        has_inverter_backup: hasInverter,
        has_lte_failover: hasLte,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      console.error("Failed to update power backup:", e);
      setSaveError(e);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center py-20">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-warning border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-bold text-ink-muted">Loading the latest cached Power Guard status...</p>
        </div>
      </div>
    );
  }

  if (loadError || !status) {
    return (
      <div className="min-h-screen bg-cream py-20">
        <div className="max-w-xl mx-auto px-4 space-y-4">
          <ErrorState
            error={loadError ?? "No Power Guard data returned."}
            title="Power Guard isn't available right now"
            onRetry={reload}
          />
          <div className="text-center">
            <Link href="/teacher/dashboard" className="min-h-11 inline-flex items-center text-sm font-bold text-cocoa hover:underline">
              Return to dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const getStageColor = (stage: number) => {
    if (stage === 0) return "bg-success text-white";
    if (stage <= 2) return "bg-warning text-white";
    if (stage <= 4) return "bg-primary text-white";
    return "bg-error text-white";
  };

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Header */}
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
                <span className="text-xs font-mono font-bold text-warning-hover bg-warning-surface px-2 py-0.5 rounded-md">
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
            className="min-h-11 px-6 py-2.5 bg-ink hover:bg-black text-white text-xs font-black rounded-xl shadow-sm flex items-center gap-2 transition-all self-start sm:self-auto"
          >
            {saved ? <Check className="w-4 h-4 text-gold-bright" /> : <ShieldCheck className="w-4 h-4" />}
            <span>{saving ? "Saving..." : saved ? "Certification Saved!" : "Save Hardware Settings"}</span>
          </button>
        </div>

        <InlineError error={saveError} />

        {status.stale && (
          <div className="p-4 rounded-2xl bg-warning-surface border border-warning-border text-xs text-warning-hover flex gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              Showing the last provider reading from {new Date(status.retrieved_at).toLocaleString()}. Provider state: {status.provider_status}.
            </span>
          </div>
        )}

        {/* Live Grid Stage Monitor Card */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-6">
            <div className="space-y-1">
              <span className="text-xs font-bold text-ink-muted uppercase tracking-wider block">Live Eskom Status</span>
              <h2 className="text-xl font-black text-ink font-serif flex items-center gap-2">
                <Zap className="w-5 h-5 text-warning fill-warning" />
                <span>Stage {status.stage} Currently Active</span>
              </h2>
              <p className="text-sm text-ink-muted">
                Cached EskomSePush reading · Area: <strong>{status.area_name}</strong>
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

          {/* Provider area and next outage */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-cocoa" />
                <span>Municipal Suburb &amp; Load Shedding Block</span>
              </label>
              <div className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs text-ink font-semibold">
                {status.area_name}
              </div>
              <p className="text-sm text-ink-muted">Area mapping is managed by support and provider identifiers are not guessed in this form.</p>
            </div>

            <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-1">
              <span className="text-xs font-bold text-ink flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-warning" />
                <span>Next Scheduled Outage Window</span>
              </span>
              <p className="text-sm font-extrabold text-ink font-mono">
                {status.next_outage_start && status.next_outage_end
                  ? `${new Date(status.next_outage_start).toLocaleString()} - ${new Date(status.next_outage_end).toLocaleString()}`
                  : "No outage window reported"}
              </p>
              <p className="text-sm text-ink-muted">
                Uncertified tutors have unbooked slots hidden during this block.
              </p>
            </div>
          </div>
        </div>

        {/* Hardware Certification Checklist */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
          <div className="border-b border-divider pb-4 space-y-1">
            <h3 className="text-lg font-black text-ink font-serif">Power &amp; Fiber Redundancy Certification</h3>
            <p className="text-sm text-ink-muted">
              Record the backup hardware used when the platform evaluates risk for upcoming lessons.
            </p>
          </div>

          <div className="space-y-4">
            {/* Toggle 1: Inverter */}
            <div
              onClick={() => setHasInverter(!hasInverter)}
              className={`p-5 rounded-2xl border transition-all cursor-pointer flex items-start justify-between gap-4 ${
                hasInverter
                  ? "bg-success-surface/70 border-success-border"
                  : "bg-cream-surface border-divider hover:border-cocoa-300"
              }`}
            >
              <div className="flex items-start gap-3.5">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                    hasInverter ? "bg-success text-white" : "bg-cream-deep text-ink-muted"
                  }`}
                >
                  <BatteryCharging className="w-5 h-5" />
                </div>
                <div className="space-y-1">
                  <span className="text-sm font-extrabold text-ink block">
                    Inverter / Solar Lithium Battery Backup
                  </span>
                  <p className="text-sm text-ink-muted leading-relaxed">
                    I certify that my workstation is powered by an inverter, UPS, or solar setup capable of sustaining
                    at least <strong>4 continuous hours</strong> of laptop and Wi-Fi operation during municipal outages.
                  </p>
                </div>
              </div>

              <div
                className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 transition-colors border ${
                  hasInverter ? "bg-success border-success text-white" : "border-divider bg-white"
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
                  ? "bg-cocoa/10 border-cocoa/30"
                  : "bg-cream-surface border-divider hover:border-cocoa-300"
              }`}
            >
              <div className="flex items-start gap-3.5">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                    hasLte ? "bg-cocoa text-white" : "bg-cream-deep text-ink-muted"
                  }`}
                >
                  <Radio className="w-5 h-5" />
                </div>
                <div className="space-y-1">
                  <span className="text-sm font-extrabold text-ink block">
                    Secondary Cellular LTE / 5G Failover Router
                  </span>
                  <p className="text-sm text-ink-muted leading-relaxed">
                    I maintain an active 4G/5G mobile data router or hotspot that auto-connects if the local fiber node
                    loses power during neighborhood load-shedding.
                  </p>
                </div>
              </div>

              <div
                className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 transition-colors border ${
                  hasLte ? "bg-cocoa border-cocoa text-white" : "border-divider bg-white"
                }`}
              >
                {hasLte && <Check className="w-4 h-4 stroke-[3]" />}
              </div>
            </div>
          </div>

          {/* Benefits Callout */}
          <div className="p-4 rounded-2xl bg-cream-surface border border-divider text-xs space-y-2">
            <span className="font-bold text-ink flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-cocoa" aria-hidden="true" /> Tutor Guarantee &amp; Penalty Shield:
            </span>
            <ul className="text-xs text-ink-muted list-disc list-inside space-y-1">
              <li>
                <strong>Risk assessment:</strong> Power and connectivity backup are considered together for proactive alerts.
              </li>
              <li>
                <strong>Advance warning:</strong> At-risk lessons receive idempotent notifications from cached provider windows.
              </li>
              <li>
                <strong>Evidence:</strong> Student-reported outages require fresh provider corroboration or tutor/staff confirmation.
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
