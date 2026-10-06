"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, CheckCircle2, Clock, LockKeyhole } from "lucide-react";
import { useApiData } from "@/hooks/useApiData";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/http";

type TrainingItem = { slug: string; title: string; summary: string; position: number; estimated_minutes: number; is_required: boolean; completed: boolean };
type TrainingOverview = { modules: TrainingItem[]; required_total: number; required_completed: number; completed_at: string | null; can_train: boolean };

export default function TeacherTrainingPage() {
  const training = useApiData(() => api.getTeacherTraining() as Promise<TrainingOverview>, []);
  const data = training.data;
  const percent = data && data.required_total ? Math.round((data.required_completed / data.required_total) * 100) : 0;

  return (
    <main className="min-h-screen bg-cream px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <header className="rounded-3xl bg-cocoa p-7 text-white shadow-card sm:p-10">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-accent">Teacher training centre</p>
          <h1 className="mt-3 font-serif text-4xl font-black sm:text-5xl">Teach with confidence.</h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-white/80">Complete the required learning modules before opening your calendar to students.</p>
          {!training.loading && data && (
            <div className="mt-8 max-w-xl">
              <div className="mb-2 flex justify-between text-xs font-bold"><span>{data.required_completed} of {data.required_total} required modules</span><span>{percent}%</span></div>
              <div className="h-3 overflow-hidden rounded-full bg-white/15"><div className="h-full rounded-full bg-accent transition-all" style={{ width: `${percent}%` }} /></div>
            </div>
          )}
        </header>

        {training.loading && <div className="rounded-3xl bg-white p-10 text-sm text-ink-muted shadow-card">Loading your training path…</div>}
        {training.error != null && <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">{errorMessage(training.error, "Training could not be loaded.")}</div>}
        {data && !data.can_train && <div className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900"><LockKeyhole className="mt-0.5 h-5 w-5 shrink-0" /><p>Training becomes available after your tutor application is approved. Your progress will be ready here once the review is complete.</p></div>}
        {data && data.can_train && !data.completed_at && <div className="rounded-2xl border border-cocoa/20 bg-cocoa/5 p-5 text-sm text-cocoa">Calendar slots remain locked until all required modules are complete.</div>}

        {data && <section className="grid gap-4 md:grid-cols-2">
          {[...data.modules].sort((a, b) => a.position - b.position).map((module) => (
            <Link key={module.slug} href={`/teacher/training/${module.slug}`} className="group rounded-3xl border border-divider bg-white p-6 shadow-card transition hover:-translate-y-0.5 hover:border-cocoa/30">
              <div className="flex items-start justify-between gap-4"><span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cocoa/10 text-cocoa"><BookOpen className="h-5 w-5" /></span>{module.completed ? <CheckCircle2 className="h-6 w-6 text-emerald-600" /> : <ArrowRight className="h-5 w-5 text-ink-muted transition group-hover:translate-x-1" />}</div>
              <p className="mt-5 text-xs font-bold uppercase tracking-wider text-ink-muted">Module {module.position}{module.is_required ? " · Required" : " · Optional"}</p>
              <h2 className="mt-2 font-serif text-2xl font-black text-ink">{module.title}</h2>
              <p className="mt-3 text-sm leading-6 text-ink-muted">{module.summary}</p>
              <p className="mt-5 flex items-center gap-1.5 text-xs font-bold text-cocoa"><Clock className="h-3.5 w-3.5" /> {module.estimated_minutes} min</p>
            </Link>
          ))}
        </section>}
      </div>
    </main>
  );
}
