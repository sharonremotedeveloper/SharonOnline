"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Calendar,
  Clock,
  Video,
  BookOpen,
  DollarSign,
  ArrowRight,
  Send,
  Zap,
  ShieldCheck,
  Star,
  Users,
  Award,
} from "lucide-react";
import { api } from "@/lib/api";
import { EskomStatus, TeacherWalletData } from "@/types/teacher";
import { EskomStageBanner } from "@/components/teacher/EskomStageBanner";

export default function TeacherDashboardPage() {
  const [eskomStatus, setEskomStatus] = useState<EskomStatus | null>(null);
  const [wallet, setWallet] = useState<TeacherWalletData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [eskom, w] = await Promise.all([api.getEskomStatus(), api.getTeacherWallet()]);
        setEskomStatus(eskom);
        setWallet(w);
      } catch (e) {
        console.error("Failed to load tutor dashboard:", e);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const upcomingLesson = {
    bookingId: "BK-884192",
    studentName: "Aiko Tanaka",
    studentCountry: "🇯🇵 Japan (Tokyo)",
    scheduledTime: "Today · 15:00 - 15:25 SAST (22:00 JST)",
    material: "Global Remote Work & Digital Nomads",
    materialCefr: "B2",
    targetFocus: "Conversational fluency & STAR interview phrasing",
  };

  const pendingMemo = {
    bookingId: "BK-884185",
    studentName: "Marco Rossi",
    lessonTitle: "Mastering Cross-Cultural Negotiations",
    completedTime: "Today · 14:00 SAST",
  };

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/20 text-accent-surface text-xs font-bold border border-accent/30">
              <Award className="w-3.5 h-3.5 text-accent" />
              <span>Verified Educator Operations Portal</span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-black text-ink font-serif tracking-tight">
              Tutor Operations Cockpit
            </h1>
            <p className="text-xs sm:text-sm text-ink-muted">
              Manage your upcoming synchronous classes, submit lesson memos, and monitor Eskom Power Guard.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <Link
              href="/teacher/schedule"
              className="px-4 py-2.5 bg-white hover:bg-cream-surface text-ink text-xs font-bold rounded-xl border border-divider shadow-xs flex items-center gap-1.5 transition-colors"
            >
              <Calendar className="w-3.5 h-3.5 text-teal" />
              <span>Availability</span>
            </Link>

            <Link
              href="/teacher/power-guard"
              className="px-4 py-2.5 bg-white hover:bg-cream-surface text-ink text-xs font-bold rounded-xl border border-divider shadow-xs flex items-center gap-1.5 transition-colors"
            >
              <Zap className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
              <span>Power Guard</span>
            </Link>

            <Link
              href="/teacher/wallet"
              className="px-4 py-2.5 bg-teal hover:bg-teal-hover text-white text-xs font-black rounded-xl shadow-sm flex items-center gap-1.5 transition-colors"
            >
              <DollarSign className="w-3.5 h-3.5" />
              <span>Wallet: R{wallet ? wallet.cleared_balance_zar.toFixed(0) : "2,400"} ZAR</span>
            </Link>
          </div>
        </div>

        {/* Eskom Stage Banner */}
        {eskomStatus && <EskomStageBanner status={eskomStatus} />}

        {/* Pending Memo Action Alert */}
        {pendingMemo && (
          <div className="p-5 rounded-2xl bg-plum/10 border border-plum/20 text-ink flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-plum text-white flex items-center justify-center font-bold shrink-0">
                <Send className="w-5 h-5" />
              </div>
              <div className="space-y-0.5">
                <div className="text-xs font-bold text-plum">1 Pending Post-Lesson Memo</div>
                <div className="text-sm font-black text-ink">
                  {pendingMemo.studentName} — {pendingMemo.lessonTitle}
                </div>
                <div className="text-[11px] text-ink-muted">Completed {pendingMemo.completedTime}</div>
              </div>
            </div>

            <Link
              href={`/teacher/bookings/${pendingMemo.bookingId}/memo`}
              className="px-5 py-2.5 bg-plum hover:bg-purple-900 text-white text-xs font-black rounded-xl shadow-xs flex items-center justify-center gap-1.5 transition-all shrink-0"
            >
              <span>Compose Memo</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        )}

        {/* Next Class Hero Card */}
        <div className="bg-gradient-to-br from-[#0B3530] via-teal to-[#082622] text-white rounded-3xl p-6 sm:p-10 shadow-card space-y-6 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-2 text-xs font-extrabold bg-white/10 border border-white/20 px-3.5 py-1 rounded-full text-accent-surface">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Next Class to Host
            </span>
            <span className="text-xs text-white/80 font-medium">Staging opens 5m before start</span>
          </div>

          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-3">
              <div className="text-2xl sm:text-3xl font-black font-serif">{upcomingLesson.studentName}</div>
              <div className="text-xs text-white/80 font-medium">{upcomingLesson.studentCountry}</div>

              <div className="flex flex-wrap items-center gap-3 pt-1">
                <span className="text-xs bg-accent text-ink px-3 py-1 rounded-lg font-bold flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5" />
                  [{upcomingLesson.materialCefr}] {upcomingLesson.material}
                </span>

                <span className="text-xs text-white/90 flex items-center gap-1.5 font-medium">
                  <Clock className="w-3.5 h-3.5 text-accent" />
                  {upcomingLesson.scheduledTime}
                </span>
              </div>

              <p className="text-xs text-cream/70 italic border-l-2 border-accent pl-3">
                Focus: &ldquo;{upcomingLesson.targetFocus}&rdquo;
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 shrink-0">
              <Link
                href={`/teacher/classroom/${upcomingLesson.bookingId}`}
                className="px-6 py-4 bg-accent hover:bg-amber-600 text-ink font-black rounded-2xl text-xs sm:text-sm transition-all shadow-lg flex items-center justify-center gap-2 hover:scale-[1.01]"
              >
                <Video className="w-4 h-4" />
                <span>Enter Classroom Staging Pad</span>
                <ArrowRight className="w-4 h-4 ml-1" />
              </Link>
            </div>
          </div>
        </div>

        {/* 3 Metric Stat Highlights */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
            <div className="text-xs font-bold text-ink-muted">Tutor Rating</div>
            <div className="text-2xl font-black text-ink flex items-center gap-1.5 font-serif">
              <Star className="w-5 h-5 text-accent fill-accent" />
              <span>4.98</span>
              <span className="text-xs font-normal text-ink-muted">(142 reviews)</span>
            </div>
            <p className="text-[11px] text-ink-muted">Top 1% rated native educator</p>
          </div>

          <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
            <div className="text-xs font-bold text-ink-muted">Completed Lessons This Month</div>
            <div className="text-2xl font-black text-teal font-serif">28 Classes</div>
            <p className="text-[11px] text-ink-muted">100% on-time attendance score</p>
          </div>

          <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
            <div className="text-xs font-bold text-ink-muted">Upcoming Payout</div>
            <div className="text-2xl font-black text-emerald-800 font-serif">R2,400.00 ZAR</div>
            <p className="text-[11px] text-ink-muted">Scheduled for batch EFT on the 1st</p>
          </div>
        </div>

        {/* Today's Full Roster */}
        <div className="bg-white rounded-3xl border border-divider shadow-card p-6 sm:p-8 space-y-6">
          <div className="flex items-center justify-between border-b border-divider pb-4">
            <div>
              <h3 className="text-lg font-black text-ink font-serif">Today&apos;s Class Schedule</h3>
              <p className="text-xs text-ink-muted">All sessions synchronized across timezones</p>
            </div>
            <span className="text-xs font-bold text-teal bg-teal/10 px-3 py-1 rounded-full">
              2 Scheduled Lessons
            </span>
          </div>

          <div className="divide-y divide-divider">
            <div className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3.5">
                <div className="w-10 h-10 rounded-2xl bg-teal/10 text-teal font-black flex items-center justify-center text-xs">
                  AT
                </div>
                <div>
                  <h4 className="font-extrabold text-sm text-ink">Aiko Tanaka (Tokyo)</h4>
                  <div className="text-xs text-ink-muted">15:00 - 15:25 SAST · 25-Min Lesson · B2 Daily News</div>
                </div>
              </div>

              <div className="flex items-center gap-2 self-start sm:self-auto">
                <span className="text-xs font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-xl">
                  Staging Ready
                </span>
                <Link
                  href="/teacher/classroom/BK-884192"
                  className="px-3.5 py-1.5 bg-teal hover:bg-teal-hover text-white text-xs font-bold rounded-xl transition-colors"
                >
                  Host Pad
                </Link>
              </div>
            </div>

            <div className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3.5">
                <div className="w-10 h-10 rounded-2xl bg-cream-surface text-ink font-black flex items-center justify-center text-xs border border-divider">
                  MR
                </div>
                <div>
                  <h4 className="font-extrabold text-sm text-ink">Marco Rossi (Milan)</h4>
                  <div className="text-xs text-ink-muted">16:00 - 16:25 SAST · 25-Min Lesson · C1 Business English</div>
                </div>
              </div>

              <div className="flex items-center gap-2 self-start sm:self-auto">
                <span className="text-xs font-bold text-ink-muted bg-cream-surface px-3 py-1 rounded-xl border border-divider">
                  Upcoming
                </span>
                <Link
                  href="/teacher/classroom/BK-884185"
                  className="px-3.5 py-1.5 bg-cream-surface hover:bg-cream-deep text-ink text-xs font-bold rounded-xl border border-divider transition-colors"
                >
                  Preview
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
