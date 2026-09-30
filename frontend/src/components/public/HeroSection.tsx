"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Play, CheckCircle2, Star, Shield, Clock } from "lucide-react";
import { Modal } from "@/components/ui/Modal";

export function HeroSection() {
  const [showVideoModal, setShowVideoModal] = useState(false);

  return (
    <section className="bg-gradient-to-b from-teal to-teal-hover text-white pt-16 pb-24 px-4 sm:px-6 lg:px-8 relative overflow-hidden">
      <div className="max-w-6xl mx-auto text-center space-y-6 relative z-10">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/10 border border-white/20 text-xs font-bold text-accent-surface">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          <span>Live 25-Minute Synchronous English Lessons · Japan, Korea & Europe</span>
        </div>

        <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold font-serif tracking-tight text-white leading-tight">
          Real English. <span className="text-gold-bright">Real Progress.</span>
        </h1>

        <p className="max-w-2xl mx-auto text-base sm:text-lg text-white/85 font-normal leading-relaxed">
          Master spoken English 1-on-1 with certified native and South African tutors.
          Designed around focused 25-minute synchronous sessions with instant Zoom access and personalized lesson memos.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
          <Link
            href="/tutors"
            className="w-full sm:w-auto px-8 py-4 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl transition-all shadow-lg text-sm flex items-center justify-center gap-2"
          >
            Find Your Tutor <ArrowRight className="w-4 h-4" />
          </Link>

          <button
            onClick={() => setShowVideoModal(true)}
            className="w-full sm:w-auto px-8 py-4 bg-white/10 hover:bg-white/20 text-white font-bold rounded-xl border border-white/20 transition-all text-sm flex items-center justify-center gap-2"
          >
            <Play className="w-4 h-4 text-accent fill-accent" /> Watch 60-Sec Demo
          </button>
        </div>

        {/* Feature Badges */}
        <div className="pt-8 flex flex-wrap items-center justify-center gap-3 text-xs font-semibold text-white/80">
          <span className="px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15 flex items-center gap-1.5">
            <Star className="w-3.5 h-3.5 text-accent fill-accent" /> 4.98 Rating (1,400+ Reviews)
          </span>
          <span className="px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-accent" /> 25-Min Focused Slots
          </span>
          <span className="px-3.5 py-1.5 rounded-full bg-white/10 border border-white/15 flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-accent" /> Eskom Power Guard Resilience
          </span>
        </div>
      </div>

      {/* Video Modal */}
      <Modal isOpen={showVideoModal} onClose={() => setShowVideoModal(false)} title="Sharon Online Classroom Demo">
        <div className="space-y-4">
          <div className="aspect-video bg-black rounded-xl overflow-hidden relative">
            <iframe
              src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?autoplay=1"
              title="Sharon Online Demo"
              className="w-full h-full border-0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
          <p className="text-xs text-ink-muted">
            Demonstration of synchronous 25-minute lesson, split-screen materials reader, and real-time tutor notes.
          </p>
        </div>
      </Modal>
    </section>
  );
}
