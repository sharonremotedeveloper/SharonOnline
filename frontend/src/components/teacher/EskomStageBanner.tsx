"use client";

import Link from "next/link";
import { Zap, ShieldCheck, AlertTriangle, ArrowRight, BatteryCharging, Radio } from "lucide-react";
import { EskomStatus } from "@/types/teacher";

interface EskomStageBannerProps {
  status: EskomStatus;
  onRefresh?: () => void;
  className?: string;
}

export function EskomStageBanner({ status, className = "" }: EskomStageBannerProps) {
  const isOutageRisk = status.stage > 0 && !status.has_inverter_backup;

  return (
    <div
      className={`rounded-2xl border p-4 sm:p-5 transition-all shadow-sm ${
        status.has_inverter_backup
          ? "bg-success-surface/80 border-success-border text-success-hover"
          : isOutageRisk
          ? "bg-warning-surface/90 border-warning-border text-warning-hover"
          : "bg-cream-surface border-divider text-ink"
      } ${className}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Left: Stage and Suburb */}
        <div className="flex items-start sm:items-center gap-3.5">
          <div
            className={`w-11 h-11 rounded-2xl flex items-center justify-center shrink-0 ${
              status.has_inverter_backup
                ? "bg-success text-white"
                : isOutageRisk
                ? "bg-warning text-white animate-pulse"
                : "bg-cocoa/10 text-cocoa"
            }`}
          >
            <Zap className="w-5 h-5 fill-current" />
          </div>

          <div className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-black uppercase tracking-wider">
                Eskom Grid Status: {status.stage === 0 ? "Normal (No Outages)" : `Stage ${status.stage} Active`}
              </span>
              <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-black/5">
                {status.area_name.split("-")[0].trim()}
              </span>
            </div>

            <p className="text-xs font-medium opacity-90">
              {status.has_inverter_backup ? (
                <span className="flex items-center gap-1.5 text-success-hover font-semibold">
                  <ShieldCheck className="w-3.5 h-3.5 text-success" />
                  Inverter Backup Certified — Your calendar slots remain active &amp; open to global students.
                </span>
              ) : isOutageRisk ? (
                <span className="text-warning-hover font-semibold">
                  Warning: Outage window scheduled {status.next_outage_start} - {status.next_outage_end}.
                  Uncertified slots are temporarily hidden.
                </span>
              ) : (
                "Grid stable. All booking slots are live across global student timezones."
              )}
            </p>
          </div>
        </div>

        {/* Right: Certified Badges & Console Link */}
        <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
          {status.has_inverter_backup && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl bg-success-surface text-success-hover text-xs font-bold">
              <BatteryCharging className="w-3.5 h-3.5 text-success-hover" />
              <span>Inverter Verified</span>
            </span>
          )}

          {status.has_lte_failover && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl bg-cocoa/15 text-cocoa text-xs font-bold hidden sm:inline-flex">
              <Radio className="w-3.5 h-3.5" />
              <span>LTE Failover</span>
            </span>
          )}

          <Link
            href="/teacher/power-guard"
            className="px-3.5 py-1.5 rounded-xl bg-white hover:bg-cream-surface text-ink text-xs font-bold border border-divider shadow-xs flex items-center gap-1 transition-all"
          >
            <span>Power Guard</span>
            <ArrowRight className="w-3 h-3 text-ink-muted" />
          </Link>
        </div>
      </div>
    </div>
  );
}
