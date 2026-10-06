import Link from "next/link";
import { ArrowRight, CheckCircle2, Clock, Video, FileText, Calendar, Sparkles } from "lucide-react";
import { HowItWorksSteps } from "@/components/public/HowItWorksSteps";

export default function HowItWorksPage() {
  return (
    <div className="space-y-16 pb-16">
      {/* Header */}
      <section className="bg-cocoa text-white py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/20 text-xs font-bold text-accent-surface">
            <Sparkles className="w-3.5 h-3.5 text-accent" />
            <span>Frictionless 25-Minute Synchronous Format</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-extrabold font-serif">How Sharon Online Works</h1>
          <p className="text-sm sm:text-base text-white/80 max-w-2xl mx-auto">
            From discovering certified tutors to instant 1-click Zoom entry and post-lesson vocabulary memos — built for rapid English fluency.
          </p>
        </div>
      </section>

      {/* 4-Step Walkthrough */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center space-y-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Simple Step-by-Step</h2>
          <p className="text-2xl font-extrabold text-ink font-serif">Your Path to Speaking Confidence</p>
        </div>
        <HowItWorksSteps />
      </section>

      {/* Deep-Dive Feature Breakdown */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="bg-white p-8 rounded-2xl border border-divider shadow-card space-y-4">
          <div className="w-12 h-12 rounded-xl bg-cocoa/10 text-cocoa flex items-center justify-center">
            <Clock className="w-6 h-6" />
          </div>
          <h3 className="text-xl font-bold text-ink font-serif">Why 25-Minute Sessions?</h3>
          <p className="text-sm text-ink-muted leading-relaxed">
            Cognitive research proves that 25-minute high-focus sessions deliver 3x better retention than grueling 60-minute lectures. It fits easily into busy work schedules in Tokyo, Seoul, or London.
          </p>
          <ul className="space-y-2 text-xs font-semibold text-ink">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Maximum focus without speaking fatigue
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> 5-minute transition buffer between classes
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Easy daily habit building
            </li>
          </ul>
        </div>

        <div className="bg-white p-8 rounded-2xl border border-divider shadow-card space-y-4">
          <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
            <FileText className="w-6 h-6" />
          </div>
          <h3 className="text-xl font-bold text-ink font-serif">Post-Lesson Memos & Vocab Bank</h3>
          <p className="text-sm text-ink-muted leading-relaxed">
            After every lesson, your tutor compiles a personalized Lesson Memo detailing grammar fixes, natural phrasing alternatives, and new vocabulary cards added to your account.
          </p>
          <ul className="space-y-2 text-xs font-semibold text-ink">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Automated review notifications &lt; 24 hours
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Interactive flashcards in student study room
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Exportable study notes & audio logs
            </li>
          </ul>
        </div>
      </section>

      {/* CTA Ribbon */}
      <section className="max-w-5xl mx-auto px-4 text-center">
        <div className="bg-cream-surface rounded-3xl p-8 border border-divider space-y-4">
          <h3 className="text-2xl font-extrabold text-ink font-serif">Ready for your first class?</h3>
          <p className="text-xs text-ink-muted">Choose your preferred tutor and book a 25-minute session in less than 60 seconds.</p>
          <Link
            href="/tutors"
            className="inline-flex items-center gap-2 px-8 py-3.5 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl text-xs shadow-sm transition-all"
          >
            Find a Tutor Now <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
