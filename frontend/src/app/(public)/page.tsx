import Link from "next/link";
import { ArrowRight, CheckCircle2, Star, Video, Clock, Globe, Shield } from "lucide-react";

export default function HomePage() {
  return (
    <div className="space-y-16 pb-16">
      {/* Hero Section */}
      <section className="bg-gradient-to-b from-[#0D4440] to-[#0A3734] text-white pt-16 pb-24 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto text-center space-y-6">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 border border-white/20 text-xs font-semibold text-white/90">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            Live 25-Minute Synchronous Lessons · Japan, Korea & Europe
          </div>

          <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-white leading-tight">
            Real English. <span className="text-gold-500">Real progress.</span>
          </h1>

          <p className="max-w-2xl mx-auto text-lg sm:text-xl text-white/80 font-normal leading-relaxed">
            Master spoken English 1-on-1 with certified native and South African tutors.
            Designed around focused 25-minute synchronous sessions that fit your daily schedule.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
            <Link
              href="/tutors"
              className="w-full sm:w-auto px-8 py-3.5 bg-gold-500 hover:bg-gold-600 text-brand-950 font-bold rounded-xl transition-all shadow-lg text-base flex items-center justify-center gap-2"
            >
              Find Your Tutor <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/materials"
              className="w-full sm:w-auto px-8 py-3.5 bg-white/10 hover:bg-white/20 text-white font-semibold rounded-xl border border-white/20 transition-all text-base flex items-center justify-center gap-2"
            >
              Browse Curriculum
            </Link>
          </div>

          {/* Trust Chips Row */}
          <div className="pt-8 flex flex-wrap items-center justify-center gap-3 text-xs font-semibold text-white/80">
            <span className="px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15">
              1,200+ Active Learners
            </span>
            <span className="px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15">
              Certified TEFL Tutors
            </span>
            <span className="px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15">
              Instant Zoom Classroom
            </span>
            <span className="px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15">
              Automatic Local Timezone
            </span>
          </div>
        </div>
      </section>

      {/* Stats Ribbon */}
      <section className="max-w-7xl mx-auto px-4 -mt-10">
        <div className="bg-white rounded-2xl shadow-card border border-gray-100 p-6 sm:p-8 grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          <div>
            <div className="text-3xl font-extrabold text-brand-900">4.9 ★</div>
            <div className="text-xs text-gray-500 font-medium mt-1">Average Student Rating</div>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-brand-900">25 Min</div>
            <div className="text-xs text-gray-500 font-medium mt-1">High-Focus Lesson Format</div>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-brand-900">100%</div>
            <div className="text-xs text-gray-500 font-medium mt-1">Verified Video Tutors</div>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-brand-900">$8.00</div>
            <div className="text-xs text-gray-500 font-medium mt-1">Starting Price / Class</div>
          </div>
        </div>
      </section>

      {/* How It Works (Engoo/Cambly Pattern) */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <h2 className="text-xs font-bold text-brand-700 tracking-wider uppercase mb-2">Frictionless Experience</h2>
          <p className="text-3xl font-extrabold text-gray-900">How Sharon Online Works</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-brand-50 text-brand-900 flex items-center justify-center font-bold">1</div>
            <h3 className="font-bold text-lg text-gray-900">1. Browse Video Profiles</h3>
            <p className="text-sm text-gray-600 leading-relaxed">
              Watch 1-minute video reels to choose a tutor by accent, teaching specialty, and student reviews.
            </p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-brand-50 text-brand-900 flex items-center justify-center font-bold">2</div>
            <h3 className="font-bold text-lg text-gray-900">2. Pick a 25-Min Slot</h3>
            <p className="text-sm text-gray-600 leading-relaxed">
              Times automatically render in your local Tokyo, Seoul, or European clock. Instant 10-minute slot lock.
            </p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm space-y-3">
            <div className="w-10 h-10 rounded-lg bg-brand-50 text-brand-900 flex items-center justify-center font-bold">3</div>
            <h3 className="font-bold text-lg text-gray-900">3. 1-Click Zoom Class</h3>
            <p className="text-sm text-gray-600 leading-relaxed">
              Join class with 1-click. Receive a structured Lesson Memo with vocabulary cards saved to your bank.
            </p>
          </div>
        </div>
      </section>

      {/* CEFR Curriculum Preview */}
      <section className="bg-brand-50 py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto space-y-8">
          <div className="text-center max-w-2xl mx-auto">
            <h2 className="text-xs font-bold text-brand-700 tracking-wider uppercase mb-2">Structured Learning</h2>
            <p className="text-3xl font-extrabold text-gray-900">Aligned with CEFR International Standards</p>
            <p className="text-sm text-gray-600 mt-2">From A1 Beginner to C2 Proficient conversation</p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            {[
              { level: 'A1', name: 'Beginner', desc: 'Basic greetings & daily phrases' },
              { level: 'A2', name: 'Elementary', desc: 'Simple everyday conversations' },
              { level: 'B1', name: 'Intermediate', desc: 'Travel & work opinions' },
              { level: 'B2', name: 'Upper-Int', desc: 'Debates & professional English' },
              { level: 'C1', name: 'Advanced', desc: 'Fluent idiomatic discussions' },
              { level: 'C2', name: 'Mastery', desc: 'Native nuance & technical speech' },
            ].map((c) => (
              <div key={c.level} className="bg-white rounded-xl p-4 border border-brand-100 shadow-sm text-center">
                <div className="text-2xl font-black text-brand-900">{c.level}</div>
                <div className="text-xs font-bold text-gray-800 mt-1">{c.name}</div>
                <div className="text-[11px] text-gray-500 mt-1 leading-snug">{c.desc}</div>
              </div>
            ))}
          </div>

          <div className="text-center pt-4">
            <Link
              href="/materials"
              className="inline-flex items-center gap-2 text-sm font-bold text-brand-900 hover:text-brand-700"
            >
              Explore all curriculum lesson sheets & worksheets <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center max-w-2xl mx-auto mb-10">
          <h2 className="text-xs font-bold text-brand-700 tracking-wider uppercase mb-2">Student Reviews</h2>
          <p className="text-3xl font-extrabold text-gray-900">What Learners Say</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-card space-y-3">
            <div className="flex text-amber-400 text-sm">★★★★★</div>
            <p className="text-sm text-gray-700 italic leading-relaxed">
              "The 25-minute format is perfect for Tokyo work days. I do a class right on my lunch break and review the vocabulary notes in the evening."
            </p>
            <div className="text-xs font-bold text-gray-900 pt-2">— Aiko T. · Tokyo, Japan</div>
          </div>

          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-card space-y-3">
            <div className="flex text-amber-400 text-sm">★★★★★</div>
            <p className="text-sm text-gray-700 italic leading-relaxed">
              "My tutor in South Africa has such a clear, neutral accent. My confidence speaking in company meetings has improved dramatically."
            </p>
            <div className="text-xs font-bold text-gray-900 pt-2">— Marco R. · Milan, Italy</div>
          </div>

          <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-card space-y-3">
            <div className="flex text-amber-400 text-sm">★★★★★</div>
            <p className="text-sm text-gray-700 italic leading-relaxed">
              "Booking is instant and the Zoom meeting opens immediately with one click. No confusing software or lagging videos."
            </p>
            <div className="text-xs font-bold text-gray-900 pt-2">— Min-jun K. · Seoul, South Korea</div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-[#0D4440] text-white rounded-2xl p-8 sm:p-12 text-center space-y-6 shadow-xl">
          <h2 className="text-3xl sm:text-4xl font-extrabold">Ready to start speaking fluent English?</h2>
          <p className="max-w-xl mx-auto text-sm sm:text-base text-white/80">
            Book your first 25-minute lesson today. No monthly subscription lock-in. Pay as you go or choose a discounted credit pack.
          </p>
          <div className="pt-2">
            <Link
              href="/tutors"
              className="inline-flex items-center gap-2 px-8 py-3.5 bg-gold-500 hover:bg-gold-600 text-brand-950 font-bold rounded-xl transition-all shadow-md text-base"
            >
              Browse Available Tutors <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
