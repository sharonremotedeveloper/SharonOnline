"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Calendar,
  Clock,
  Video,
  BookOpen,
  Award,
  ChevronRight,
  ExternalLink,
  Star,
  Sparkles
} from "lucide-react";

export default function StudentDashboardPage() {
  const [activeTab, setActiveTab] = useState<'upcoming' | 'vocabulary' | 'history'>('upcoming');

  // Realistic mock state for demonstration
  const nextLesson = {
    tutorName: "Naledi Molefe",
    tutorAccent: "🇿🇦 South African",
    avatar: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&q=80&w=300",
    date: "Tomorrow · Sat, Sep 26",
    time: "15:00 JST (06:00 UTC)",
    zoomUrl: "https://zoom.us/j/9876543210",
    materialTitle: "Global Remote Work Trends in 2026",
    materialCefr: "B2",
  };

  const vocabularyBank = [
    { word: "Asynchronous", def: "Not occurring at the same time; communication via messages rather than real-time calls.", lesson: "Remote Work Trends (B2)", date: "Sep 22" },
    { word: "Resilience", def: "The capacity to recover quickly from difficulties; toughness.", lesson: "Business Fluency (B1)", date: "Sep 20" },
    { word: "Ubiquitous", def: "Present, appearing, or found everywhere.", lesson: "Daily News & Tech (C1)", date: "Sep 18" },
    { word: "Nuance", def: "A subtle difference in or shade of meaning, expression, or sound.", lesson: "FreeTalk Practice (B2)", date: "Sep 15" },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-gray-900 tracking-tight">Student Command Center</h1>
          <p className="text-xs sm:text-sm text-gray-500">Welcome back, Aiko! Track your 25-minute lessons and vocabulary progress.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="bg-white border border-gray-200 px-4 py-2 rounded-xl text-xs shadow-sm">
            <span className="text-gray-500">Credits Remaining:</span>{" "}
            <strong className="text-brand-900 text-sm font-black">3 Credits</strong>
          </div>
          <Link
            href="/tutors"
            className="px-4 py-2 bg-brand-900 hover:bg-brand-950 text-white font-bold text-xs rounded-xl shadow-sm transition-all"
          >
            Book Lesson
          </Link>
        </div>
      </div>

      {/* Next Upcoming Lesson Spotlight Card */}
      <div className="bg-gradient-to-r from-[#0D4440] to-[#12534E] text-white rounded-2xl p-6 sm:p-8 shadow-xl space-y-6">
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-2 text-xs font-bold bg-white/10 border border-white/20 px-3 py-1 rounded-full text-gold-500">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> Next Scheduled Lesson
          </span>
          <span className="text-xs text-white/70 font-medium">Starts in 18 hrs 25 mins</span>
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <img
              src={nextLesson.avatar}
              alt={nextLesson.tutorName}
              className="w-16 h-16 rounded-full object-cover border-2 border-white/30"
            />
            <div className="space-y-1">
              <h2 className="text-xl sm:text-2xl font-black">{nextLesson.tutorName}</h2>
              <div className="text-xs text-white/80">{nextLesson.tutorAccent}</div>
              <div className="text-xs text-gold-500 font-semibold flex items-center gap-1 mt-1">
                <BookOpen className="w-3.5 h-3.5" />
                Lesson Sheet: [{nextLesson.materialCefr}] {nextLesson.materialTitle}
              </div>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <div className="bg-white/10 rounded-xl px-4 py-3 text-center sm:text-left border border-white/15 text-xs space-y-0.5">
              <div className="text-white/70">Scheduled Time</div>
              <div className="font-extrabold text-sm">{nextLesson.date}</div>
              <div className="text-gold-500 font-bold">{nextLesson.time}</div>
            </div>

            <a
              href={nextLesson.zoomUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3.5 bg-gold-500 hover:bg-gold-600 text-brand-950 font-black rounded-xl text-sm transition-all shadow-lg flex items-center justify-center gap-2"
            >
              <Video className="w-4 h-4" /> Launch Zoom Classroom
            </a>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-gray-200 gap-6 text-sm font-bold">
        <button
          onClick={() => setActiveTab('upcoming')}
          className={`pb-3 border-b-2 transition-all ${
            activeTab === 'upcoming'
              ? 'border-brand-900 text-brand-900'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          My Classes
        </button>
        <button
          onClick={() => setActiveTab('vocabulary')}
          className={`pb-3 border-b-2 transition-all flex items-center gap-1.5 ${
            activeTab === 'vocabulary'
              ? 'border-brand-900 text-brand-900'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Sparkles className="w-4 h-4 text-gold-500" /> "My Words" Vocabulary Bank
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'vocabulary' ? (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <p className="text-xs text-gray-500">
              Words, expressions, and pronunciation tips saved directly from your tutors' lesson memos.
            </p>
            <span className="text-xs font-bold text-gray-700">{vocabularyBank.length} Flashcards</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {vocabularyBank.map((item, idx) => (
              <div key={idx} className="bg-white p-5 rounded-2xl border border-gray-100 shadow-card space-y-2">
                <div className="flex justify-between items-start">
                  <h3 className="text-lg font-black text-brand-900">{item.word}</h3>
                  <span className="text-[10px] text-gray-400 font-medium">{item.date}</span>
                </div>
                <p className="text-xs text-gray-600 leading-relaxed">{item.def}</p>
                <div className="text-[11px] text-gray-400 pt-2 border-t border-gray-50 flex items-center gap-1">
                  <BookOpen className="w-3 h-3" /> From memo: {item.lesson}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="bg-white rounded-2xl border border-gray-100 shadow-card divide-y divide-gray-100">
            <div className="p-5 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-brand-50 text-brand-900 flex items-center justify-center font-bold">
                  <Calendar className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-bold text-sm text-gray-900">Completed Lesson with Naledi Molefe</h4>
                  <div className="text-xs text-gray-500">Sep 22, 2026 · 15:00 JST · 25 Minutes verified</div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full">
                  Memo Available
                </span>
                <span className="text-xs text-gray-400">★★★★★</span>
              </div>
            </div>

            <div className="p-5 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-brand-50 text-brand-900 flex items-center justify-center font-bold">
                  <Calendar className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-bold text-sm text-gray-900">Completed Lesson with David Smith</h4>
                  <div className="text-xs text-gray-500">Sep 18, 2026 · 18:00 JST · 25 Minutes verified</div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full">
                  Memo Available
                </span>
                <span className="text-xs text-gray-400">★★★★★</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
