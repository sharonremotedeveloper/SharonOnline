"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Clock, Calendar, ShieldCheck, Zap, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { PublicTutor } from "@/types/tutor";
import { BookingSlot } from "@/types/booking";
import { Avatar } from "@/components/ui/Avatar";
import { StarRating } from "@/components/ui/StarRating";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import { TimezoneSelector } from "@/components/booking/TimezoneSelector";
import { SlotGrid } from "@/components/booking/SlotGrid";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

export default function StudentBookingPage() {
  const params = useParams();
  const router = useRouter();
  const tutorId = params?.tutorId as string;

  const [tutor, setTutor] = useState<PublicTutor | null>(null);
  const [timezone, setTimezone] = useState("Asia/Tokyo");
  const [selectedDate, setSelectedDate] = useState("");
  const [allSlots, setAllSlots] = useState<BookingSlot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<BookingSlot | null>(null);
  const [loading, setLoading] = useState(true);
  const [reserving, setReserving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);

  // Detect student timezone
  useEffect(() => {
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected) setTimezone(detected);
    } catch (e) {}
  }, []);

  // Generate 14 rolling calendar days
  const calendarDays = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i);
    const isoDate = d.toISOString().split("T")[0];
    const isToday = i === 0;
    const isTomorrow = i === 1;

    return {
      date: isoDate,
      dayNumber: d.getDate(),
      dayName: d.toLocaleDateString("en-US", { weekday: "short" }),
      monthName: d.toLocaleDateString("en-US", { month: "short" }),
      label: isToday ? "Today" : isTomorrow ? "Tomorrow" : d.toLocaleDateString("en-US", { weekday: "short" }),
    };
  });

  // Load tutor details & slots
  useEffect(() => {
    async function loadData() {
      if (!tutorId) return;
      setLoading(true);
      setLoadError(null);
      try {
        const [tutorRes, slotsRes] = await Promise.all([
          api.getTutor(tutorId),
          api.getTeacherSlots(tutorId, timezone, 14),
        ]);

        setTutor(tutorRes);
        setAllSlots(slotsRes.slots || []);

        setSelectedDate((current) => current || new Date().toISOString().split("T")[0]);
      } catch (err) {
        console.error("Failed to load booking slots:", err);
        setTutor(null);
        setAllSlots([]);
        setLoadError(err);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [tutorId, timezone, reloadTick]);

  const activeDateSlots = allSlots.filter((s) => s.local_date === selectedDate);

  const handleSlotSelect = async (slot: BookingSlot) => {
    setSelectedSlot(slot);
    setReserving(true);
    setError(null);

    try {
      const res = await api.reserveSlot(tutorId, slot.start_time_utc);
      router.push(`/student/checkout/${res.booking_id}`);
    } catch (err) {
      console.error("Failed to reserve slot:", err);
      setError(err);
      setSelectedSlot(null);
      setReserving(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Back button */}
      <div>
        <Link
          href={`/tutors/${tutorId}`}
          className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Tutor Profile
        </Link>
      </div>

      {/* Tutor Mini Showcase Card */}
      {tutor && (
        <div className="bg-white rounded-3xl p-6 border border-divider shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <Avatar src={tutor.avatar_url} name={tutor.full_name} size="lg" />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-extrabold text-ink font-serif">{tutor.full_name}</h1>
                <span>{tutor.country_flag}</span>
              </div>
              <div className="text-xs text-ink-muted">{tutor.accent_display}</div>
              <div className="flex items-center gap-1.5 mt-1">
                <StarRating rating={tutor.rating_avg} size="sm" />
                <span className="text-xs font-bold text-ink">{tutor.rating_avg.toFixed(2)}</span>
              </div>
            </div>
          </div>

          <div className="flex flex-col sm:items-end gap-2 border-t sm:border-t-0 pt-3 sm:pt-0 border-divider">
            <div className="text-right">
              <LessonPriceLabel className="text-2xl font-black text-teal font-serif" />
              <span className="text-xs text-ink-muted"> / 25-minute lesson</span>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] font-bold text-amber-800 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
              <Zap className="w-3 h-3 text-accent" />
              <span>100% Load-Shedding Immune (Inverter Backup)</span>
            </div>
          </div>
        </div>
      )}

      <InlineError error={error} />

      {loadError ? (
        <ErrorState
          error={loadError}
          title="We couldn't load this tutor's availability"
          onRetry={() => setReloadTick((t) => t + 1)}
        />
      ) : (
      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
        {/* Step Header & Timezone Selector */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-6">
          <div>
            <h2 className="text-xl font-extrabold text-ink font-serif">Select Your Lesson Time</h2>
            <p className="text-xs text-ink-muted mt-0.5">
              Choose an available 25-minute discrete slot. Click to hold for 10 minutes.
            </p>
          </div>

          <TimezoneSelector value={timezone} onChange={setTimezone} />
        </div>

        {/* 14-Day Horizontal Rolling Day Picker */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-ink-muted uppercase tracking-wider">
            <span>Choose Date (14-Day Calendar)</span>
            <span className="text-teal font-semibold">Discrete 25-Min Units</span>
          </div>

          <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin">
            {calendarDays.map((day) => {
              const isSelected = selectedDate === day.date;
              return (
                <button
                  key={day.date}
                  onClick={() => setSelectedDate(day.date)}
                  className={`px-4 py-3 rounded-2xl border text-center transition-all shrink-0 min-w-[76px] ${
                    isSelected
                      ? "bg-teal text-white border-teal shadow-md"
                      : "bg-cream-surface hover:bg-cream-deep border-divider text-ink"
                  }`}
                >
                  <div className="text-[10px] font-bold uppercase tracking-wider opacity-80">
                    {day.label}
                  </div>
                  <div className="text-lg font-black font-serif my-0.5">
                    {day.dayNumber}
                  </div>
                  <div className="text-[10px] opacity-75">{day.monthName}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Slot Grid for selected day */}
        <div className="pt-4 border-t border-divider">
          <SlotGrid
            slots={activeDateSlots}
            selectedSlotId={selectedSlot?.id || null}
            onSelectSlot={handleSlotSelect}
            loading={loading}
          />
        </div>
      </div>
      )}
    </div>
  );
}
