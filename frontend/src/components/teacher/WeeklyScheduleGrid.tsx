"use client";

import { useEffect, useState } from "react";
import { Check, Save, Clock, Copy, Sparkles, AlertCircle, Info } from "lucide-react";
import { api } from "@/lib/api";
import { request } from "@/lib/http";
import {
  DAYS,
  TIME_BLOCKS,
  conflictsFromError,
  rowsToMatrix,
  wouldChangeSavedWindows,
  type AvailabilityRow,
  type LessonConflict,
  type WeeklyMatrix,
} from "@/lib/availability";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";
import { useAuth } from "@/context/AuthContext";

interface AvailabilityPage {
  rows: AvailabilityRow[];
  truncated: boolean;
}

async function loadAvailability(): Promise<AvailabilityPage> {
  const res = await request<AvailabilityRow[] | { results: AvailabilityRow[]; next?: string | null }>(
    "/teachers/availability/manage/"
  );
  if (Array.isArray(res)) return { rows: res, truncated: false };
  return { rows: res.results ?? [], truncated: Boolean(res.next) };
}

// The grid is in the tutor's own account timezone (User.timezone), never a hard-coded one.
function lessonTime(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    timeZone,
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function WeeklyScheduleGrid() {
  const { user } = useAuth();
  const tutorZone = user?.timezone || "UTC";
  // Matrix state: dayIdx (0-6) -> array of boolean blocks, built from the availability saved on the server.
  const { data: availability, error: loadError, loading, reload } = useApiData(loadAvailability, []);
  const [schedule, setSchedule] = useState<WeeklyMatrix>({});

  useEffect(() => {
    if (!availability) return;
    setSchedule(rowsToMatrix(availability.rows));
  }, [availability]);

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  // Confirmed lessons the save would leave outside the open hours (refused until the tutor acknowledges), and the ones
  // that were left outside after an acknowledged save. Saving never cancels a lesson.
  const [pendingConflicts, setPendingConflicts] = useState<LessonConflict[] | null>(null);
  const [leftConflicts, setLeftConflicts] = useState<LessonConflict[]>([]);

  const toggleSlot = (dayIdx: number, blockIdx: number) => {
    setSchedule((prev) => {
      const daySlots = [...(prev[dayIdx] || new Array(TIME_BLOCKS.length).fill(false))];
      daySlots[blockIdx] = !daySlots[blockIdx];
      return { ...prev, [dayIdx]: daySlots };
    });
    setSaved(false);
  };

  const copyMondayToWeekdays = () => {
    const mondaySlots = [...(schedule[0] || new Array(TIME_BLOCKS.length).fill(false))];
    setSchedule((prev) => ({
      ...prev,
      1: [...mondaySlots],
      2: [...mondaySlots],
      3: [...mondaySlots],
      4: [...mondaySlots],
    }));
    setSaved(false);
  };

  const applyPreset = (preset: "business" | "evening" | "clear") => {
    const newSchedule: { [day: number]: boolean[] } = {};

    DAYS.forEach((d) => {
      if (preset === "clear") {
        newSchedule[d.id] = new Array(TIME_BLOCKS.length).fill(false);
      } else if (preset === "business") {
        // Weekdays: 08:00 - 17:00 (first 8 blocks)
        newSchedule[d.id] =
          d.id < 5
            ? [true, true, true, true, true, true, true, true, false, false, false, false]
            : [false, false, false, false, false, false, false, false, false, false, false, false];
      } else if (preset === "evening") {
        // 17:00 - 21:00 (last 4 blocks)
        newSchedule[d.id] = [false, false, false, false, false, false, false, false, true, true, true, true];
      }
    });

    setSchedule(newSchedule);
    setSaved(false);
  };

  const handleSave = async (acknowledgeConflicts = false) => {
    // Saving from the hourly grid replaces saved windows that do not line up with it (or overlap): ask first (T2 QA MINOR-9).
    if (
      !acknowledgeConflicts &&
      availability &&
      wouldChangeSavedWindows(availability.rows) &&
      !window.confirm("Some of your saved windows do not fit this hourly grid (or overlap). Saving replaces them with the blocks shown. Continue?")
    ) {
      return;
    }
    setSaving(true);
    setSaved(false);
    setSaveError(null);
    try {
      const result = await api.saveTeacherAvailability(schedule, acknowledgeConflicts);
      setPendingConflicts(null);
      setLeftConflicts(result.conflicts);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      reload();
    } catch (e) {
      const conflicts = conflictsFromError(e);
      if (conflicts) {
        setPendingConflicts(conflicts);
      } else {
        console.error("Failed to save schedule:", e);
        setSaveError(e);
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-3xl p-10 border border-divider shadow-card text-center text-sm font-bold text-ink-muted">
        Loading your saved availability...
      </div>
    );
  }

  if (loadError) {
    return <ErrorState error={loadError} title="We couldn't load your availability" onRetry={reload} />;
  }

  // Count active weekly hours
  let activeHours = 0;
  Object.values(schedule).forEach((day) => {
    day.forEach((active) => {
      if (active) activeHours += 1;
    });
  });

  return (
    <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
      {/* Controls & Quick Actions Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-divider pb-6">
        <div>
          <h2 className="text-xl font-black text-ink font-serif">Weekly Recurring Teaching Matrix</h2>
          <p className="text-xs text-ink-muted">
            All slots are in your account timezone ({tutorZone}).
            Converted automatically on student booking pads.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={copyMondayToWeekdays}
            className="px-3 py-1.5 rounded-xl bg-cream-surface hover:bg-cream-deep text-ink text-xs font-bold border border-divider flex items-center gap-1.5 transition-colors"
          >
            <Copy className="w-3.5 h-3.5 text-cocoa" />
            <span>Copy Mon &rarr; Weekdays</span>
          </button>

          <button
            type="button"
            onClick={() => applyPreset("business")}
            className="px-3 py-1.5 rounded-xl bg-cream-surface hover:bg-cream-deep text-ink text-xs font-bold border border-divider transition-colors"
          >
            08:00 - 17:00 Preset
          </button>

          <button
            type="button"
            onClick={() => applyPreset("evening")}
            className="px-3 py-1.5 rounded-xl bg-cream-surface hover:bg-cream-deep text-ink text-xs font-bold border border-divider transition-colors"
          >
            Evening Preset
          </button>

          <button
            type="button"
            onClick={() => applyPreset("clear")}
            className="px-3 py-1.5 rounded-xl bg-cream-surface hover:bg-cream-deep text-ink-muted hover:text-ink text-xs font-bold border border-divider transition-colors"
          >
            Clear All
          </button>

          <button
            type="button"
            onClick={() => handleSave(false)}
            disabled={saving}
            className="px-5 py-2 rounded-xl bg-cocoa hover:bg-cocoa-hover text-white text-xs font-black flex items-center gap-2 shadow-sm transition-all ml-auto lg:ml-2"
          >
            {saved ? <Check className="w-4 h-4 text-gold-bright" /> : <Save className="w-4 h-4" />}
            <span>{saving ? "Saving..." : saved ? "Schedule Saved!" : "Save Availability"}</span>
          </button>
        </div>
      </div>

      <InlineError error={saveError} />
      {availability?.truncated && (
        <p className="text-xs text-warning-hover bg-warning-surface border border-warning-border rounded-xl px-3 py-2">
          Only part of your saved availability could be loaded, so this grid may be incomplete. Do not save from here.
        </p>
      )}
      {availability && wouldChangeSavedWindows(availability.rows) && (
        <p className="text-xs text-warning-hover bg-warning-surface border border-warning-border rounded-xl px-3 py-2">
          Some saved windows do not line up with this hourly grid (or overlap each other). Saving here replaces them with
          the blocks shown.
        </p>
      )}
      {pendingConflicts && (
        <div role="alert" className="text-xs text-warning-hover bg-warning-surface border border-warning-border rounded-2xl px-4 py-3 space-y-2">
          <p className="font-bold">
            Nothing was saved: {pendingConflicts.length} confirmed lesson{pendingConflicts.length === 1 ? "" : "s"} would
            fall outside your open hours.
          </p>
          <ul className="list-disc pl-5">
            {pendingConflicts.map((c) => (
              <li key={c.booking_id}>{lessonTime(c.start_time_utc, tutorZone)} ({tutorZone})</li>
            ))}
          </ul>
          <p>
            Saving anyway keeps these lessons booked: you must still teach them, or cancel them from your lessons (late
            cancellations count as strikes).
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={() => handleSave(true)}
              className="px-3 py-1.5 rounded-xl bg-cocoa hover:bg-cocoa-hover text-white font-black"
            >
              Save anyway
            </button>
            <button
              type="button"
              onClick={() => setPendingConflicts(null)}
              className="px-3 py-1.5 rounded-xl bg-white border border-divider font-bold"
            >
              Keep editing
            </button>
          </div>
        </div>
      )}
      {leftConflicts.length > 0 && (
        <p className="text-xs text-warning-hover bg-warning-surface border border-warning-border rounded-xl px-3 py-2">
          Saved. {leftConflicts.length} confirmed lesson{leftConflicts.length === 1 ? " is" : "s are"} outside your new hours but
          still booked: teach {leftConflicts.length === 1 ? "it" : "them"} or cancel from your lessons.
        </p>
      )}

      {/* Summary Indicator */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-2xl bg-cream-surface border border-divider text-xs">
        <span className="font-bold text-ink flex items-center gap-1.5">
          <Clock className="w-4 h-4 text-cocoa" /> Total Open Hours:
          <span className="text-cocoa font-extrabold ml-1">{activeHours} hours/week</span>
          <span className="text-ink-muted font-normal ml-1">({activeHours * 2} discrete 25-min slots)</span>
        </span>

        <span className="text-xs text-ink-muted italic">
          Select a block to open or close it. Dark blocks are open for students to book.
        </span>
      </div>

      {/* 7-Day Matrix Table */}
      <div className="overflow-x-auto rounded-2xl border border-divider">
        <table className="w-full min-w-[700px] border-collapse text-sm">
          <thead>
            <tr className="bg-cream-surface border-b border-divider">
              <th className="py-3 px-4 font-bold text-ink-muted uppercase tracking-wider text-left w-36">
                Time (local)
              </th>
              {DAYS.map((d) => (
                <th key={d.id} className="py-3 px-2 font-black text-ink text-center">
                  <div>{d.label}</div>
                  <span className="text-xs font-normal text-ink-muted hidden sm:inline">{d.full}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-divider bg-white">
            {TIME_BLOCKS.map((timeRange, blockIdx) => (
              <tr key={timeRange} className="hover:bg-cream-surface/40 transition-colors">
                <td className="py-2.5 px-4 font-bold text-ink font-mono whitespace-nowrap bg-cream-surface/20">
                  {timeRange}
                </td>
                {DAYS.map((d) => {
                  const isOpen = schedule[d.id]?.[blockIdx];
                  return (
                    <td key={d.id} className="py-1.5 px-2 text-center">
                      <button
                        type="button"
                        onClick={() => toggleSlot(d.id, blockIdx)}
                        className={`w-full min-h-[44px] py-2 px-1 rounded-xl text-sm font-bold transition-all ${
                          isOpen
                            ? "bg-cocoa text-white shadow-xs hover:bg-cocoa-hover"
                            : "bg-cream-surface text-ink-muted hover:bg-cream-deep hover:text-ink border border-divider/60"
                        }`}
                      >
                        {isOpen ? "Open" : "—"}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
