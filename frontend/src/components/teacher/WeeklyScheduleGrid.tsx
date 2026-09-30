"use client";

import { useState } from "react";
import { Check, Save, Clock, Copy, Sparkles, AlertCircle, Info } from "lucide-react";
import { api } from "@/lib/api";

const DAYS = [
  { id: 0, label: "Mon", full: "Monday" },
  { id: 1, label: "Tue", full: "Tuesday" },
  { id: 2, label: "Wed", full: "Wednesday" },
  { id: 3, label: "Thu", full: "Thursday" },
  { id: 4, label: "Fri", full: "Friday" },
  { id: 5, label: "Sat", full: "Saturday" },
  { id: 6, label: "Sun", full: "Sunday" },
];

const TIME_BLOCKS = [
  "08:00 - 09:00",
  "09:00 - 10:00",
  "10:00 - 11:00",
  "11:00 - 12:00",
  "13:00 - 14:00",
  "14:00 - 15:00",
  "15:00 - 16:00",
  "16:00 - 17:00",
  "17:00 - 18:00",
  "18:00 - 19:00",
  "19:00 - 20:00",
  "20:00 - 21:00",
];

export function WeeklyScheduleGrid() {
  // Matrix state: dayIdx (0-6) -> array of boolean blocks (0-11)
  const [schedule, setSchedule] = useState<{ [day: number]: boolean[] }>({
    0: [true, true, true, true, true, true, true, true, false, false, false, false], // Mon
    1: [true, true, true, true, true, true, true, true, false, false, false, false], // Tue
    2: [true, true, true, true, true, true, true, true, false, false, false, false], // Wed
    3: [true, true, true, true, true, true, true, true, false, false, false, false], // Thu
    4: [true, true, true, true, true, true, true, true, false, false, false, false], // Fri
    5: [false, false, true, true, true, false, false, false, false, false, false, false], // Sat
    6: [false, false, false, false, false, false, false, false, false, false, false, false], // Sun
  });

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const toggleSlot = (dayIdx: number, blockIdx: number) => {
    setSchedule((prev) => {
      const daySlots = [...(prev[dayIdx] || new Array(TIME_BLOCKS.length).fill(false))];
      daySlots[blockIdx] = !daySlots[blockIdx];
      return { ...prev, [dayIdx]: daySlots };
    });
    setSaved(false);
  };

  const copyMondayToWeekdays = () => {
    const mondaySlots = [...schedule[0]];
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

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.saveTeacherAvailability(schedule);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      console.error("Failed to save schedule:", e);
    } finally {
      setSaving(false);
    }
  };

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
            All slots defined in South African Standard Time (SAST / UTC+2).
            Converted automatically on student booking pads.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={copyMondayToWeekdays}
            className="px-3 py-1.5 rounded-xl bg-cream-surface hover:bg-cream-deep text-ink text-xs font-bold border border-divider flex items-center gap-1.5 transition-colors"
          >
            <Copy className="w-3.5 h-3.5 text-teal" />
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
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2 rounded-xl bg-teal hover:bg-teal-hover text-white text-xs font-black flex items-center gap-2 shadow-sm transition-all ml-auto lg:ml-2"
          >
            {saved ? <Check className="w-4 h-4 text-accent" /> : <Save className="w-4 h-4" />}
            <span>{saving ? "Saving..." : saved ? "Schedule Saved!" : "Save Availability"}</span>
          </button>
        </div>
      </div>

      {/* Summary Indicator */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-2xl bg-cream-surface border border-divider text-xs">
        <span className="font-bold text-ink flex items-center gap-1.5">
          <Clock className="w-4 h-4 text-teal" /> Total Open Hours:
          <span className="text-teal font-extrabold ml-1">{activeHours} hours/week</span>
          <span className="text-ink-muted font-normal ml-1">({activeHours * 2} discrete 25-min slots)</span>
        </span>

        <span className="text-[11px] text-ink-muted italic">
          Click any block to toggle open/closed. Green blocks are live on the booking grid.
        </span>
      </div>

      {/* 7-Day Matrix Table */}
      <div className="overflow-x-auto rounded-2xl border border-divider">
        <table className="w-full min-w-[700px] border-collapse text-xs">
          <thead>
            <tr className="bg-cream-surface border-b border-divider">
              <th className="py-3 px-4 font-bold text-ink-muted uppercase tracking-wider text-left w-36">
                Time (SAST)
              </th>
              {DAYS.map((d) => (
                <th key={d.id} className="py-3 px-2 font-black text-ink text-center">
                  <div>{d.label}</div>
                  <span className="text-[10px] font-normal text-ink-muted hidden sm:inline">{d.full}</span>
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
                        className={`w-full py-2 px-1 rounded-xl text-[11px] font-bold transition-all ${
                          isOpen
                            ? "bg-teal text-white shadow-xs hover:bg-teal-hover"
                            : "bg-cream-surface text-ink-muted/60 hover:bg-cream-deep hover:text-ink border border-divider/60"
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
