"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { TutorFilters } from "@/components/tutors/TutorFilters";
import { TutorGrid } from "@/components/tutors/TutorGrid";
import type { PublicTutor, TutorFilterState } from "@/types/tutor";
import { api } from "@/lib/api";
import { buildTutorQuery, toPublicTutor } from "@/lib/tutorsDirectory";
import { errorMessage } from "@/lib/http";
const EMPTY: TutorFilterState = { search: "", accent: "", specialty: "", learning_goal: "", only_power_guard: false, only_today: false };
function TutorsContent() {
  const params = useSearchParams(); const [filters, setFilters] = useState<TutorFilterState>({ ...EMPTY, search: params.get("search") || "", accent: params.get("accent") || "", specialty: params.get("specialty") || "" });
  const [tutors, setTutors] = useState<PublicTutor[]>([]); const [page, setPage] = useState(1); const [count, setCount] = useState(0); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  useEffect(() => { setPage(1); }, [filters.search, filters.accent, filters.specialty]);
  useEffect(() => { let active = true; setLoading(true); setError(""); void api.getTeachers(Object.fromEntries(new URLSearchParams(buildTutorQuery({ ...filters, page, pageSize: 12 }))))
    .then((data) => { if (!active) return; const rows = Array.isArray(data) ? data : data?.results || []; setTutors(rows.map((row: Record<string, unknown>) => toPublicTutor(row))); setCount(Number(data?.count ?? rows.length)); })
    .catch((err) => { if (active) { setTutors([]); setCount(0); setError(errorMessage(err, "Tutors could not be loaded.")); } }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [filters, page]);
  const reset = () => { setFilters(EMPTY); setPage(1); };
  return <main className="min-h-screen bg-[#f7f8f5] px-5 py-12"><div className="mx-auto max-w-7xl"><p className="text-sm font-semibold uppercase tracking-[.18em] text-[#657a73]">Find your tutor</p><h1 className="mt-3 font-['Lora'] text-5xl text-[#0E2421]">Learn with someone who gets you.</h1><p className="mt-4 max-w-2xl text-[#536963]">Search the live tutor directory by name, specialty, and accent.</p><div className="mt-8"><TutorFilters filters={filters} onFilterChange={setFilters} totalCount={count} /></div>{error && <p className="mt-5 rounded-lg bg-amber-50 p-4 text-amber-900">{error}</p>}<div className="mt-8"><TutorGrid tutors={tutors} loading={loading} onResetFilters={reset} /></div>{!loading && count > 12 && <div className="mt-8 flex items-center justify-center gap-4"><button className="rounded-lg border px-4 py-2" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} of {Math.ceil(count / 12)}</span><button className="rounded-lg border px-4 py-2" disabled={page >= Math.ceil(count / 12)} onClick={() => setPage(page + 1)}>Next</button></div>}</div></main>;
}
export default function TutorsPage() { return <Suspense fallback={<main className="p-12">Loading tutors…</main>}><TutorsContent /></Suspense>; }
