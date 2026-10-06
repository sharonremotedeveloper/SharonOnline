"use client";

import Link from "next/link";
import { CalendarPlus, CheckCircle2, Clock, ExternalLink, Video } from "lucide-react";
import { useApiData } from "@/hooks/useApiData";
import { useEffect, useState } from "react";
import { getStudentLessons } from "@/lib/api";
import type { StudentLessonItem } from "@/types/student";

function calendarUrl(lesson: StudentLessonItem) {
  const start = new Date(lesson.start_time_utc).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const end = new Date(lesson.end_time_utc).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(`Sharon Online lesson with ${lesson.teacher.name}`)}&dates=${start}/${end}&details=${encodeURIComponent(lesson.zoom_url || "Join from Sharon Online")}`;
}
function canEnter(lesson: StudentLessonItem) { const now = Date.now(); const start = new Date(lesson.start_time_utc).getTime(); return lesson.status === "confirmed" && now >= start - 15 * 60_000 && now <= start + 30 * 60_000; }

export default function StudentSchedulePage() {
  const lessons = useApiData(getStudentLessons, []);
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), []);
  const rows = [...(lessons.data || [])].sort((a, b) => Date.parse(a.start_time_utc) - Date.parse(b.start_time_utc));
  return <main className="min-h-screen bg-cream px-4 py-10 sm:px-6 lg:px-8"><div className="mx-auto max-w-5xl space-y-7"><header><p className="text-sm font-bold uppercase tracking-[.18em] text-cocoa">Student workspace</p><h1 className="mt-2 font-serif text-4xl font-black text-ink">Your schedule</h1><p className="mt-2 text-sm text-ink-muted">Upcoming and past lessons are shown in your saved timezone.</p></header>{lessons.loading && <div className="rounded-3xl bg-white p-8 shadow-card">Loading your lessons…</div>}{lessons.error != null && <div className="rounded-2xl bg-warning-surface p-5 text-sm text-warning-hover">Your schedule could not be loaded.</div>} {!lessons.loading && lessons.error == null && <div className="space-y-4">{rows.map((lesson) => { const upcoming = now === null || Date.parse(lesson.end_time_utc) >= now; return <article key={lesson.id} className="rounded-3xl border border-divider bg-white p-6 shadow-card"><div className="flex flex-col justify-between gap-5 sm:flex-row"><div><div className="flex flex-wrap items-center gap-2 text-sm font-bold text-cocoa"><span>{lesson.local_date}</span><span>·</span><span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> {lesson.local_start_time}–{lesson.local_end_time}</span><span className="rounded-full bg-cocoa/10 px-2 py-1">{lesson.viewer_timezone}</span></div><h2 className="mt-3 font-serif text-2xl font-black text-ink">{lesson.teacher.name}</h2><p className="mt-1 text-sm text-ink-muted">{lesson.material_title || "English lesson"} · {lesson.status}</p></div><div className="flex flex-wrap items-center gap-2">{upcoming && now !== null && canEnter(lesson) && <Link href={`/student/classroom/${lesson.id}`} className="inline-flex items-center gap-2 rounded-xl bg-cocoa px-4 py-2.5 text-sm font-bold text-white"><Video className="h-4 w-4" /> Enter classroom</Link>}{upcoming && <a href={calendarUrl(lesson)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl border border-divider px-4 py-2.5 text-sm font-bold text-ink"><CalendarPlus className="h-4 w-4 text-cocoa" /> Add to Google Calendar</a>}{!upcoming && <span className="inline-flex items-center gap-2 rounded-xl bg-success-surface px-4 py-2.5 text-sm font-bold text-success-hover"><CheckCircle2 className="h-4 w-4" /> Completed</span>}</div></div></article>; })}{rows.length === 0 && <div className="rounded-3xl bg-white p-10 text-center shadow-card"><h2 className="font-serif text-2xl font-black text-ink">No lessons yet</h2><Link href="/tutors" className="mt-4 inline-block rounded-xl bg-cocoa px-4 py-2 text-sm font-bold text-white">Find a tutor</Link></div>}</div>}</div></main>;
}
