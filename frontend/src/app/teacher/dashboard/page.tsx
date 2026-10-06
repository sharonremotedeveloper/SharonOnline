"use client";

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
  Star,
  Award,
} from "lucide-react";
import { api } from "@/lib/api";
import { listBookings } from "@/lib/bookings";
import { BookingDetail } from "@/types/booking";
import { EskomStageBanner } from "@/components/teacher/EskomStageBanner";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";
import { useAuth } from "@/context/AuthContext";
import { viewerPeriodBounds } from "@/lib/dashboardTime";

/** The server filters and counts, so nothing here depends on how many lessons the tutor has had. */
async function loadTeacherBookings(timezone: string): Promise<{
  upcoming: BookingDetail[];
  pendingMemos: BookingDetail[];
  pendingMemoCount: number;
  todayLessons: BookingDetail[];
  todayCount: number;
  completedThisMonth: number;
}> {
  const { dayStart, dayEnd, monthStart } = viewerPeriodBounds(timezone);
  const [upcoming, memos, today, completed] = await Promise.all([
    listBookings({ when: "upcoming", status: ["confirmed", "in_progress"], pageSize: 1 }),
    listBookings({ status: ["completed_pending_memo"], pageSize: 1 }),
    listBookings({ status: ["confirmed", "in_progress"], from: dayStart, to: dayEnd, ordering: "start_time_utc", pageSize: 50 }),
    listBookings({ status: ["completed", "completed_pending_memo"], from: monthStart, pageSize: 1 }),
  ]);
  return {
    upcoming: upcoming.items,
    pendingMemos: memos.items,
    pendingMemoCount: memos.count,
    todayLessons: today.items,
    todayCount: today.count,
    completedThisMonth: completed.count,
  };
}

export default function TeacherDashboardPage() {
  const { user } = useAuth();
  const viewerTimezone = user?.timezone || "UTC";
  // Each data source loads independently so one failing source never blanks the others.
  const eskom = useApiData(() => api.getEskomStatus(), []);
  const walletQ = useApiData(() => api.getTeacherWallet(), []);
  const bookingsQ = useApiData(() => loadTeacherBookings(viewerTimezone), [viewerTimezone]);
  const eskomStatus = eskom.data;
  const wallet = walletQ.data;

  const upcoming = bookingsQ.data?.upcoming ?? [];
  const pendingMemos = bookingsQ.data?.pendingMemos ?? [];
  const pendingMemoCount = bookingsQ.data?.pendingMemoCount ?? 0;
  const completedThisMonth = bookingsQ.data?.completedThisMonth ?? 0;
  const upcomingLesson = upcoming[0] ?? null;
  const todayLessons = bookingsQ.data?.todayLessons ?? [];
  const todayCount = bookingsQ.data?.todayCount ?? 0;

  const pendingMemo = pendingMemos[0] ?? null;
  const fmtWhen = (b: BookingDetail) =>
    `${b.local_date} · ${b.local_start_time} - ${b.local_end_time} (${b.viewer_timezone})`;

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-sun-soft text-ink text-sm font-bold border border-sun">
              <Award className="w-3.5 h-3.5 text-gold-bright" />
              <span>Tutor workspace</span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-black text-ink font-serif tracking-tight">
              Your tutor dashboard
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
              <Calendar className="w-3.5 h-3.5 text-cocoa" />
              <span>Availability</span>
            </Link>

            <Link
              href="/teacher/power-guard"
              className="px-4 py-2.5 bg-white hover:bg-cream-surface text-ink text-xs font-bold rounded-xl border border-divider shadow-xs flex items-center gap-1.5 transition-colors"
            >
              <Zap className="w-3.5 h-3.5 text-warning fill-warning" />
              <span>Power Guard</span>
            </Link>

            <Link
              href="/teacher/wallet"
              className="px-4 py-2.5 bg-cocoa hover:bg-cocoa-hover text-white text-xs font-black rounded-xl shadow-sm flex items-center gap-1.5 transition-colors"
            >
              <DollarSign className="w-3.5 h-3.5" />
              <span>{wallet ? `Wallet: R${wallet.cleared_balance_zar.toFixed(0)} ZAR` : "Wallet"}</span>
            </Link>
          </div>
        </div>

        {/* Eskom Stage Banner */}
        {eskom.loading ? (
          <div className="h-16 rounded-2xl bg-white border border-divider animate-pulse" />
        ) : eskom.error ? (
          <ErrorState error={eskom.error} title="Eskom Power Guard status isn't available" onRetry={eskom.reload} />
        ) : (
          eskomStatus && <EskomStageBanner status={eskomStatus} />
        )}

        {bookingsQ.error != null && (
          <ErrorState error={bookingsQ.error} title="We couldn't load your lessons" onRetry={bookingsQ.reload} />
        )}

        {/* Pending Memo Action Alert */}
        {pendingMemo && (
          <div className="p-5 rounded-2xl bg-plum/10 border border-plum/20 text-ink flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-plum text-white flex items-center justify-center font-bold shrink-0">
                <Send className="w-5 h-5" />
              </div>
              <div className="space-y-0.5">
                <div className="text-xs font-bold text-plum">
                  {pendingMemoCount} Pending Post-Lesson Memo{pendingMemoCount === 1 ? "" : "s"}
                </div>
                <div className="text-sm font-black text-ink">
                  {pendingMemo.student.full_name} — {pendingMemo.material_title || "Lesson"}
                </div>
                <div className="text-xs text-ink-muted">Lesson on {fmtWhen(pendingMemo)}</div>
              </div>
            </div>

            <Link
              href={`/teacher/bookings/${pendingMemo.id}/memo`}
              className="px-5 py-2.5 bg-plum hover:bg-cocoa-hover text-white text-xs font-black rounded-xl shadow-xs flex items-center justify-center gap-1.5 transition-all shrink-0"
            >
              <span>Compose Memo</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        )}

        {/* Next Class Hero Card */}
        {bookingsQ.loading ? (
          <div className="h-48 rounded-3xl bg-white border border-divider animate-pulse" />
        ) : bookingsQ.error ? null : !upcomingLesson ? (
          <div className="bg-white rounded-3xl p-8 border border-divider shadow-card text-center space-y-1">
            <h3 className="text-lg font-black text-ink font-serif">No upcoming lessons</h3>
            <p className="text-xs text-ink-muted">Confirmed bookings will appear here once students book your slots.</p>
          </div>
        ) : (
          <div className="bg-cocoa text-white rounded-3xl p-6 sm:p-10 shadow-card space-y-6 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-2 text-xs font-extrabold bg-white/10 border border-white/20 px-3.5 py-1 rounded-full text-sun-soft">
                <span className="w-2.5 h-2.5 rounded-full bg-sun animate-pulse"></span>
                Next Class to Host
              </span>
              <span className="text-xs text-white/80 font-medium">Staging opens 5m before start</span>
            </div>

            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
              <div className="space-y-3">
                <div className="text-2xl sm:text-3xl font-black font-serif">{upcomingLesson.student.full_name}</div>

                <div className="flex flex-wrap items-center gap-3 pt-1">
                  {upcomingLesson.material_title && (
                    <span className="text-xs bg-accent text-ink px-3 py-1 rounded-lg font-bold flex items-center gap-1.5">
                      <BookOpen className="w-3.5 h-3.5" />
                      {upcomingLesson.material_title}
                    </span>
                  )}

                  <span className="text-xs text-white/90 flex items-center gap-1.5 font-medium">
                    <Clock className="w-3.5 h-3.5 text-gold-bright" />
                    {fmtWhen(upcomingLesson)}
                  </span>
                </div>

                {upcomingLesson.student.learning_goals && (
                  <p className="text-xs text-cream/70 italic border-l-2 border-accent pl-3">
                    Focus: &ldquo;{upcomingLesson.student.learning_goals}&rdquo;
                  </p>
                )}
              </div>

              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 shrink-0">
                <Link
                  href={`/teacher/classroom/${upcomingLesson.id}`}
                  className="px-6 py-4 bg-accent hover:bg-warning text-ink font-black rounded-2xl text-xs sm:text-sm transition-all shadow-lg flex items-center justify-center gap-2 hover:scale-[1.01]"
                >
                  <Video className="w-4 h-4" />
                  <span>Enter Classroom Staging Pad</span>
                  <ArrowRight className="w-4 h-4 ml-1" />
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* Metric Highlights */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
            <div className="text-xs font-bold text-ink-muted">Tutor Rating</div>
            <div className="text-2xl font-black text-ink flex items-center gap-1.5 font-serif">
              <Star className="w-5 h-5 text-gold-bright fill-gold-bright" />
              <span>&mdash;</span>
            </div>
            <p className="text-xs text-ink-muted">Rating summary isn&apos;t available yet.</p>
          </div>

          <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
            <div className="text-xs font-bold text-ink-muted">Completed Lessons This Month</div>
            <div className="text-2xl font-black text-cocoa font-serif">
              {bookingsQ.data ? `${completedThisMonth} ${completedThisMonth === 1 ? "Class" : "Classes"}` : "—"}
            </div>
            <p className="text-xs text-ink-muted">
              {bookingsQ.error != null ? "Couldn't load your lessons." : "Based on your bookings."}
            </p>
          </div>

          <div className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-1">
            <div className="text-xs font-bold text-ink-muted">Cleared Balance</div>
            {walletQ.loading ? (
              <div className="h-8 rounded bg-cream-surface animate-pulse" />
            ) : wallet ? (
              <>
                <div className="text-2xl font-black text-success-hover font-serif">
                  R{wallet.cleared_balance_zar.toFixed(2)} ZAR
                </div>
                <p className="text-xs text-ink-muted">Ledger-cleared and awaiting an approved payout workflow.</p>
              </>
            ) : (
              <>
                <div className="text-2xl font-black text-ink-muted font-serif">&mdash;</div>
                <p className="text-xs text-error">
                  Wallet isn&apos;t available yet.{" "}
                  <button type="button" onClick={walletQ.reload} className="underline font-bold">
                    Retry
                  </button>
                </p>
              </>
            )}
          </div>
        </div>

        {/* Today's Full Roster */}
        <div className="bg-white rounded-3xl border border-divider shadow-card p-6 sm:p-8 space-y-6">
          <div className="flex items-center justify-between border-b border-divider pb-4">
            <div>
              <h3 className="text-lg font-black text-ink font-serif">Today&apos;s Class Schedule</h3>
              <p className="text-xs text-ink-muted">All sessions synchronized across timezones</p>
            </div>
            {bookingsQ.data && (
              <span className="text-xs font-bold text-cocoa bg-cocoa/10 px-3 py-1 rounded-full">
                {todayCount} Scheduled {todayCount === 1 ? "Lesson" : "Lessons"}
              </span>
            )}
          </div>

          {bookingsQ.loading ? (
            <div className="h-16 rounded-2xl bg-cream-surface animate-pulse" />
          ) : bookingsQ.error != null ? (
            <p className="text-xs text-error">Today&apos;s schedule couldn&apos;t be loaded.</p>
          ) : todayLessons.length === 0 ? (
            <p className="text-xs text-ink-muted text-center py-4">No lessons scheduled for today.</p>
          ) : (
            <div className="divide-y divide-divider">
              {todayLessons.map((b, i) => (
                <div key={b.id} className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-3.5">
                    <div className="w-10 h-10 rounded-2xl bg-cocoa/10 text-cocoa font-black flex items-center justify-center text-xs">
                      {b.student.full_name
                        .split(" ")
                        .map((w) => w[0])
                        .join("")
                        .slice(0, 2)
                        .toUpperCase()}
                    </div>
                    <div>
                      <h4 className="font-extrabold text-sm text-ink">{b.student.full_name}</h4>
                      <div className="text-xs text-ink-muted">
                        {b.local_start_time} - {b.local_end_time} ({b.viewer_timezone}) · 25-Min Lesson
                        {b.material_title ? ` · ${b.material_title}` : ""}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-start sm:self-auto">
                    <Link
                      href={`/teacher/classroom/${b.id}`}
                      className={
                        i === 0
                          ? "px-3.5 py-1.5 bg-cocoa hover:bg-cocoa-hover text-white text-xs font-bold rounded-xl transition-colors"
                          : "px-3.5 py-1.5 bg-cream-surface hover:bg-cream-deep text-ink text-xs font-bold rounded-xl border border-divider transition-colors"
                      }
                    >
                      {i === 0 ? "Host Pad" : "Preview"}
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
