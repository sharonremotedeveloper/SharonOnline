"use client";

import type { PublicTutor } from "@/types/tutor";
import { TutorCard } from "./TutorCard";
import { SearchX } from "lucide-react";

interface TutorGridProps {
  tutors: PublicTutor[];
  loading: boolean;
  onResetFilters?: () => void;
}

export function TutorGrid({ tutors, loading, onResetFilters }: TutorGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3" role="status" aria-label="Loading tutors">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse overflow-hidden rounded-3xl border border-divider bg-white">
            <div className="aspect-[4/5] bg-cream-deep/60" />
            <div className="space-y-3 p-5">
              <div className="h-5 w-3/4 rounded bg-cream-deep/60" />
              <div className="h-4 w-1/2 rounded bg-cream-deep/40" />
              <div className="h-11 w-full rounded-full bg-cream-deep/40" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (tutors.length === 0) {
    return (
      <div className="space-y-4 rounded-3xl border border-divider bg-white p-12 text-center shadow-card">
        <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-sun">
          <SearchX className="h-8 w-8 text-ink" aria-hidden="true" />
        </span>
        <h3 className="font-serif text-2xl font-bold text-ink">No tutors match your search</h3>
        <p className="mx-auto max-w-md text-base text-ink-muted">
          Try a shorter search, or remove a filter to see more tutors.
        </p>
        {onResetFilters && (
          <button
            type="button"
            onClick={onResetFilters}
            className="inline-flex min-h-[48px] items-center rounded-full bg-cocoa px-7 text-base font-bold text-white transition-colors hover:bg-cocoa-hover"
          >
            Clear all filters
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
      {tutors.map((tutor) => (
        <TutorCard key={tutor.id} tutor={tutor} />
      ))}
    </div>
  );
}
