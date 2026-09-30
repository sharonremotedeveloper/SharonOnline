import { Zap, ShieldCheck, BatteryCharging, Radio } from "lucide-react";

export function PowerGuardCallout() {
  return (
    <div className="bg-gradient-to-r from-teal to-teal-mid text-white rounded-3xl p-8 sm:p-10 shadow-card relative overflow-hidden">
      {/* Background Decorative Pattern */}
      <div className="absolute -right-12 -bottom-12 w-64 h-64 rounded-full bg-white/5 pointer-events-none blur-2xl" />

      <div className="max-w-4xl space-y-6 relative z-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 border border-white/20 text-xs font-bold text-accent-surface">
          <Zap className="w-3.5 h-3.5 text-accent animate-pulse" />
          <span>EskomSePush API Power Resilience Infrastructure</span>
        </div>

        <h3 className="text-2xl sm:text-3xl font-extrabold font-serif leading-snug">
          100% Uninterrupted Lessons. Guaranteed Power Resilience.
        </h3>

        <p className="text-sm sm:text-base text-white/85 leading-relaxed">
          South African tutors are mandatory-verified for solar, inverter, or UPS battery backups. 
          Our proprietary EskomSePush API system monitors municipal load shedding stages, automatically blacking out at-risk slots before students can book them.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
          <div className="bg-white/10 rounded-xl p-4 border border-white/15 flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-accent flex-shrink-0" />
            <div>
              <div className="text-xs font-bold text-white">Power Backups</div>
              <div className="text-[11px] text-white/70">Verified inverter/UPS setup</div>
            </div>
          </div>

          <div className="bg-white/10 rounded-xl p-4 border border-white/15 flex items-center gap-3">
            <Radio className="w-5 h-5 text-accent flex-shrink-0" />
            <div>
              <div className="text-xs font-bold text-white">Grid Telemetry</div>
              <div className="text-[11px] text-white/70">EskomSePush suburb sync</div>
            </div>
          </div>

          <div className="bg-white/10 rounded-xl p-4 border border-white/15 flex items-center gap-3">
            <BatteryCharging className="w-5 h-5 text-accent flex-shrink-0" />
            <div>
              <div className="text-xs font-bold text-white">Zero Disruption</div>
              <div className="text-[11px] text-white/70">Auto 100% refund protection</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
