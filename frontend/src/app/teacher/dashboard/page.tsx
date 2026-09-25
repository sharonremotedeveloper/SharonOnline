"use client";

import Link from "next/link";
import { Calendar, Clock, Video, BookOpen, User, DollarSign, ArrowRight } from "lucide-react";

export default function TeacherDashboardPage() {
  const upcomingLesson = {
    studentName: "Aiko Tanaka",
    studentCountry: "🇯🇵 Japan (Tokyo)",
    scheduledTime: "Today · 15:00 SAST (22:00 JST)",
    material: "Global Remote Work Trends in 2026",
    materialCefr: "B2",
    hostZoomUrl: "https://zoom.us/s/9876543210?zak=teacher_token",
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-gray-900 tracking-tight">Teacher Operations Hub</h1>
          <p className="text-xs sm:text-sm text-gray-500">
            Welcome, Naledi! Manage your upcoming lessons, host Zoom classes, and submit lesson memos.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-white border border-gray-200 px-4 py-2 rounded-xl text-xs shadow-sm">
            <span className="text-gray-500">Cleared Balance:</span>{" "}
            <strong className="text-emerald-700 text-sm font-black">R1,875.00 ZAR</strong>
          </div>
          <Link
            href="/teacher/schedule"
            className="px-4 py-2 bg-brand-900 hover:bg-brand-950 text-white font-bold text-xs rounded-xl shadow-sm transition-all"
          >
            Edit Schedule
          </Link>
        </div>
      </div>

      {/* Next Class Host Card */}
      <div className="bg-[#0D4440] text-white rounded-2xl p-6 sm:p-8 shadow-xl space-y-6">
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-2 text-xs font-bold bg-white/10 border border-white/20 px-3 py-1 rounded-full text-gold-500">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> Next Class to Host
          </span>
          <span className="text-xs text-white/70">In 2 hours 15 mins</span>
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="text-2xl font-black">{upcomingLesson.studentName}</div>
            <div className="text-xs text-white/80">{upcomingLesson.studentCountry}</div>
            <div className="text-xs text-gold-500 font-semibold flex items-center gap-1.5 mt-2">
              <BookOpen className="w-3.5 h-3.5" />
              Lesson Plan: [{upcomingLesson.materialCefr}] {upcomingLesson.material}
            </div>
            <div className="text-xs text-white/70 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              {upcomingLesson.scheduledTime}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <a
              href={upcomingLesson.hostZoomUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3.5 bg-gold-500 hover:bg-gold-600 text-brand-950 font-black rounded-xl text-sm transition-all shadow-lg flex items-center justify-center gap-2"
            >
              <Video className="w-4 h-4" /> Start Class as Host (Zoom)
            </a>
          </div>
        </div>
      </div>

      {/* Roster & Memo Queue */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-card p-6 space-y-4">
        <h3 className="font-extrabold text-base text-gray-900">Today's Class Roster</h3>
        <div className="divide-y divide-gray-100">
          <div className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-brand-50 text-brand-900 font-bold flex items-center justify-center text-xs">
                AT
              </div>
              <div>
                <h4 className="font-bold text-xs text-gray-900">Aiko Tanaka (Tokyo)</h4>
                <div className="text-[11px] text-gray-500">15:00 - 15:25 SAST · 25-Min Lesson</div>
              </div>
            </div>
            <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full self-start sm:self-auto">
              Ready to Host
            </span>
          </div>

          <div className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-brand-50 text-brand-900 font-bold flex items-center justify-center text-xs">
                MR
              </div>
              <div>
                <h4 className="font-bold text-xs text-gray-900">Marco Rossi (Milan)</h4>
                <div className="text-[11px] text-gray-500">16:00 - 16:25 SAST · 25-Min Lesson</div>
              </div>
            </div>
            <span className="text-xs font-semibold text-gray-500 bg-gray-100 px-3 py-1 rounded-full self-start sm:self-auto">
              Upcoming
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
