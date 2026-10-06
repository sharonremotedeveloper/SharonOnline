import Link from "next/link";
import { ArrowRight, CheckCircle2, Clock, Video, FileText, Calendar, Sparkles } from "lucide-react";
import { HowItWorksSteps } from "@/components/public/HowItWorksSteps";

export default function HowItWorksPage() {
  return (
    <div className="space-y-16 pb-16">
      {/* Header */}
      <section className="bg-cocoa text-white py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/20 text-sm font-bold text-sun-soft">
            <Sparkles className="w-3.5 h-3.5 text-gold-bright" />
            <span>25-minute lessons</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-extrabold font-serif">How Sharon Online Works</h1>
          <p className="text-sm sm:text-base text-white/80 max-w-2xl mx-auto">
            Choose a tutor, pick a time, join your lesson in the browser, and get notes with new words afterwards.
          </p>
        </div>
      </section>

      {/* 4-Step Walkthrough */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center space-y-2">
          <h2 className="text-sm font-bold uppercase tracking-wider text-primary">Simple Step-by-Step</h2>
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
          <h3 className="text-xl font-bold text-ink font-serif">Why 25-minute lessons?</h3>
          <p className="text-sm text-ink-muted leading-relaxed">
            A short lesson is easy to fit into a busy day in Tokyo, Seoul or London. You stay focused, you speak the whole time, and it is simple to build a daily habit.
          </p>
          <ul className="space-y-2 text-sm font-semibold text-ink">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Stay focused without getting tired
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> A short break between lessons for your tutor
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Easy to make a daily habit
            </li>
          </ul>
        </div>

        <div className="bg-white p-8 rounded-2xl border border-divider shadow-card space-y-4">
          <div className="w-12 h-12 rounded-xl bg-cocoa/10 text-primary flex items-center justify-center">
            <FileText className="w-6 h-6" />
          </div>
          <h3 className="text-xl font-bold text-ink font-serif">Post-Lesson Memos & Vocab Bank</h3>
          <p className="text-sm text-ink-muted leading-relaxed">
            After every lesson, your tutor compiles a personalized Lesson Memo detailing grammar fixes, natural phrasing alternatives, and new vocabulary cards added to your account.
          </p>
          <ul className="space-y-2 text-sm font-semibold text-ink">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Your notes arrive after the lesson
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> Interactive flashcards in student study room
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success" /> New words saved to your flashcards
            </li>
          </ul>
        </div>
      </section>

      {/* CTA Ribbon */}
      <section className="max-w-5xl mx-auto px-4 text-center">
        <div className="bg-cream-surface rounded-3xl p-8 border border-divider space-y-4">
          <h3 className="text-2xl font-extrabold text-ink font-serif">Ready for your first lesson?</h3>
          <p className="text-base text-ink-muted">Choose a tutor and book a time. It takes about a minute.</p>
          <Link
            href="/tutors"
            className="min-h-11 inline-flex items-center gap-2 px-8 py-3.5 bg-cocoa hover:bg-cocoa-hover text-white font-bold rounded-xl text-sm shadow-sm transition-all"
          >
            Find a Tutor Now <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
