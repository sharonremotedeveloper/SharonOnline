"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Video,
  Mic,
  Camera,
  CheckCircle2,
  Clock,
  Sparkles,
  ExternalLink,
  ShieldCheck,
  AlertCircle,
  Headphones,
} from "lucide-react";
import { api } from "@/lib/api";
import { BookingDetail } from "@/types/booking";
import { MaterialDetail } from "@/types/material";
import { HardwareCheckModal } from "@/components/classroom/HardwareCheckModal";
import { ZoomLauncherButton } from "@/components/classroom/ZoomLauncherButton";
import { LessonCountDownClock } from "@/components/classroom/LessonCountDownClock";
import { EskomReportButton } from "@/components/classroom/EskomReportButton";
import { ClassroomSplitLayout } from "@/components/classroom/ClassroomSplitLayout";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

export default function StudentClassroomPage() {
  const params = useParams();
  const bookingId = params?.id as string;

  const [booking, setBooking] = useState<BookingDetail | null>(null);
  const [material, setMaterial] = useState<MaterialDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [materialError, setMaterialError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [hardwareModalOpen, setHardwareModalOpen] = useState(false);
  const [hardwareChecked, setHardwareChecked] = useState(false);

  useEffect(() => {
    if (!bookingId) return;
    let cancelled = false;
    async function loadClassroom() {
      setLoading(true);
      setLoadError(null);
      setMaterialError(null);
      setMaterial(null);
      try {
        const b = await api.getBooking(bookingId);
        if (cancelled) return;
        setBooking(b);

        // Lesson material is optional; a failure here must not hide the classroom, but it is reported honestly.
        if (b.material_slug) {
          try {
            const m = await api.getMaterialBySlug(b.material_slug);
            if (!cancelled) setMaterial(m);
          } catch (mErr) {
            console.error("Failed to load lesson material:", mErr);
            if (!cancelled) setMaterialError(mErr);
          }
        }
      } catch (err) {
        console.error("Failed to load classroom booking:", err);
        if (!cancelled) {
          setBooking(null);
          setLoadError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadClassroom();
    return () => {
      cancelled = true;
    };
  }, [bookingId, reloadTick]);

  if (loading) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center py-20">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-teal border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-bold text-ink-muted">Initializing student classroom staging...</p>
        </div>
      </div>
    );
  }

  if (loadError || !booking) {
    return (
      <div className="min-h-screen bg-cream py-20">
        <div className="max-w-xl mx-auto px-4 text-center space-y-6">
          <ErrorState
            error={loadError ?? "The requested booking session does not exist or has expired."}
            title="We could not load this classroom"
            onRetry={() => setReloadTick((t) => t + 1)}
          />
          <Link
            href="/student/dashboard"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-teal text-white text-xs font-bold"
          >
            <ArrowLeft className="w-4 h-4" /> Return to Student Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const isConfirmed = booking.status === "confirmed" || booking.status === "in_progress";
  const isInterrupted = booking.status === "interrupted_power";

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Top Header Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/student/dashboard"
              className="p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-teal bg-teal/10 px-2 py-0.5 rounded-md">
                  {booking.booking_reference}
                </span>
                <span className="text-xs font-bold text-ink-muted">Synchronous Lesson Pad</span>
              </div>
              <h1 className="text-xl sm:text-2xl font-black text-ink font-serif">
                Classroom Staging &amp; Live Lesson
              </h1>
            </div>
          </div>

          {/* Quick Hardware Check Trigger & Eskom Button */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setHardwareModalOpen(true)}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold border transition-colors flex items-center gap-2 shadow-xs ${
                hardwareChecked
                  ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                  : "bg-white text-ink border-divider hover:bg-cream-surface"
              }`}
            >
              {hardwareChecked ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>AV Hardware Verified</span>
                </>
              ) : (
                <>
                  <Camera className="w-4 h-4 text-teal" />
                  <span>Test Camera &amp; Mic</span>
                </>
              )}
            </button>

            <EskomReportButton
              bookingId={booking.id}
              isInterrupted={isInterrupted}
              onReported={() => setBooking({ ...booking, status: "interrupted_power" })}
            />
          </div>
        </div>

        {/* Countdown Clock Bar */}
        <LessonCountDownClock
          startTimeUtc={booking.start_time_utc}
          endTimeUtc={booking.end_time_utc}
        />

        {/* Dual Split Layout */}
        <ClassroomSplitLayout material={material}>
          {/* Left Pane Cockpit Content */}
          <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
            {/* Tutor Profile Summary */}
            <div className="flex items-start gap-4 border-b border-divider pb-6">
              <div className="w-16 h-16 rounded-2xl overflow-hidden bg-cream-surface border border-divider shrink-0">
                {booking.teacher.avatar_url ? (
                  <img
                    src={booking.teacher.avatar_url}
                    alt={booking.teacher.full_name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center font-bold text-teal text-xl">
                    {booking.teacher.first_name[0]}
                  </div>
                )}
              </div>

              <div className="space-y-1 flex-1">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-black text-ink font-serif">{booking.teacher.full_name}</h3>
                  <span className="text-[11px] font-bold text-teal bg-teal/10 px-2 py-0.5 rounded-full">
                    Native Tutor
                  </span>
                </div>
                <p className="text-xs text-ink-muted">{booking.teacher.accent}</p>
                <p className="text-xs text-ink font-medium">
                  {booking.local_date} · {booking.local_start_time} - {booking.local_end_time} ({booking.viewer_timezone})
                </p>
              </div>
            </div>

            {/* Launch Zoom Call to Action */}
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs font-bold text-ink">
                <span>Synchronous Video Room</span>
                <span className="text-[11px] text-success flex items-center gap-1 font-bold">
                  <ShieldCheck className="w-3.5 h-3.5" /> End-to-End Encrypted
                </span>
              </div>

              {booking.zoom_meeting_id && (booking.zoom_join_url || booking.zoom_url) ? (
                <ZoomLauncherButton
                  meetingId={booking.zoom_meeting_id}
                  password={booking.zoom_password || ""}
                  joinUrl={(booking.zoom_join_url || booking.zoom_url) as string}
                  disabled={!isConfirmed}
                />
              ) : (
                <div className="p-4 rounded-2xl bg-cream-surface border border-divider text-xs text-ink-muted">
                  Your Zoom room details are not available yet. They appear here once the lesson is confirmed.
                </div>
              )}
              {materialError ? <InlineError error={materialError} /> : null}
            </div>

            {/* Student Staging Checklist */}
            <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-3 text-xs">
              <span className="font-bold text-ink flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-teal" /> Pre-Session Classroom Checklist
              </span>
              <div className="space-y-2 text-ink-muted text-[11px]">
                <div className="flex items-center gap-2">
                  <Headphones className="w-3.5 h-3.5 text-teal shrink-0" />
                  <span>Use headphones or a headset to eliminate audio echo during speaking practice.</span>
                </div>
                <div className="flex items-center gap-2">
                  <Camera className="w-3.5 h-3.5 text-teal shrink-0" />
                  <span>Position your camera at eye level with adequate front-facing lighting.</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-teal shrink-0" />
                  <span>The interactive curriculum on the right is synchronized with your tutor&apos;s pad.</span>
                </div>
              </div>
            </div>
          </div>
        </ClassroomSplitLayout>

        {/* Hardware AV Tester Modal */}
        <HardwareCheckModal
          isOpen={hardwareModalOpen}
          onClose={() => setHardwareModalOpen(false)}
          onComplete={() => setHardwareChecked(true)}
        />
      </div>
    </div>
  );
}
