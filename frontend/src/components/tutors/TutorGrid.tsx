"use client";

import { PublicTutor } from "@/types/tutor";
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
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-4 animate-pulse"
          >
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-full bg-cream-deep" />
              <div className="space-y-2 flex-1">
                <div className="h-4 bg-cream-deep rounded w-3/4" />
                <div className="h-3 bg-cream-surface rounded w-1/2" />
              </div>
            </div>
            <div className="space-y-2">
              <div className="h-3 bg-cream-surface rounded w-full" />
              <div className="h-3 bg-cream-surface rounded w-5/6" />
            </div>
            <div className="h-8 bg-cream-surface rounded-xl w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (tutors.length === 0) {
    return (
      <div className="bg-white rounded-3xl p-12 text-center border border-divider shadow-card space-y-4">
        <div className="w-16 h-16 rounded-2xl bg-cream-surface text-ink-muted flex items-center justify-center mx-auto">
          <SearchX className="w-8 h-8 text-ink-muted" />
        </div>
        <h3 className="text-xl font-bold text-ink font-serif">No Tutors Matched Your Filters</h3>
        <p className="text-xs text-ink-muted max-w-md mx-auto">
          Try loosening your search terms, selecting "All Accents", or clearing the Power Guard filter.
        </p>
        {onResetFilters && (
          <button
            onClick={onResetFilters}
            className="px-6 py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl shadow-sm transition-all"
          >
            Clear All Filters
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {tutors.map((tutor) => (
        <TutorCard key={tutor.id} tutor={tutor} />
      ))}
    </div>
  );
}
