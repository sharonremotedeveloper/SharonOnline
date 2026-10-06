"use client";

import Link from "next/link";
import { Heart, Search } from "lucide-react";

export default function StudentFavoritesPage() {
  return <main className="min-h-screen bg-cream px-4 py-10 sm:px-6 lg:px-8"><div className="mx-auto max-w-5xl space-y-7"><header><p className="text-xs font-bold uppercase tracking-[.18em] text-cocoa">Student workspace</p><h1 className="mt-2 font-serif text-4xl font-black text-ink">Favorite tutors</h1><p className="mt-2 text-sm text-ink-muted">Keep the tutors you want to return to in one place.</p></header><section className="rounded-3xl border border-divider bg-white p-10 text-center shadow-card"><Heart className="mx-auto h-10 w-10 text-cocoa" /><h2 className="mt-4 font-serif text-2xl font-black text-ink">Your favorites will appear here</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-ink-muted">Tutor bookmarking is waiting for the persistent favorites API contract. You can still browse live availability and book directly from the tutor directory.</p><Link href="/tutors" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-cocoa px-5 py-3 text-sm font-bold text-white"><Search className="h-4 w-4" /> Browse tutors</Link></section></div></main>;
}
