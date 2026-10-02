"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Clock, Globe, ArrowRight, ShieldCheck, Zap, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { Slot, TeacherSlotsResponse } from "@/types";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

interface InlineSlotMatrixProps {
  tutorId: string;
  tutorName: string;
  pricePerLesson: number;
}

const COMMON_TIMEZONES = [
  { value: "Asia/Tokyo", label: "Tokyo / Seoul (JST/KST, UTC+9)" },
  { value: "Europe/London", label: "London (GMT/BST, UTC+0/+1)" },
  { value: "Europe/Paris", label: "Paris / Berlin (CET/CEST, UTC+1/+2)" },
  { value: "Africa/Johannesburg", label: "Johannesburg (SAST, UTC+2)" },
  { value: "America/New_York", label: "New York (EST/EDT, UTC-5/-4)" },
];

export function InlineSlotMatrix({ tutorId, tutorName, pricePerLesson }: InlineSlotMatrixProps) {
  const router = useRouter();
  const [timezone, setTimezone] = useState("Asia/Tokyo");
  const [slotsData, setSlotsData] = useState<TeacherSlotsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [reserving, setReserving] = useState(false);
  const [reserveError, setReserveError] = useState<unknown>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected) setTimezone(detected);
    } catch (e) {}
  }, []);

  useEffect(() => {
    async function loadSlots() {
      if (!tutorId) return;
      setLoading(true);
      setLoadError(null);
      try {
        const res = await api.getTeacherSlots(tutorId, timezone, 7);
        setSlotsData(res);
      } catch (err) {
        console.error("Failed to load slots:", err);
        setSlotsData(null);
        setLoadError(err);
      } finally {
        setLoading(false);
      }
    }
    loadSlots();
  }, [tutorId, timezone, reloadTick]);

  const handleSelectSlot = async (slot: Slot) => {
    if (!slot.is_bookable) return;
    setSelectedSlot(slot);
    setReserving(true);
    setReserveError(null);

    try {
      const res = await api.reserveSlot(tutorId, slot.start_time_utc);
      // Route directly to checkout or student booking summary
      if (!res?.booking_id) throw new Error("The server did not return a booking for this slot. Please try again.");
      router.push(`/student/checkout/${res.booking_id}`);
    } catch (err) {
      console.error("Failed to reserve slot:", err);
      setReserveError(err);
      setSelectedSlot(null);
      setReserving(false);
    }
  };

  return (
    <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
      {/* Header & Timezone Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-6">
        <div>
          <h3 className="text-xl font-extrabold text-ink font-serif">Book a 25-Minute Lesson</h3>
          <p className="text-xs text-ink-muted mt-0.5">
            Times automatically adjust to your local computer clock
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-teal" />
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="bg-cream-surface border border-divider rounded-xl px-3 py-1.5 text-xs font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal cursor-pointer"
          >
            {COMMON_TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>
                {tz.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <InlineError error={reserveError} />

      {/* 7-Day Slot Columns */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 animate-pulse">
          {[1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div key={i} className="h-44 bg-cream-surface rounded-2xl border border-divider" />
          ))}
        </div>
      ) : loadError ? (
        <ErrorState
          error={loadError}
          title="We couldn't load availability"
          onRetry={() => setReloadTick((t) => t + 1)}
        />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            {slotsData?.slots && slotsData.slots.length > 0 ? (
              slotsData.slots.map((slot) => {
                const isSelected = selectedSlot?.start_time_utc === slot.start_time_utc;
                return (
                  <button
                    key={slot.start_time_utc}
                    disabled={!slot.is_bookable || reserving}
                    onClick={() => handleSelectSlot(slot)}
                    className={`p-3 rounded-2xl border text-center transition-all flex flex-col justify-between space-y-2 ${
                      isSelected
                        ? "bg-teal text-white border-teal shadow-md ring-2 ring-teal/30"
                        : slot.is_bookable
                        ? "bg-cream-surface hover:bg-cream-deep hover:border-teal border-divider text-ink"
                        : "bg-gray-50 border-gray-200 text-gray-400 opacity-60 cursor-not-allowed"
                    }`}
                  >
                    <div className="text-[11px] font-semibold text-ink-muted">
                      {slot.local_date}
                    </div>

                    <div className="text-base font-extrabold font-serif">
                      {slot.local_start_time}
                    </div>

                    <div className="text-[10px] font-bold">
                      {slot.is_bookable ? (
                        <span className="text-success">Available</span>
                      ) : (
                        <span>Booked</span>
                      )}
                    </div>
                  </button>
                );
              })
            ) : (
              <div className="col-span-full py-8 text-center text-xs text-ink-muted">
                No slots open this week. Check back soon or request a custom schedule.
              </div>
            )}
          </div>

          <div className="p-3 bg-cream-surface rounded-2xl border border-cream-deep flex items-center justify-between text-xs text-ink-muted">
            <div className="flex items-center gap-2">
              <Lock className="w-3.5 h-3.5 text-teal" />
              <span>Selecting a slot initiates a <strong>10-minute lock</strong> to complete booking.</span>
            </div>
            <div className="text-right font-bold text-ink">
              ${pricePerLesson.toFixed(2)} / class
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
