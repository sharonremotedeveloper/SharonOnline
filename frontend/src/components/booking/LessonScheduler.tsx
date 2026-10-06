"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Clock, Globe, Lock, Sun, Sunrise, Sunset, Moon } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import type { Slot, TeacherSlotsResponse } from "@/types";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import {
  DAY_PARTS,
  dateRange,
  dayLabel,
  dayPartOf,
  groupByLocalDate,
  monthYearLabel,
  todayInZone,
  zoneCityName,
  zoneOffsetLabel,
} from "@/lib/scheduling";

interface LessonSchedulerProps {
  tutorId: string;
  tutorName: string;
  /** How many calendar days ahead to offer. */
  days?: number;
  /** Where "Sign in" should send the student back to. */
  returnTo?: string;
}

const PART_ICONS = { morning: Sunrise, afternoon: Sun, evening: Sunset, night: Moon } as const;

const BASE_ZONES = [
  "Asia/Tokyo",
  "Asia/Seoul",
  "Europe/London",
  "Europe/Paris",
  "Africa/Johannesburg",
  "America/New_York",
  "America/Los_Angeles",
];

/**
 * Pick a day, then a time. One component for the tutor profile and the student booking page, so the two can never
 * disagree. Every date and time comes from the server in the viewer's zone; nothing here converts a slot.
 */
export function LessonScheduler({ tutorId, tutorName, days = 14, returnTo }: LessonSchedulerProps) {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const stripRef = useRef<HTMLDivElement>(null);

  const [timezone, setTimezone] = useState<string | null>(null);
  const [slotsData, setSlotsData] = useState<TeacherSlotsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [reserving, setReserving] = useState(false);
  const [reserveError, setReserveError] = useState<unknown>(null);
  const [detectedZone, setDetectedZone] = useState<string | null>(null);

  // Start in the visitor's own zone; fall back to Tokyo (our largest market) if the browser will not say.
  useEffect(() => {
    let zone = "Asia/Tokyo";
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected) {
        zone = detected;
        setDetectedZone(detected);
      }
    } catch {
      // keep the fallback
    }
    setTimezone(zone);
  }, []);

  useEffect(() => {
    if (!tutorId || !timezone) return;
    let active = true;
    setLoading(true);
    setLoadError(null);
    setSelectedSlot(null);
    api
      .getTeacherSlots(tutorId, timezone, days)
      .then((res: TeacherSlotsResponse) => {
        if (active) setSlotsData(res);
      })
      .catch((err: unknown) => {
        if (!active) return;
        console.error("Failed to load slots:", err);
        setSlotsData(null);
        setLoadError(err);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tutorId, timezone, days, reloadTick]);

  // Only bookable times are offered: a taken time is simply not there, as on other tutoring sites.
  const byDay = useMemo(
    () => groupByLocalDate((slotsData?.slots ?? []).filter((s) => s.is_bookable)),
    [slotsData],
  );
  const calendar = useMemo(() => (timezone ? dateRange(todayInZone(timezone), days) : []), [timezone, days]);

  // Open on the first day that has a time, and move there again when the zone or data changes.
  useEffect(() => {
    if (loading || calendar.length === 0) return;
    setSelectedDate((current) => {
      if (current && byDay.has(current)) return current;
      return calendar.find((d) => byDay.has(d)) ?? null;
    });
  }, [loading, calendar, byDay]);

  const zones = useMemo(() => {
    const list = [...BASE_ZONES];
    if (detectedZone && !list.includes(detectedZone)) list.unshift(detectedZone);
    return list;
  }, [detectedZone]);

  const zoneName = timezone ? zoneCityName(timezone) : "";
  const zoneOffset = timezone ? zoneOffsetLabel(timezone) : "";
  const daySlots = selectedDate ? byDay.get(selectedDate) ?? [] : [];
  const totalTimes = [...byDay.values()].reduce((n, d) => n + d.length, 0);
  const selectedLabel = selectedSlot ? dayLabel(selectedSlot.local_date) : null;

  const scrollStrip = (direction: -1 | 1) => {
    stripRef.current?.scrollBy({ left: direction * 280, behavior: "smooth" });
  };

  const reserve = async () => {
    if (!selectedSlot) return;
    setReserving(true);
    setReserveError(null);
    try {
      const res = await api.reserveSlot(tutorId, selectedSlot.start_time_utc);
      if (!res?.booking_id) throw new Error("The server did not return a booking for this time. Please try again.");
      router.push(`/student/checkout/${res.booking_id}`);
    } catch (err) {
      console.error("Failed to reserve slot:", err);
      setReserveError(err);
      setReserving(false);
      // The time may have just been taken: reload so the list is honest.
      setReloadTick((t) => t + 1);
    }
  };

  const loginHref = `/login?next=${encodeURIComponent(returnTo ?? `/student/book/${tutorId}`)}`;

  return (
    <section aria-label={`Book a lesson with ${tutorName}`} className="min-w-0 space-y-5">
      {/* Time zone */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <label htmlFor="scheduler-timezone" className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Globe className="h-4 w-4 text-cocoa" aria-hidden="true" />
          Times are shown in
        </label>
        <select
          id="scheduler-timezone"
          value={timezone ?? ""}
          onChange={(e) => setTimezone(e.target.value)}
          disabled={!timezone}
          className="min-h-[44px] w-full cursor-pointer rounded-xl border border-strong bg-cream-surface px-3 text-base sm:text-sm font-semibold text-ink focus:outline-none focus:ring-2 focus:ring-cocoa sm:w-auto sm:min-w-[15rem]"
        >
          {zones.map((z) => (
            <option key={z} value={z}>
              {zoneCityName(z)} ({zoneOffsetLabel(z) || z})
            </option>
          ))}
        </select>
      </div>

      <InlineError error={reserveError} />

      {loadError ? (
        <ErrorState error={loadError} title="We could not load this tutor's times" onRetry={() => setReloadTick((t) => t + 1)} />
      ) : loading || !timezone ? (
        <div className="space-y-4" role="status" aria-label="Loading available times">
          <div className="flex gap-2 overflow-hidden">
            {Array.from({ length: 7 }, (_, i) => (
              <div key={i} className="h-[84px] w-[68px] shrink-0 animate-pulse rounded-2xl bg-cream-deep/60" />
            ))}
          </div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="h-11 animate-pulse rounded-xl bg-cream-deep/60" />
            ))}
          </div>
        </div>
      ) : totalTimes === 0 ? (
        <div className="rounded-2xl border border-divider bg-cream-surface p-8 text-center">
          <Clock className="mx-auto h-8 w-8 text-ink-faint" aria-hidden="true" />
          <p className="mt-3 text-lg font-bold text-ink">No times are open right now</p>
          <p className="mt-1 text-base text-ink-muted">
            {tutorName} has no free lessons in the next {days} days. Please look at another tutor or check back soon.
          </p>
          <Link href="/tutors" className="mt-4 inline-flex min-h-[44px] items-center font-bold text-cocoa underline underline-offset-4">
            See other tutors
          </Link>
        </div>
      ) : (
        <>
          {/* Day strip */}
          <div className="min-w-0">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="font-serif text-lg font-bold text-ink">{selectedDate ? monthYearLabel(selectedDate) : "Choose a day"}</h3>
              <div className="hidden gap-1 sm:flex">
                <button
                  type="button"
                  onClick={() => scrollStrip(-1)}
                  aria-label="Earlier days"
                  className="flex h-11 w-11 items-center justify-center rounded-xl border border-divider bg-white text-ink hover:bg-cream-surface"
                >
                  <ChevronLeft className="h-5 w-5" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => scrollStrip(1)}
                  aria-label="Later days"
                  className="flex h-11 w-11 items-center justify-center rounded-xl border border-divider bg-white text-ink hover:bg-cream-surface"
                >
                  <ChevronRight className="h-5 w-5" aria-hidden="true" />
                </button>
              </div>
            </div>

            <div
              ref={stripRef}
              role="group"
              aria-label="Choose a day"
              className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-2"
            >
              {calendar.map((date) => {
                const count = byDay.get(date)?.length ?? 0;
                const label = dayLabel(date);
                const isSelected = date === selectedDate;
                const hasTimes = count > 0;
                return (
                  <button
                    key={date}
                    type="button"
                    disabled={!hasTimes}
                    aria-pressed={isSelected}
                    aria-label={`${label.long}, ${hasTimes ? `${count} times available` : "no times available"}`}
                    onClick={() => {
                      setSelectedDate(date);
                      setSelectedSlot(null);
                    }}
                    className={`flex h-[84px] w-[68px] shrink-0 snap-start flex-col items-center justify-center rounded-2xl border text-center transition-colors ${
                      isSelected
                        ? "border-cocoa bg-cocoa text-white shadow-sm"
                        : hasTimes
                          ? "border-divider bg-white text-ink hover:border-cocoa hover:bg-cream-surface"
                          : "cursor-not-allowed border-transparent bg-cream-deep/40 text-ink-muted"
                    }`}
                  >
                    <span className={`text-sm font-semibold ${isSelected ? "text-white/90" : "text-ink-muted"}`}>{label.weekday}</span>
                    <span className="font-serif text-2xl font-bold leading-tight">{label.day}</span>
                    <span className={`text-sm ${isSelected ? "text-gold-bright" : hasTimes ? "text-success" : ""}`}>
                      {hasTimes ? `${count} free` : "No times"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Times for the chosen day */}
          {selectedDate && (
            <div className="space-y-4 border-t border-divider pt-4">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                <h3 className="font-serif text-xl font-bold text-ink">{dayLabel(selectedDate).long}</h3>
                <p className="text-sm text-ink-muted">
                  {daySlots.length} {daySlots.length === 1 ? "time" : "times"} · {zoneName} time {zoneOffset && `(${zoneOffset})`}
                </p>
              </div>

              {DAY_PARTS.map((part) => {
                const inPart = daySlots.filter((s) => dayPartOf(s.local_start_time) === part.id);
                if (inPart.length === 0) return null;
                const Icon = PART_ICONS[part.id];
                return (
                  <div key={part.id}>
                    <p className="mb-2 flex items-center gap-2 text-sm font-bold text-ink-muted">
                      <Icon className="h-4 w-4 text-cocoa" aria-hidden="true" />
                      {part.label}
                      <span className="font-normal text-ink-faint">· {part.hint}</span>
                    </p>
                    <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                      {inPart.map((slot) => {
                        const isSelected = selectedSlot?.start_time_utc === slot.start_time_utc;
                        return (
                          <li key={slot.start_time_utc}>
                            <button
                              type="button"
                              aria-pressed={isSelected}
                              disabled={reserving}
                              onClick={() => setSelectedSlot(slot)}
                              className={`flex min-h-[44px] w-full items-center justify-center rounded-xl border text-base font-bold tabular-nums transition-colors disabled:opacity-60 ${
                                isSelected
                                  ? "border-cocoa bg-cocoa text-white shadow-sm"
                                  : "border-divider bg-white text-ink hover:border-cocoa hover:bg-cream-surface"
                              }`}
                            >
                              {slot.local_start_time}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}

          {/* Summary and the one action */}
          <div
            className={`rounded-2xl border p-4 transition-colors ${
              selectedSlot ? "border-cocoa/40 bg-cocoa-surface" : "border-divider bg-cream-surface"
            }`}
          >
            <p className="sr-only" aria-live="polite">
              {selectedSlot && selectedLabel ? `Selected ${selectedLabel.long} at ${selectedSlot.local_start_time}` : ""}
            </p>
            {selectedSlot && selectedLabel ? (
              <div className="space-y-3">
                <div>
                  <p className="text-sm font-semibold text-ink-muted">Your lesson with {tutorName}</p>
                  <p className="font-serif text-xl font-bold text-ink">
                    {selectedLabel.weekday} {selectedLabel.day} {selectedLabel.month}, {selectedSlot.local_start_time} to{" "}
                    {selectedSlot.local_end_time}
                  </p>
                  <p className="text-sm text-ink-muted">
                    25 minutes · {zoneName} time · <LessonPriceLabel className="font-bold text-ink" />
                  </p>
                </div>
                {isAuthenticated ? (
                  <button
                    type="button"
                    onClick={() => void reserve()}
                    disabled={reserving}
                    className="flex min-h-[52px] w-full items-center justify-center rounded-xl bg-primary px-6 text-base font-bold text-white shadow-sm transition-colors hover:bg-primary-hover disabled:opacity-60"
                  >
                    {reserving ? "Holding your time…" : "Reserve this time"}
                  </button>
                ) : (
                  <Link
                    href={loginHref}
                    className="flex min-h-[52px] w-full items-center justify-center rounded-xl bg-primary px-6 text-base font-bold text-white shadow-sm transition-colors hover:bg-primary-hover"
                  >
                    Sign in to reserve this time
                  </Link>
                )}
              </div>
            ) : (
              <p className="text-base text-ink-muted">Pick a time above to continue.</p>
            )}
            <p className="mt-3 flex items-start gap-2 text-sm text-ink-muted">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-cocoa" aria-hidden="true" />
              <span>We hold your time for 10 minutes while you pay. You are not charged yet.</span>
            </p>
          </div>
        </>
      )}
    </section>
  );
}
