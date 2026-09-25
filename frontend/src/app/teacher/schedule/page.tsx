"use client";

import { useState } from "react";
import Link from "next/link";
import { Calendar, Clock, Check, Save, Info, AlertTriangle } from "lucide-react";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

// Standard working blocks
const TIME_BLOCKS = [
  "08:00 - 10:00",
  "10:00 - 12:00",
  "13:00 - 15:00",
  "15:00 - 17:00",
  "17:00 - 19:00",
  "19:00 - 21:00",
];

export default function TeacherSchedulePage() {
  // Matrix state: day -> array of active blocks
  const [schedule, setSchedule] = useState<{ [key: number]: boolean[] }>({
    0: [true, true, true, true, false, false], // Mon
    1: [true, true, true, true, false, false], // Tue
    2: [true, true, true, true, false, false], // Wed
    3: [true, true, true, true, false, false], // Thu
    4: [true, true, true, true, false, false], // Fri
    5: [false, false, false, false, false, false], // Sat
    6: [false, false, false, false, false, false], // Sun
  });

  const [saved, setSaved] = useState(false);

  const toggleBlock = (dayIdx: number, blockIdx: number) => {
    setSchedule((prev) => {
      const currentDay = [...prev[dayIdx]];
      currentDay[blockIdx] = !currentDay[blockIdx];
      return { ...prev, [dayIdx]: currentDay };
    });
    setSaved(false);
  };

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-gray-900 tracking-tight">Weekly Availability Matrix</h1>
          <p className="text-xs sm:text-sm text-gray-500">
            Set your recurring open teaching hours in South African Standard Time (SAST / UTC+2).
          </p>
        </div>

        <button
          onClick={handleSave}
          className="px-6 py-2.5 bg-brand-900 hover:bg-brand-950 text-white font-bold text-xs rounded-xl shadow-md transition-all flex items-center gap-2 self-start sm:self-auto"
        >
          {saved ? <Check className="w-4 h-4 text-emerald-400" /> : <Save className="w-4 h-4" />}
          {saved ? "Schedule Saved!" : "Save Availability"}
        </button>
      </div>

      {/* Info notice */}
      <div className="bg-brand-50 border border-brand-100 rounded-2xl p-4 text-xs text-brand-900 flex items-start gap-3">
        <Info className="w-5 h-5 flex-shrink-0 text-brand-700 mt-0.5" />
        <div className="space-y-1">
          <strong>Automatic UTC Synchronization:</strong> Your selected blocks generate 25-minute lesson slots with 5-minute transition buffers.
          Times are converted automatically for students in Tokyo (+7h), Seoul (+7h), and Europe (-1h).
        </div>
      </div>

      {/* Availability Grid */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-card p-6 overflow-x-auto">
        <table className="w-full min-w-[700px] border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-3 px-4 font-bold text-gray-500 uppercase tracking-wider">Time (SAST)</th>
              {DAYS.map((day) => (
                <th key={day} className="py-3 px-3 font-bold text-gray-900 text-center">
                  {day}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {TIME_BLOCKS.map((timeRange, blockIdx) => (
              <tr key={timeRange} className="hover:bg-gray-50/50">
                <td className="py-3 px-4 font-extrabold text-brand-900 whitespace-nowrap">
                  {timeRange}
                </td>
                {DAYS.map((day, dayIdx) => {
                  const isActive = schedule[dayIdx]?.[blockIdx];
                  return (
                    <td key={day} className="py-2.5 px-3 text-center">
                      <button
                        onClick={() => toggleBlock(dayIdx, blockIdx)}
                        className={`w-full py-2 rounded-lg text-[11px] font-bold transition-all ${
                          isActive
                            ? "bg-brand-900 text-white shadow-sm"
                            : "bg-gray-100 text-gray-400 hover:bg-gray-200"
                        }`}
                      >
                        {isActive ? "Open" : "Closed"}
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
