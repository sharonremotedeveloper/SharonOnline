"use client";

import { useEffect, useState } from "react";
import { Clock, AlertCircle, CheckCircle2, Sparkles } from "lucide-react";

interface LessonCountDownClockProps {
  startTimeUtc: string;
  endTimeUtc?: string;
  onLessonEnded?: () => void;
  className?: string;
}

export function LessonCountDownClock({
  startTimeUtc,
  endTimeUtc,
  onLessonEnded,
  className = "",
}: LessonCountDownClockProps) {
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const startMs = new Date(startTimeUtc).getTime();
  const endMs = endTimeUtc
    ? new Date(endTimeUtc).getTime()
    : startMs + 25 * 60 * 1000;

  const diffMs = startMs - now;
  const inProgressMs = endMs - now;

  // Formatting helpers
  const formatTime = (totalSeconds: number) => {
    const s = Math.max(0, Math.floor(totalSeconds));
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  // State 1: Before lesson (> 5m before)
  if (diffMs > 5 * 60 * 1000) {
    const totalMinutes = Math.floor(diffMs / 60000);
    const hours = Math.floor(totalMinutes / 60);
    const mins = totalMinutes % 60;

    return (
      <div className={`p-4 rounded-2xl bg-cream-surface border border-divider flex items-center justify-between gap-3 ${className}`}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-teal/10 text-teal flex items-center justify-center">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <span className="text-xs font-bold text-ink block">Scheduled Session</span>
            <span className="text-[11px] text-ink-muted">Lesson staging room opens 5 minutes before start</span>
          </div>
        </div>
        <div className="text-right">
          <span className="text-xs uppercase tracking-wider text-ink-muted block font-semibold">Starts in</span>
          <span className="text-sm font-extrabold text-teal">
            {hours > 0 ? `${hours}h ${mins}m` : `${mins} mins`}
          </span>
        </div>
      </div>
    );
  }

  // State 2: Staging window (within 5m before start)
  if (diffMs > 0 && diffMs <= 5 * 60 * 1000) {
    return (
      <div className={`p-4 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-between gap-3 ${className}`}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-emerald-600 text-white flex items-center justify-center animate-pulse">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <span className="text-xs font-black text-emerald-950 block">Staging Window Active</span>
            <span className="text-[11px] text-emerald-800">Complete your AV hardware check and join early</span>
          </div>
        </div>
        <div className="text-right font-mono">
          <span className="text-[10px] uppercase tracking-wider text-emerald-700 block font-bold">Starts in</span>
          <span className="text-lg font-black text-emerald-900">{formatTime(diffMs / 1000)}</span>
        </div>
      </div>
    );
  }

  // State 3: Lesson in progress (0 to 25m)
  if (inProgressMs > 0) {
    const isWrapUp = inProgressMs <= 3 * 60 * 1000;

    return (
      <div
        className={`p-4 rounded-2xl border flex items-center justify-between gap-3 ${
          isWrapUp
            ? "bg-amber-50 border-amber-200 text-amber-950"
            : "bg-teal/10 border-teal/30 text-ink"
        } ${className}`}
      >
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-3 w-3">
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                isWrapUp ? "bg-accent" : "bg-teal"
              }`}
            />
            <span
              className={`relative inline-flex rounded-full h-3 w-3 ${
                isWrapUp ? "bg-accent" : "bg-teal"
              }`}
            />
          </span>
          <div>
            <span className="text-xs font-black block">
              {isWrapUp ? "Session Wrap-Up Period" : "Lesson Currently In Progress"}
            </span>
            <span className="text-[11px] opacity-80">
              {isWrapUp ? "Tutor summarizing key notes & feedback" : "Live 25-minute synchronous classroom"}
            </span>
          </div>
        </div>

        <div className="text-right font-mono">
          <span className="text-[10px] uppercase tracking-wider opacity-75 block font-bold">Time Left</span>
          <span className={`text-lg font-black ${isWrapUp ? "text-accent" : "text-teal"}`}>
            {formatTime(inProgressMs / 1000)}
          </span>
        </div>
      </div>
    );
  }

  // State 4: Lesson concluded
  return (
    <div className={`p-4 rounded-2xl bg-cream-surface border border-divider flex items-center justify-between gap-3 ${className}`}>
      <div className="flex items-center gap-2.5">
        <CheckCircle2 className="w-5 h-5 text-success" />
        <div>
          <span className="text-xs font-black text-ink block">Lesson Concluded</span>
          <span className="text-[11px] text-ink-muted">25-minute synchronous session has finished</span>
        </div>
      </div>
      <span className="text-xs font-extrabold text-ink-muted">00:00</span>
    </div>
  );
}
