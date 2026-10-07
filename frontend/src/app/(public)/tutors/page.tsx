"use client";

import { AlertCircle } from "lucide-react";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { TutorFilters } from "@/components/tutors/TutorFilters";
import { TutorGrid } from "@/components/tutors/TutorGrid";
import type { PublicTutor, TutorFilterState } from "@/types/tutor";
import { api } from "@/lib/api";
import { buildTutorQuery, toPublicTutor } from "@/lib/tutorsDirectory";
import { errorMessage } from "@/lib/http";

const PAGE_SIZE = 12;
const EMPTY: TutorFilterState = { search: "", accent: "", specialty: "", learning_goal: "", only_power_guard: false, only_today: false };

function TutorsContent() {
  const params = useSearchParams();
  const [filters, setFilters] = useState<TutorFilterState>({
    ...EMPTY,
    search: params.get("search") || "",
    accent: params.get("accent") || "",
    specialty: params.get("specialty") || "",
  });
  const [tutors, setTutors] = useState<PublicTutor[]>([]);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setPage(1);
  }, [filters.search, filters.accent, filters.specialty]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void api
      .getTeachers(Object.fromEntries(new URLSearchParams(buildTutorQuery({ ...filters, page, pageSize: PAGE_SIZE }))))
      .then((data) => {
        if (!active) return;
        const rows = Array.isArray(data) ? data : data?.results || [];
        setTutors(rows.map((row: Record<string, unknown>) => toPublicTutor(row)));
        setCount(Number(data?.count ?? rows.length));
      })
      .catch((err) => {
        if (!active) return;
        setTutors([]);
        setCount(0);
        setError(errorMessage(err, "Tutors could not be loaded."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters, page]);

  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const pageButton =
    "inline-flex min-h-[48px] items-center rounded-full border border-divider bg-white px-6 text-base font-bold text-ink transition-colors hover:bg-cream-surface disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
      <p className="text-sm font-bold uppercase tracking-wider text-primary">Find your tutor</p>
      <h1 className="mt-2 max-w-3xl font-serif text-4xl font-extrabold leading-tight tracking-tight text-ink sm:text-5xl">
        Learn with someone who gets you.
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-ink-muted">Search by name or topic. Open a tutor to see their free times.</p>

      <div className="mt-8">
        <TutorFilters filters={filters} onFilterChange={setFilters} totalCount={count} />
      </div>

      {error && (
        <p role="alert" className="mt-6 rounded-2xl border border-error/30 bg-error-surface p-4 text-base text-error"><AlertCircle className="mr-2 inline h-4 w-4 shrink-0 align-text-bottom" aria-hidden="true" /><span className="sr-only">Error: </span>
          {error}
        </p>
      )}

      <div className="mt-8">
        <TutorGrid tutors={tutors} loading={loading} onResetFilters={() => setFilters(EMPTY)} />
      </div>

      {!loading && count > PAGE_SIZE && (
        <nav aria-label="Tutor pages" className="mt-10 flex items-center justify-center gap-4">
          <button type="button" className={pageButton} disabled={page === 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span className="text-base text-ink-muted">
            Page {page} of {pages}
          </span>
          <button type="button" className={pageButton} disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </nav>
      )}
    </div>
  );
}

export default function TutorsPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-7xl px-4 py-14" role="status">Loading tutors…</div>}>
      <TutorsContent />
    </Suspense>
  );
}
