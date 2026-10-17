"use client";

import Link from "next/link";
import { useApiData } from "@/hooks/useApiData";
import { useEffect, useState } from "react";
import { getStudentLessons } from "@/lib/api";
import { StudentScheduleCard } from "@/components/student/StudentScheduleCard";

export default function StudentSchedulePage() {
  const lessons = useApiData(getStudentLessons, []);
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), []);
  const [view, setView] = useState<"upcoming" | "past">("upcoming");
  const all = lessons.data || [];
  // Upcoming = not finished and not cancelled (soonest first); everything else is Past (newest first).
  const isUpcoming = (l: (typeof all)[number]) =>
    now !== null && Date.parse(l.end_time_utc) >= now && !l.status.startsWith("cancelled");
  const rows = (view === "upcoming"
    ? all.filter(isUpcoming).sort((a, b) => Date.parse(a.start_time_utc) - Date.parse(b.start_time_utc))
    : all.filter((l) => !isUpcoming(l)).sort((a, b) => Date.parse(b.start_time_utc) - Date.parse(a.start_time_utc)));

  return (
    <main className="min-h-screen bg-cream px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-7">
        <header>
          <p className="text-sm font-bold uppercase tracking-[.18em] text-cocoa">Student workspace</p>
          <h1 className="mt-2 font-serif text-3xl font-black text-ink sm:text-4xl">Your schedule</h1>
          <p className="mt-2 text-sm text-ink-muted">Upcoming and past lessons are shown in your saved timezone.</p>
        </header>

        {lessons.loading && <div className="rounded-3xl bg-white p-8 shadow-card">Loading your lessons…</div>}
        {lessons.error != null && (
          <div className="rounded-2xl bg-warning-surface p-5 text-sm text-warning-hover">
            Your schedule could not be loaded.
          </div>
        )}

        {!lessons.loading && lessons.error == null && (
          <div role="tablist" aria-label="Lessons" className="inline-flex rounded-2xl border border-divider bg-white p-1">
            {(["upcoming", "past"] as const).map((v) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={view === v}
                onClick={() => setView(v)}
                className={`min-h-11 rounded-xl px-5 text-sm font-bold capitalize transition-colors ${view === v ? "bg-cocoa text-white" : "text-ink-muted hover:text-ink"}`}
              >
                {v}
              </button>
            ))}
          </div>
        )}

        {!lessons.loading && lessons.error == null && (
          <div className="space-y-4">
            {rows.map((lesson) => (
              <StudentScheduleCard key={lesson.id} lesson={lesson} now={now} />
            ))}

            {rows.length === 0 && (
              <div className="rounded-3xl bg-white p-10 text-center shadow-card">
                <h2 className="font-serif text-2xl font-black text-ink">{view === "upcoming" ? "No upcoming lessons" : "No past lessons yet"}</h2>
                <Link
                  href="/tutors"
                  className="min-h-11 inline-flex items-center mt-4 rounded-xl bg-cocoa px-4 py-2 text-sm font-bold text-white hover:bg-cocoa-hover"
                >
                  Find a tutor
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
