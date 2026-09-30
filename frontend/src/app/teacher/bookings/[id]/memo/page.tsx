"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, BookOpen, Clock, User, Calendar } from "lucide-react";
import { api } from "@/lib/api";
import { BookingDetail } from "@/types/booking";
import { MemoComposer } from "@/components/teacher/MemoComposer";

export default function TeacherMemoPage() {
  const params = useParams();
  const bookingId = (params?.id as string) || "BK-DEMO";

  const [booking, setBooking] = useState<BookingDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadBooking() {
      setLoading(true);
      try {
        const b = await api.getBooking(bookingId);
        setBooking(b);
      } catch (e) {
        console.error("Failed to load booking for memo:", e);
      } finally {
        setLoading(false);
      }
    }
    loadBooking();
  }, [bookingId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center py-20">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-teal border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-bold text-ink-muted">Loading session details...</p>
        </div>
      </div>
    );
  }

  if (!booking) {
    return (
      <div className="min-h-screen bg-cream py-20">
        <div className="max-w-xl mx-auto px-4 text-center space-y-6">
          <h2 className="text-2xl font-black text-ink font-serif">Lesson Not Found</h2>
          <p className="text-xs text-ink-muted">The requested booking ID does not exist.</p>
          <Link
            href="/teacher/dashboard"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-teal text-white text-xs font-bold"
          >
            <ArrowLeft className="w-4 h-4" /> Return to Teacher Dashboard
          </Link>
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

          <span className="text-xs font-mono font-bold text-teal bg-teal/10 px-3 py-1 rounded-full">
            REF: {booking.booking_reference}
          </span>
        </div>

        {/* Lesson Metadata Summary Card */}
        <div className="bg-white rounded-3xl p-6 border border-divider shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-2xl bg-cream-surface border border-divider flex items-center justify-center font-bold text-teal text-base">
              {booking.student.full_name[0]}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-black text-ink">{booking.student.full_name}</span>
                <span className="text-[10px] font-bold text-teal bg-teal/10 px-2 py-0.5 rounded-full">
                  Target: {booking.student.target_level || "B2 Upper-Int"}
                </span>
              </div>
              <p className="text-xs text-ink-muted">
                {booking.local_date} · {booking.local_start_time} - {booking.local_end_time} ({booking.viewer_timezone})
              </p>
            </div>
          </div>

          <div className="text-xs text-ink-muted bg-cream-surface px-4 py-2.5 rounded-2xl border border-divider">
            <span className="font-bold text-ink block">Material Covered:</span>
            <span className="font-medium text-teal">{booking.material_title || "General Conversational Practice"}</span>
          </div>
        </div>

        {/* Memo Composer Component */}
        <MemoComposer
          bookingId={booking.id}
          studentName={booking.student.full_name}
          lessonTitle={booking.material_title || "General Conversational Practice"}
        />
      </div>
    </div>
  );
}
