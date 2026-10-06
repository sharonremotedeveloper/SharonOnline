"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, ShieldCheck, Star, Zap } from "lucide-react";
import type { PublicTutor } from "@/types/tutor";
import { api } from "@/lib/api";
import { toPublicTutor } from "@/lib/tutorsDirectory";
import { errorMessage } from "@/lib/http";
import { InlineSlotMatrix } from "@/components/tutors/InlineSlotMatrix";
import { VideoReelPlayer } from "@/components/tutors/VideoReelPlayer";
import { AudioSnippetButton } from "@/components/tutors/AudioSnippetButton";

export default function TutorProfilePage() {
  const { id } = useParams<{ id: string }>(); const [tutor, setTutor] = useState<PublicTutor | null>(null); const [error, setError] = useState("");
  useEffect(() => { let active = true; void api.getTutor(id).then((row) => { if (active) setTutor(toPublicTutor(row as Record<string, unknown>)); }).catch((err) => { if (active) setError(errorMessage(err, "Tutor could not be loaded.")); }); return () => { active = false; }; }, [id]);
  if (error) return <main className="mx-auto max-w-4xl px-6 py-16"><p className="rounded-lg bg-amber-50 p-4 text-amber-900">{error}</p><Link className="mt-5 inline-block underline" href="/tutors">Back to tutors</Link></main>;
  if (!tutor) return <main className="mx-auto max-w-4xl px-6 py-16">Loading tutor…</main>;
  return <main className="mx-auto max-w-7xl px-5 py-10"><Link href="/tutors" className="inline-flex items-center gap-2 text-sm text-[#536963]"><ArrowLeft className="h-4 w-4" /> Back to tutors</Link><div className="mt-8 grid gap-8 lg:grid-cols-[1.4fr_1fr]"><section className="space-y-8"><VideoReelPlayer videoUrl={tutor.intro_video_url} posterUrl={tutor.intro_video_thumbnail || tutor.avatar_url} tutorName={tutor.full_name} headline={tutor.headline} /><article className="rounded-2xl bg-white p-7 shadow-sm"><div className="flex items-start justify-between gap-4"><div><h1 className="font-['Lora'] text-4xl text-[#0E2421]">{tutor.full_name}</h1><p className="mt-2 text-[#536963]">{tutor.headline}</p></div>{tutor.intro_audio_url && <AudioSnippetButton audioUrl={tutor.intro_audio_url} tutorName={tutor.full_name} />}</div><div className="mt-5 flex flex-wrap gap-2">{tutor.specialties.map((specialty) => <span className="rounded-full bg-[#edf4ef] px-3 py-1 text-xs" key={specialty}>{specialty}</span>)}</div><p className="mt-6 whitespace-pre-line leading-7 text-[#536963]">{tutor.bio}</p><div className="mt-6 flex flex-wrap gap-5 text-sm text-[#536963]"><span><Star className="mr-1 inline h-4 w-4 fill-amber-400 text-amber-400" /> {tutor.rating_avg.toFixed(2)} ({tutor.rating_count})</span><span><ShieldCheck className="mr-1 inline h-4 w-4 text-[#0e6f68]" /> Verified tutor</span>{tutor.has_inverter_backup && <span><Zap className="mr-1 inline h-4 w-4 text-[#0e6f68]" /> Power backup</span>}</div></article></section><aside className="rounded-2xl bg-white p-6 shadow-sm"><h2 className="text-2xl font-semibold text-[#0E2421]">Choose a lesson time</h2><p className="mt-2 text-sm text-[#536963]">Live availability is shown in your local timezone.</p><InlineSlotMatrix tutorId={tutor.id} tutorName={tutor.full_name} /></aside></div><div className="mt-8 flex items-center gap-2 text-sm text-[#536963]"><CheckCircle2 className="h-4 w-4 text-[#0e6f68]" /> Secure reservation; payment happens after the slot is held.</div></main>;
}
