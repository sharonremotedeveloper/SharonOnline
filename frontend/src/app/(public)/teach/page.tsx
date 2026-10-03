"use client";

import { useState } from "react";
import Link from "next/link";
import { DollarSign, ShieldCheck, Zap, ArrowRight, CheckCircle2 } from "lucide-react";

export default function TeachPage() {
  const [lessonsPerDay, setLessonsPerDay] = useState(6);
  const [daysPerWeek, setDaysPerWeek] = useState(5);

  // Earnings model: $6.40 net per 25-min slot ($8.00 gross * 80% payout split)
  // ZAR rate approx R18.50 per USD -> R118.40 per 25-min lesson net
  const netUsdPerLesson = 6.4;
  const netZarPerLesson = 118.4;

  const weeklyLessons = lessonsPerDay * daysPerWeek;
  const monthlyLessons = weeklyLessons * 4.33;

  const monthlyEarningsUsd = Math.round(monthlyLessons * netUsdPerLesson);
  const monthlyEarningsZar = Math.round(monthlyLessons * netZarPerLesson);

  return (
    <div className="space-y-16 pb-16">
      {/* Header */}
      <section className="bg-teal text-white py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/20 text-xs font-bold text-accent-surface">
            <DollarSign className="w-3.5 h-3.5 text-accent" />
            <span>Guaranteed Bi-Weekly South African EFT Payouts</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-extrabold font-serif">Teach English Online with Sharon</h1>
          <p className="text-sm sm:text-base text-white/80 max-w-2xl mx-auto">
            Connect directly with motivated students in Japan, Korea, and Europe. Work from home with total schedule freedom and guaranteed bank transfers.
          </p>
        </div>
      </section>

      {/* Calculator Section */}
      <section className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-white rounded-3xl p-8 border border-divider shadow-card space-y-8">
          <div className="text-center space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Earnings Calculator</h2>
            <h3 className="text-2xl font-extrabold text-ink font-serif">Estimate Your Monthly Tutor Payout</h3>
            <p className="text-xs text-ink-muted">Tutors earn an 80% split ($6.40 / ~R118 net per 25-minute lesson)</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
            <div className="space-y-6">
              <div>
                <div className="flex justify-between text-xs font-bold text-ink mb-2">
                  <span>Lessons Per Day</span>
                  <span className="text-primary">{lessonsPerDay} lessons ({lessonsPerDay * 25} mins)</span>
                </div>
                <input
                  type="range"
                  min="2"
                  max="14"
                  value={lessonsPerDay}
                  onChange={(e) => setLessonsPerDay(parseInt(e.target.value))}
                  className="w-full accent-teal cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs font-bold text-ink mb-2">
                  <span>Days Per Week</span>
                  <span className="text-primary">{daysPerWeek} days / week</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="7"
                  value={daysPerWeek}
                  onChange={(e) => setDaysPerWeek(parseInt(e.target.value))}
                  className="w-full accent-teal cursor-pointer"
                />
              </div>
            </div>

            <div className="bg-cream-surface rounded-2xl p-6 border border-cream-deep text-center space-y-3">
              <div className="text-xs font-bold uppercase tracking-wider text-ink-muted">Estimated Monthly Income</div>
              <div className="text-4xl font-extrabold text-teal font-serif">
                R{monthlyEarningsZar.toLocaleString()} <span className="text-sm font-semibold text-ink-muted">ZAR</span>
              </div>
              <div className="text-xs font-semibold text-ink-muted">
                (Approx. ${monthlyEarningsUsd.toLocaleString()} USD / month)
              </div>
              <div className="text-[11px] text-ink-faint border-t border-divider pt-3">
                Bi-weekly direct bank payouts to FNB, Standard Bank, Capitec, ABSA, Nedbank or Wise.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Tutor Benefits */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
          <ShieldCheck className="w-8 h-8 text-teal" />
          <h4 className="text-base font-bold text-ink font-serif">Direct Bank EFT</h4>
          <p className="text-xs text-ink-muted leading-relaxed">
            No international transfer fees. Receive funds directly into your South African bank account every 1st and 15th of the month.
          </p>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
          <Zap className="w-8 h-8 text-primary" />
          <h4 className="text-base font-bold text-ink font-serif">Power Guard Support</h4>
          <p className="text-xs text-ink-muted leading-relaxed">
            Connect your provider area to Power Guard. Cached outage windows identify vulnerable upcoming lessons and trigger proactive warnings.
          </p>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
          <CheckCircle2 className="w-8 h-8 text-success" />
          <h4 className="text-base font-bold text-ink font-serif">Curriculum Provided</h4>
          <p className="text-xs text-ink-muted leading-relaxed">
            Zero lesson planning needed! Access our CEFR A1-C2 slides, daily news articles, and automated post-lesson memo templates.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-4xl mx-auto px-4 text-center">
        <div className="bg-teal text-white rounded-3xl p-8 space-y-4 shadow-card">
          <h3 className="text-2xl font-extrabold font-serif">Ready to start teaching?</h3>
          <p className="text-xs text-white/80">Submit your application in 5 minutes with your SA ID and TEFL certificate.</p>
          <Link
            href="/register?role=teacher"
            className="inline-flex items-center gap-2 px-8 py-3.5 bg-accent hover:bg-gold-bright text-ink font-extrabold rounded-xl text-xs shadow-sm transition-all"
          >
            Apply to Teach <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
