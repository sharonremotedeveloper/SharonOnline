"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, BookOpen, Clock, User, Calendar } from "lucide-react";
import { api } from "@/lib/api";
import { BookingDetail } from "@/types/booking";
import { MemoComposer } from "@/components/teacher/MemoComposer";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";

function readScratch(id: string): string {
  try {
    return sessionStorage.getItem(`scratch:${id}`) || "";
  } catch {
    return "";
  }
}

export default function TeacherMemoPage() {
  const params = useParams();
  const bookingId = params?.id as string;

  const { data: booking, error, loading, reload } = useApiData(() => api.getBooking(bookingId), [bookingId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center py-20">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-cocoa border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-bold text-ink-muted">Loading session details...</p>
        </div>
      </div>
    );
  }

  if (error || !booking) {
    return (
      <div className="min-h-screen bg-cream py-20">
        <div className="max-w-xl mx-auto px-4 space-y-6">
          <ErrorState error={error ?? "Lesson not found."} title="We couldn't load this lesson" onRetry={reload} />
          <div className="text-center">
            <Link
              href="/teacher/dashboard"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-cocoa text-white text-xs font-bold"
            >
              <ArrowLeft className="w-4 h-4" /> Return to Teacher Dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Navigation */}
        <div className="flex items-center justify-between">
          <Link
            href="/teacher/dashboard"
            className="inline-flex items-center gap-2 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Dashboard</span>
          </Link>

          <span className="text-xs font-mono font-bold text-cocoa bg-cocoa/10 px-3 py-1 rounded-full">
            REF: {booking.booking_reference}
          </span>
        </div>

        {/* Lesson Metadata Summary Card */}
        <div className="bg-white rounded-3xl p-6 border border-divider shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-2xl bg-cream-surface border border-divider flex items-center justify-center font-bold text-cocoa text-base">
              {booking.student.full_name[0]}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-black text-ink">{booking.student.full_name}</span>
                {booking.student.target_level && (
                  <span className="text-[10px] font-bold text-cocoa bg-cocoa/10 px-2 py-0.5 rounded-full">
                    Target: {booking.student.target_level}
                  </span>
                )}
              </div>
              <p className="text-xs text-ink-muted">
                {booking.local_date} · {booking.local_start_time} - {booking.local_end_time} ({booking.viewer_timezone})
              </p>
            </div>
          </div>

          <div className="text-xs text-ink-muted bg-cream-surface px-4 py-2.5 rounded-2xl border border-divider">
            <span className="font-bold text-ink block">Material Covered:</span>
            <span className="font-medium text-cocoa">{booking.material_title || "No material linked"}</span>
          </div>
        </div>

        {/* Memo Composer Component */}
        <MemoComposer
          bookingId={booking.id}
          studentName={booking.student.full_name}
          initialScratchpad={readScratch(bookingId)}
          lessonTitle={booking.material_title || "No material linked"}
        />
      </div>
    </div>
  );
}
