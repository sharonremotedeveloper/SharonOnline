"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, CheckCircle2, Clock } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/http";
import { useApiData } from "@/hooks/useApiData";

type Module = { slug: string; title: string; summary: string; position: number; estimated_minutes: number; is_required: boolean; completed: boolean; body: string };
function MarkdownBody({ body }: { body: string }) {
  return <div className="prose prose-teal max-w-none text-ink">{body.split(/\r?\n/).map((line, index) => { const value = line.trim(); if (!value) return <div key={index} className="h-3" />; if (value.startsWith("# ")) return <h1 key={index}>{value.slice(2)}</h1>; if (value.startsWith("## ")) return <h2 key={index}>{value.slice(3)}</h2>; if (value.startsWith("- ")) return <li key={index} className="ml-5">{value.slice(2)}</li>; return <p key={index}>{value}</p>; })}</div>;
}

export default function TeacherTrainingModulePage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const trainingModule = useApiData(() => api.getTeacherTrainingModule(slug) as Promise<Module>, [slug]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const complete = async () => { setSaving(true); setError(""); try { await api.completeTeacherTrainingModule(slug); router.push("/teacher/training"); } catch (err) { setError(errorMessage(err, "This module could not be marked complete.")); } finally { setSaving(false); } };
  if (trainingModule.loading) return <main className="min-h-screen bg-cream p-10">Loading module…</main>;
  if (trainingModule.error || !trainingModule.data) return <main className="min-h-screen bg-cream p-10"><p className="rounded-xl bg-amber-50 p-5 text-amber-900">{errorMessage(trainingModule.error, "This module could not be loaded.")}</p><Link className="mt-5 inline-block underline" href="/teacher/training">Back to training</Link></main>;
  const item = trainingModule.data;
  return <main className="min-h-screen bg-cream px-4 py-10 sm:px-6 lg:px-8"><div className="mx-auto max-w-4xl"><Link href="/teacher/training" className="inline-flex items-center gap-2 text-sm font-bold text-ink-muted"><ArrowLeft className="h-4 w-4" /> All training modules</Link><article className="mt-7 rounded-3xl bg-white p-6 shadow-card sm:p-10"><div className="flex flex-wrap items-center gap-3 text-xs font-bold uppercase tracking-wider text-teal"><span>Module {item.position}</span><span>·</span><span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> {item.estimated_minutes} min</span>{item.completed && <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 className="h-4 w-4" /> Completed</span>}</div><h1 className="mt-4 font-serif text-4xl font-black text-ink">{item.title}</h1><p className="mt-3 text-lg text-ink-muted">{item.summary}</p><div className="my-8 border-t border-divider" /><MarkdownBody body={item.body} /><div className="mt-10 border-t border-divider pt-6">{error && <p className="mb-4 rounded-xl bg-amber-50 p-4 text-sm text-amber-900">{error}</p>}{item.completed ? <Link href="/teacher/training" className="inline-flex items-center gap-2 rounded-xl bg-teal px-5 py-3 text-sm font-bold text-white">Continue to training centre <ArrowRight className="h-4 w-4" /></Link> : <button disabled={saving} onClick={complete} className="inline-flex items-center gap-2 rounded-xl bg-teal px-5 py-3 text-sm font-bold text-white disabled:opacity-50">{saving ? "Saving…" : "Complete & Continue"}<ArrowRight className="h-4 w-4" /></button>}</div></article></div></main>;
}
