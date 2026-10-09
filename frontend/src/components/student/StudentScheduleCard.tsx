"use client";

import React from "react";
import Link from "next/link";
import {
  CalendarPlus,
  CheckCircle2,
  Clock,
  Video,
  CreditCard,
  AlertTriangle,
  XCircle,
  HelpCircle,
  ShieldAlert,
} from "lucide-react";
import type { StudentLessonItem } from "@/types/student";

export interface StudentScheduleCardProps {
  lesson: StudentLessonItem;
  now: number | null;
}

export function calendarUrl(lesson: StudentLessonItem): string {
  const start = new Date(lesson.start_time_utc).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const end = new Date(lesson.end_time_utc).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(
    `Sharon Online lesson with ${lesson.teacher.name}`
  )}&dates=${start}/${end}&details=${encodeURIComponent(lesson.zoom_url || "Join from Sharon Online")}`;
}

export function canEnterClassroom(lesson: StudentLessonItem, nowMs: number | null): boolean {
  if (nowMs === null) return false;
  const start = new Date(lesson.start_time_utc).getTime();
  return (
    (lesson.status === "confirmed" || lesson.status === "in_progress") &&
    nowMs >= start - 15 * 60_000 &&
    nowMs <= start + 30 * 60_000
  );
}

export function formatStatusLabel(status: string): string {
  switch (status) {
    case "completed":
    case "completed_pending_memo":
    case "completed_memo_forfeited":
      return "Completed";
    case "confirmed":
      return "Scheduled";
    case "in_progress":
      return "In Progress";
    case "pending_payment":
      return "Awaiting Payment";
    case "cancelled_by_student":
      return "Cancelled by Student";
    case "cancelled_by_teacher":
      return "Cancelled by Tutor";
    case "cancelled":
      return "Cancelled";
    case "student_late_cancelled":
      return "Late Cancelled";
    case "interrupted_power":
      return "Grid Interrupted";
    case "disputed":
      return "Disputed / In Review";
    case "student_no_show":
      return "Student No-Show";
    case "teacher_no_show":
      return "Tutor No-Show";
    default:
      return status.replace(/_/g, " ");
  }
}

export function StudentScheduleCard({ lesson, now }: StudentScheduleCardProps) {
  const endMs = Date.parse(lesson.end_time_utc);
  const isPast = now !== null && !Number.isNaN(endMs) && endMs < now;
  const isPending = lesson.status === "pending_payment";
  const isConfirmed = lesson.status === "confirmed" || lesson.status === "in_progress";
  const isCompleted =
    lesson.status === "completed" ||
    lesson.status === "completed_pending_memo" ||
    lesson.status === "completed_memo_forfeited";
  const isCancelled =
    lesson.status.startsWith("cancelled") || lesson.status === "student_late_cancelled";
  const isDisputed = lesson.status === "disputed";
  const isInterrupted = lesson.status === "interrupted_power";
  const isNoShow = lesson.status === "student_no_show" || lesson.status === "teacher_no_show";

  const allowClassroom = canEnterClassroom(lesson, now);

  return (
    <article className="rounded-3xl border border-divider bg-white p-6 shadow-card hover:shadow-card-hover transition-all">
      <div className="flex flex-col justify-between gap-5 sm:flex-row">
        <div className="min-w-0 space-y-2">
          {/* Timing details */}
          <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm font-bold text-cocoa">
            <span>{lesson.local_date}</span>
            <span>·</span>
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" /> {lesson.local_start_time}–{lesson.local_end_time}
            </span>
            <span className="max-w-full break-all rounded-full bg-cocoa/10 px-2 py-0.5 text-xs text-cocoa">
              {lesson.viewer_timezone}
            </span>
          </div>

          {/* Teacher and Subject */}
          <h2 className="font-serif text-2xl font-black text-ink">{lesson.teacher.name}</h2>
          <p className="text-sm text-ink-muted">
            {lesson.material_title || "English lesson"}
            {lesson.material_cefr ? ` · CEFR ${lesson.material_cefr}` : ""}
          </p>

          {/* Status Pills */}
          <div className="pt-1 flex flex-wrap items-center gap-2">
            {isCompleted && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-success-surface px-3 py-1 text-xs font-bold text-success-hover border border-success-border">
                <CheckCircle2 className="h-3.5 w-3.5 text-success" /> Completed
              </span>
            )}
            {isPending && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-warning-surface px-3 py-1 text-xs font-bold text-warning-hover border border-warning-border">
                <AlertTriangle className="h-3.5 w-3.5 text-warning" />
                {isPast ? "Payment Expired" : "Awaiting Payment"}
              </span>
            )}
            {isConfirmed && !isPast && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-cocoa/10 px-3 py-1 text-xs font-bold text-cocoa border border-cocoa/20">
                <Clock className="h-3.5 w-3.5 text-cocoa" /> {formatStatusLabel(lesson.status)}
              </span>
            )}
            {isCancelled && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-cream-deep px-3 py-1 text-xs font-bold text-ink-muted border border-divider">
                <XCircle className="h-3.5 w-3.5" /> {formatStatusLabel(lesson.status)}
              </span>
            )}
            {isInterrupted && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-warning-surface px-3 py-1 text-xs font-bold text-warning-hover border border-warning-border">
                <AlertTriangle className="h-3.5 w-3.5 text-warning" /> Grid Interrupted
              </span>
            )}
            {isDisputed && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-warning-surface px-3 py-1 text-xs font-bold text-warning-hover border border-warning-border">
                <ShieldAlert className="h-3.5 w-3.5 text-warning" /> Disputed / In Review
              </span>
            )}
            {isNoShow && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-error-surface px-3 py-1 text-xs font-bold text-error border border-error-border">
                <HelpCircle className="h-3.5 w-3.5 text-error" /> {formatStatusLabel(lesson.status)}
              </span>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
          {/* Pending Payment -> Checkout link */}
          {isPending && !isPast && (
            <Link
              href={`/student/checkout/${lesson.id}`}
              className="min-h-11 inline-flex items-center gap-2 rounded-xl bg-cocoa px-4 py-2.5 text-sm font-bold text-white hover:bg-cocoa-hover transition-colors shadow-xs"
            >
              <CreditCard className="h-4 w-4" /> Complete Checkout
            </Link>
          )}

          {/* Confirmed & Live Classroom Entry */}
          {isConfirmed && !isPast && allowClassroom && (
            <Link
              href={`/student/classroom/${lesson.id}`}
              className="min-h-11 inline-flex items-center gap-2 rounded-xl bg-cocoa px-4 py-2.5 text-sm font-bold text-white hover:bg-cocoa-hover transition-colors shadow-xs"
            >
              <Video className="h-4 w-4" /> Enter classroom
            </Link>
          )}

          {/* Confirmed & Upcoming -> Google Calendar Sync */}
          {isConfirmed && !isPast && (
            <a
              href={calendarUrl(lesson)}
              target="_blank"
              rel="noreferrer"
              className="min-h-11 inline-flex items-center gap-2 rounded-xl border border-divider px-4 py-2.5 text-sm font-bold text-ink hover:bg-cream-surface transition-colors"
            >
              <CalendarPlus className="h-4 w-4 text-cocoa" /> Add to Google Calendar
            </a>
          )}
        </div>
      </div>
    </article>
  );
}
