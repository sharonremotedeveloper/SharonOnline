"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  User,
  FileEdit,
  Video,
  CheckCircle2,
  Camera,
  Sparkles,
  Target,
  BookOpen,
  Send,
  ShieldCheck,
  Save,
} from "lucide-react";
import { api } from "@/lib/api";
import { ErrorState } from "@/components/ui/ErrorState";
import { BookingDetail } from "@/types/booking";
import { MaterialDetail } from "@/types/material";
import { HardwareCheckModal } from "@/components/classroom/HardwareCheckModal";
import { ZoomLauncherButton } from "@/components/classroom/ZoomLauncherButton";
import { VideoSdkClassroom } from "@/components/classroom/VideoSdkClassroom";
import { LessonCountDownClock } from "@/components/classroom/LessonCountDownClock";
import { EskomReportButton } from "@/components/classroom/EskomReportButton";
import { ClassroomSplitLayout } from "@/components/classroom/ClassroomSplitLayout";

export default function TeacherClassroomPage() {
  const params = useParams();
  const router = useRouter();
  const bookingId = params?.id as string;

  const [booking, setBooking] = useState<BookingDetail | null>(null);
  const [material, setMaterial] = useState<MaterialDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [materialError, setMaterialError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [hardwareModalOpen, setHardwareModalOpen] = useState(false);
  const [hardwareChecked, setHardwareChecked] = useState(false);
  const [scratchNotes, setScratchNotes] = useState("");

  useEffect(() => {
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
        try {
          if (b.material_slug) {
            const m = await api.getMaterialBySlug(b.material_slug);
            if (!cancelled) setMaterial(m);
          }
        } catch (err) {
          console.error("Failed to load lesson material:", err);
          if (!cancelled) setMaterialError(err);
        }
      } catch (err) {
        console.error("Failed to load tutor classroom:", err);
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

  // Scratch notes are kept in this browser session only and handed to the memo studio; they are not sent to the server.
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(`scratch:${bookingId}`);
      if (saved) setScratchNotes(saved);
    } catch {
      /* storage unavailable: notes simply won't persist */
    }
  }, [bookingId]);

  const handleNotesChange = (value: string) => {
    setScratchNotes(value);
    try {
      sessionStorage.setItem(`scratch:${bookingId}`, value);
    } catch {
      /* storage unavailable: notes simply won't persist */
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center py-20">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-cocoa border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-bold text-ink-muted">Loading tutor cockpit &amp; classroom pad...</p>
        </div>
      </div>
    );
  }

  if (loadError || !booking) {
    return (
      <div className="min-h-screen bg-cream py-20">
        <div className="max-w-xl mx-auto px-4 space-y-6">
          <ErrorState
            error={loadError ?? "Classroom session not found."}
            title="We couldn't load this classroom session"
            onRetry={() => setReloadTick((t) => t + 1)}
          />
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

  const isConfirmed = booking.status === "confirmed" || booking.status === "in_progress";
  const isInterrupted = booking.status === "interrupted_power";

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Header Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/teacher/dashboard"
              className="p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-gold-bright bg-accent/15 px-2 py-0.5 rounded-md">
                  TUTOR COCKPIT
                </span>
                <span className="text-xs font-bold text-ink-muted">Ref: {booking.booking_reference}</span>
              </div>
              <h1 className="text-xl sm:text-2xl font-black text-ink font-serif">
                Classroom Staging &amp; Host Control
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setHardwareModalOpen(true)}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold border transition-colors flex items-center gap-2 shadow-xs ${
                hardwareChecked
                  ? "bg-success-surface text-success-hover border-success-border"
                  : "bg-white text-ink border-divider hover:bg-cream-surface"
              }`}
            >
              {hardwareChecked ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-success" />
                  <span>Hardware Ready</span>
                </>
              ) : (
                <>
                  <Camera className="w-4 h-4 text-cocoa" />
                  <span>Test AV Setup</span>
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

        {/* Synchronous Countdown Clock */}
        <LessonCountDownClock
          startTimeUtc={booking.start_time_utc}
          endTimeUtc={booking.end_time_utc}
        />

        {/* Dual Split Layout */}
        <ClassroomSplitLayout material={material} isTeacher={true}>
          {/* Left Pane Tutor Host Controls */}
          <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
            {/* Student Dossier Overview */}
            <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl bg-cocoa/10 text-cocoa flex items-center justify-center font-bold">
                    <User className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-black text-ink">{booking.student.full_name}</h3>
                    <p className="text-xs text-ink-muted">{booking.student.email}</p>
                  </div>
                </div>

                {booking.student.target_level && (
                  <span className="text-xs font-extrabold text-cocoa bg-cocoa/10 px-2.5 py-1 rounded-full">
                    Target CEFR: {booking.student.target_level}
                  </span>
                )}
              </div>

              <div className="text-xs text-ink-muted bg-white p-3 rounded-xl border border-divider">
                <span className="font-bold text-ink block mb-0.5">Student Focus &amp; Goals:</span>
                <p className="text-xs leading-relaxed">
                  {booking.student.learning_goals || "The student has not shared any learning goals yet."}
                </p>
              </div>
            </div>

            {/* In-Browser Synchronous Video Stage (Zoom Video SDK) */}
            <div className="space-y-3">
              <VideoSdkClassroom
                bookingId={booking.id}
                isHost={true}
                partnerName={booking.student.full_name}
                legacyJoinUrl={
                  booking.zoom_meeting_id
                    ? `/api/proxy/bookings/${booking.id}/host-link/`
                    : undefined
                }
              />
              {materialError != null && (
                <p className="text-xs text-error">Lesson material could not be loaded.</p>
              )}
            </div>

            {/* In-Lesson Tutor Scratchpad */}
            <div className="space-y-2 pt-2 border-t border-divider">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-1.5">
                  <FileEdit className="w-3.5 h-3.5 text-cocoa" />
                  <span>Lesson Notes &amp; Mispronunciation Scratchpad</span>
                </label>
                <span className="text-xs text-ink-muted flex items-center gap-1">
                  <Save className="w-3 h-3" />
                  <span>Kept in this browser only</span>
                </span>
              </div>

              <textarea
                rows={4}
                value={scratchNotes}
                onChange={(e) => handleNotesChange(e.target.value)}
                placeholder="Jot down mispronounced words, grammar slips, or praise phrases during the call. These will carry into the post-lesson memo..."
                className="w-full p-3.5 bg-cream-surface rounded-2xl border border-divider text-xs text-ink placeholder:text-ink-muted/60 focus:outline-none focus:ring-2 focus:ring-cocoa/30 focus:border-cocoa font-sans leading-relaxed"
              />
            </div>

            {/* Post-Lesson Memo Action */}
            <div className="pt-2 flex items-center justify-between">
              <Link
                href={`/teacher/bookings/${booking.id}/memo`}
                className="w-full py-3 px-4 rounded-xl bg-ink hover:bg-black text-white text-xs font-bold flex items-center justify-center gap-2 transition-colors shadow-sm"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Open Post-Lesson Memo Studio</span>
              </Link>
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
