"use client";

import { useState } from "react";
import Link from "next/link";
import { DollarSign, ShieldCheck, Zap, ArrowRight, CheckCircle2 } from "lucide-react";

export default function TeachPage() {
  const [lessonsPerDay, setLessonsPerDay] = useState(6);
  const [daysPerWeek, setDaysPerWeek] = useState(5);

  const weeklyLessons = lessonsPerDay * daysPerWeek;
  const monthlyLessons = Math.round(weeklyLessons * 4.33);

  return (
    <div className="space-y-16 pb-16">
      {/* Header */}
      <section className="bg-cocoa text-white py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/20 text-sm font-bold text-sun-soft">
            <DollarSign className="w-3.5 h-3.5 text-gold-bright" />
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
            <h2 className="text-sm font-bold uppercase tracking-wider text-primary">Schedule Planner</h2>
            <h3 className="text-2xl font-extrabold text-ink font-serif">Plan Your Teaching Week</h3>
            <p className="text-sm text-ink-muted">Tutors earn a share of every completed 25-minute lesson. Your exact payout per lesson is shown in your tutor wallet.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
            <div className="space-y-6">
              <div>
                <div className="flex justify-between text-sm font-bold text-ink mb-2">
                  <span>Lessons Per Day</span>
                  <span className="text-primary">{lessonsPerDay} lessons ({lessonsPerDay * 25} mins)</span>
                </div>
                <input
                  type="range"
                  aria-label="Lessons per day"
                  min="2"
                  max="14"
                  value={lessonsPerDay}
                  onChange={(e) => setLessonsPerDay(parseInt(e.target.value))}
                  className="w-full accent-cocoa cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-sm font-bold text-ink mb-2">
                  <span>Days Per Week</span>
                  <span className="text-primary">{daysPerWeek} days / week</span>
                </div>
                <input
                  type="range"
                  aria-label="Days per week"
                  min="1"
                  max="7"
                  value={daysPerWeek}
                  onChange={(e) => setDaysPerWeek(parseInt(e.target.value))}
                  className="w-full accent-cocoa cursor-pointer"
                />
              </div>
            </div>

            <div className="bg-cream-surface rounded-2xl p-6 border border-cream-deep text-center space-y-3">
              <div className="text-sm font-bold uppercase tracking-wider text-ink-muted">Estimated Lessons Per Month</div>
              <div className="text-4xl font-extrabold text-cocoa font-serif">
                {monthlyLessons} <span className="text-sm font-semibold text-ink-muted">lessons</span>
              </div>
              <div className="text-sm font-semibold text-ink-muted">
                ({weeklyLessons} lessons / week)
              </div>
              <div className="text-sm text-ink-faint border-t border-divider pt-3">
                Bi-weekly direct bank payouts to FNB, Standard Bank, Capitec, ABSA, Nedbank or Wise.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Tutor Benefits */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
          <ShieldCheck className="w-8 h-8 text-cocoa" />
          <h4 className="text-base font-bold text-ink font-serif">Direct Bank EFT</h4>
          <p className="text-sm text-ink-muted leading-relaxed">
            No international transfer fees. Receive funds directly into your South African bank account every 1st and 15th of the month.
          </p>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
          <Zap className="w-8 h-8 text-primary" />
          <h4 className="text-base font-bold text-ink font-serif">Power Guard Support</h4>
          <p className="text-sm text-ink-muted leading-relaxed">
            Connect your provider area to Power Guard. Cached outage windows identify vulnerable upcoming lessons and trigger proactive warnings.
          </p>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-divider shadow-card space-y-3">
          <CheckCircle2 className="w-8 h-8 text-success" />
          <h4 className="text-base font-bold text-ink font-serif">Curriculum Provided</h4>
          <p className="text-sm text-ink-muted leading-relaxed">
            Zero lesson planning needed! Access our CEFR A1-C2 slides, daily news articles, and automated post-lesson memo templates.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-4xl mx-auto px-4 text-center">
        <div className="bg-cocoa text-white rounded-3xl p-8 space-y-4 shadow-card">
          <h3 className="text-2xl font-extrabold font-serif">Ready to start teaching?</h3>
          <p className="text-sm text-white/80">Submit your application in 5 minutes with your SA ID and TEFL certificate.</p>
          <Link
            href="/register?role=teacher"
            className="inline-flex items-center gap-2 px-8 py-3.5 bg-accent hover:bg-accent-500 text-ink font-extrabold rounded-xl text-sm shadow-sm transition-all"
          >
            Apply to Teach <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
