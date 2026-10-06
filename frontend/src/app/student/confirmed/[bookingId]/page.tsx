"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  CheckCircle2,
  Calendar,
  Clock,
  Video,
  Download,
  ExternalLink,
  ArrowRight,
  ShieldCheck,
  LayoutDashboard,
} from "lucide-react";
import { api } from "@/lib/api";
import { BookingDetail } from "@/types/booking";
import { Avatar } from "@/components/ui/Avatar";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";
import { PENDING_NOTICE } from "@/lib/paypalOutcome";

export default function BookingConfirmedPage() {
  const params = useParams();
  const bookingId = params?.bookingId as string;
  // ?payment=pending is only a hint to show the notice; the booking status itself always comes from the server.
  const paymentPending = useSearchParams()?.get("payment") === "pending";
  const { data: booking, error, loading, reload } = useApiData<BookingDetail>(() => api.getBooking(bookingId), [bookingId]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center text-sm text-ink-muted">
        Loading confirmation details...
      </div>
    );
  }

  if (error || !booking) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16">
        <ErrorState error={error ?? "We could not find this booking."} title="We could not load your booking" onRetry={reload} />
      </div>
    );
  }

  // Never claim a lesson is confirmed unless the server says so.
  if (booking.status !== "confirmed" && booking.status !== "in_progress" && booking.status !== "completed") {
    return (
      <div className="max-w-xl mx-auto px-4 py-16 text-center space-y-4">
        <h1 className="text-xl font-extrabold text-ink font-serif">This lesson is not confirmed</h1>
        <p className="text-sm text-ink-muted">
          Booking {booking.booking_reference} is currently &quot;{booking.status.replace(/_/g, " ")}&quot;. If you were
          trying to pay, the payment has not been confirmed.
        </p>
        <Link
          href={booking.status === "pending_payment" ? `/student/checkout/${booking.id}` : "/student/dashboard"}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-cocoa text-white rounded-xl text-sm font-bold"
        >
          {booking.status === "pending_payment" ? "Back to checkout" : "Return to dashboard"} <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    );
  }

  // Google Calendar URL generator
  const startTime = booking.start_time_utc.replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const endTime = booking.end_time_utc.replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const gcalTitle = encodeURIComponent(`Sharon Online: 25-Min Lesson with ${booking.teacher.full_name}`);
  const gcalDetails = encodeURIComponent(`1-on-1 English Lesson. Zoom Room: ${booking.zoom_url || "Link in dashboard"}`);
  const gcalUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${gcalTitle}&dates=${startTime}/${endTime}&details=${gcalDetails}`;

  // ICS file generator trigger
  const handleDownloadIcs = () => {
    const icsData = [
      "BEGIN:VCALENDAR",
      "VERSION:2.0",
      "PRODID:-//Sharon Online//ESL Platform//EN",
      "BEGIN:VEVENT",
      `SUMMARY:English Lesson with ${booking.teacher.full_name}`,
      `DESCRIPTION:Join Zoom Classroom: ${booking.zoom_url || "link available in your student dashboard"}`,
      `DTSTART:${startTime}`,
      `DTEND:${endTime}`,
      `LOCATION:Online Zoom Room`,
      "STATUS:CONFIRMED",
      "END:VEVENT",
      "END:VCALENDAR",
    ].join("\r\n");

    const blob = new Blob([icsData], { type: "text/calendar;charset=utf-8" });
    const link = document.createElement("a");
    link.href = window.URL.createObjectURL(blob);
    link.setAttribute("download", `lesson_${booking.booking_reference}.ics`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-8">
      {/* Celebration Header */}
      <div className="bg-white rounded-3xl p-8 border border-divider shadow-card text-center space-y-4">
        <div className="w-16 h-16 rounded-full bg-success/15 text-success flex items-center justify-center mx-auto">
          <CheckCircle2 className="w-8 h-8" />
        </div>

        <div className="space-y-1">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-cream-surface border border-cream-deep text-sm font-bold text-cocoa">
            <span>Booking Reference: </span>
            <strong className="text-ink">{booking.booking_reference}</strong>
          </div>
          <h1 className="text-3xl font-extrabold text-ink font-serif pt-1">
            Lesson Confirmed!
          </h1>
          <p className="text-sm text-ink-muted max-w-md mx-auto">
            Your private 25-minute synchronous English lesson has been locked into the schedule.
          </p>
        </div>
      </div>

      {paymentPending && (
        <div role="status"className="p-4 rounded-2xl bg-warning-surface border border-warning-border text-sm text-warning-hover">
          {PENDING_NOTICE}
        </div>
      )}

      {/* Lesson Details Card */}
      <div className="bg-white rounded-3xl p-8 border border-divider shadow-card space-y-6">
        <div className="flex items-center gap-4 border-b border-divider pb-6">
          <Avatar src={booking.teacher.avatar_url} name={booking.teacher.full_name} size="lg" />
          <div>
            <div className="text-base font-bold text-ink">{booking.teacher.full_name}</div>
            <div className="text-sm text-ink-muted">{booking.teacher.accent}</div>
            <div className="text-sm text-cocoa font-semibold mt-0.5">Verified Native Educator</div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div className="p-4 rounded-2xl bg-cream-surface border border-cream-deep space-y-1">
            <span className="text-ink-muted flex items-center gap-1.5 font-medium">
              <Calendar className="w-4 h-4 text-cocoa" /> Date
            </span>
            <div className="text-sm font-bold text-ink">{booking.local_date}</div>
          </div>

          <div className="p-4 rounded-2xl bg-cream-surface border border-cream-deep space-y-1">
            <span className="text-ink-muted flex items-center gap-1.5 font-medium">
              <Clock className="w-4 h-4 text-cocoa" /> Time (Your Local Clock)
            </span>
            <div className="text-sm font-bold text-ink">
              {booking.local_start_time} - {booking.local_end_time} ({booking.viewer_timezone})
            </div>
          </div>
        </div>

        {/* 1-Click Zoom Link Preview */}
        <div className="p-5 rounded-2xl bg-cocoa text-white flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center">
              <Video className="w-5 h-5 text-gold-bright" />
            </div>
            <div>
              <div className="text-sm font-bold text-sun-soft">Your classroom</div>
              <div className="text-sm text-white/80">Room will open 5 minutes prior to class</div>
            </div>
          </div>

          <Link
            href={`/student/classroom/${booking.id}`}
            className="w-full sm:w-auto px-5 py-2.5 bg-accent hover:bg-accent-500 text-ink rounded-xl text-sm font-extrabold transition-all shadow-sm text-center"
          >
            Open Live Classroom Pad
          </Link>
        </div>

        {/* Calendar Sync Actions */}
        <div className="space-y-2 pt-2">
          <label className="text-sm font-bold text-ink-muted uppercase tracking-wider">
            Add to Personal Calendar
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <a
              href={gcalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="py-3 px-4 rounded-xl border border-divider hover:bg-cream-surface text-sm font-bold text-ink flex items-center justify-center gap-2 transition-all"
            >
              <ExternalLink className="w-3.5 h-3.5 text-cocoa" /> Add to Google Calendar
            </a>

            <button
              onClick={handleDownloadIcs}
              className="py-3 px-4 rounded-xl border border-divider hover:bg-cream-surface text-sm font-bold text-ink flex items-center justify-center gap-2 transition-all"
            >
              <Download className="w-3.5 h-3.5 text-primary" /> Download .ICS (Apple / Outlook)
            </button>
          </div>
        </div>

        {/* Policy Badges */}
        <div className="p-4 rounded-2xl bg-cream-surface/60 border border-divider text-sm text-ink-muted space-y-1.5">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-3.5 h-3.5 text-success" />
            <span>Free cancellation or rescheduling up to <strong>2 hours prior</strong> to start time.</span>
          </div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-3.5 h-3.5 text-success" />
            <span>Your teacher will submit a structured <strong>Lesson Memo & Vocab Cards</strong> within 24 hours.</span>
          </div>
        </div>

        {/* Return to Dashboard */}
        <div className="pt-2 text-center">
          <Link
            href="/student/dashboard"
            className="inline-flex items-center gap-2 text-sm font-bold text-cocoa hover:underline"
          >
            <LayoutDashboard className="w-3.5 h-3.5" /> Return to Student Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
