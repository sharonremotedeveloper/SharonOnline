import Link from "next/link";
import { ShieldCheck, Lock, Award, Radio, RefreshCw, CheckCircle } from "lucide-react";
import { PowerGuardCallout } from "@/components/public/PowerGuardCallout";

export default function TrustSafetyPage() {
  return (
    <div className="space-y-16 pb-16">
      {/* Header */}
      <section className="bg-cocoa text-white py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/20 text-xs font-bold text-accent-surface">
            <ShieldCheck className="w-3.5 h-3.5 text-accent" />
            <span>Uncompromising Trust & Quality Protocol</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-extrabold font-serif">Trust, Safety & Escrow Protection</h1>
          <p className="text-sm sm:text-base text-white/80 max-w-2xl mx-auto">
            From 4-stage tutor screening to Eskom load shedding resilience and 24-hour escrow release guarantees.
          </p>
        </div>
      </section>

      {/* Main Content */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
        <PowerGuardCallout />

        {/* 4 Pillars of Safety */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
            <div className="w-10 h-10 rounded-xl bg-cocoa/10 text-cocoa flex items-center justify-center font-bold">
              <Award className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-ink font-serif">1. Rigorous 4-Stage Vetting</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              Every tutor submits verified South African ID credentials, TEFL certification, speed tests, and a 60-second video audition manually audited by Sharon's team.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
            <div className="w-10 h-10 rounded-xl bg-cocoa/10 text-cocoa flex items-center justify-center font-bold">
              <Lock className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-ink font-serif">2. 24-Hour Escrow Protection</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              Student payments remain safely locked in escrow until the lesson completes and attendance telemetry verifies tutor presence for &gt;= 20 minutes.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
            <div className="w-10 h-10 rounded-xl bg-cocoa/10 text-cocoa flex items-center justify-center font-bold">
              <RefreshCw className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-ink font-serif">3. Automated 100% Refunds</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              If a tutor is late by &gt;5 minutes or experiences an emergency, your lesson credit is instantly re-credited to your account along with a bonus credit.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
