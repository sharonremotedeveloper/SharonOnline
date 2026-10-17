"use client";

import { useState, useEffect } from "react";
import { Search, RotateCcw, Zap, Calendar, SlidersHorizontal, ChevronDown } from "lucide-react";
import type { TutorFilterState } from "@/types/tutor";

interface TutorFiltersProps {
  filters: TutorFilterState;
  onFilterChange: (newFilters: TutorFilterState) => void;
  totalCount: number;
  loading: boolean;
}

// Plain labels: flag emoji render as bare letters ("ZA", "GB") on Windows, so they are not used.
const ACCENT_OPTIONS = [
  { value: "", label: "Any accent" },
  { value: "ZA", label: "South African" },
  { value: "UK", label: "British" },
  { value: "US", label: "American" },
  { value: "OTHER", label: "Other" },
];

const SPECIALTY_OPTIONS = [
  "All topics",
  "Business English",
  "Interview Prep",
  "FreeTalk",
  "Daily News",
  "IELTS Prep",
  "Grammar Mastery",
  "Pronunciation & Accent",
];

const chip = (active: boolean) =>
  `inline-flex min-h-[44px] items-center rounded-full px-4 text-base font-semibold transition-colors ${
    active ? "bg-cocoa text-white" : "border border-divider bg-white text-ink hover:border-cocoa hover:bg-cream-surface"
  }`;

export function TutorFilters({ filters, onFilterChange, totalCount, loading }: TutorFiltersProps) {
  const [searchTerm, setSearchTerm] = useState(filters.search);
  // Phones: the filter groups fold behind one button (they took ~1.5 screens before the first tutor). md+: always open.
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    setSearchTerm(filters.search);
  }, [filters.search]);

  // Debounced search input
  useEffect(() => {
    const handler = setTimeout(() => {
      if (searchTerm !== filters.search) {
        onFilterChange({ ...filters, search: searchTerm });
      }
    }, 300);
    return () => clearTimeout(handler);
  }, [searchTerm, filters, onFilterChange]);

  const handleReset = () => {
    setSearchTerm("");
    onFilterChange({ search: "", accent: "", specialty: "", learning_goal: "", only_power_guard: false, only_today: false });
  };

  const hasActiveFilters =
    filters.search || filters.accent || filters.specialty || filters.learning_goal || filters.only_power_guard || filters.only_today;
  const activeFilterCount = [filters.accent, filters.specialty, filters.learning_goal, filters.only_power_guard, filters.only_today].filter(Boolean).length;

  return (
    <div className="space-y-6 rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full">
          <label htmlFor="tutor-search" className="sr-only">
            Search tutors
          </label>
          <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-muted" aria-hidden="true" />
          <input
            id="tutor-search"
            type="search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by name or topic"
            className="min-h-[52px] w-full rounded-full border border-strong bg-cream-surface pl-12 pr-4 text-base text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-cocoa"
          />
        </div>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={handleReset}
            className="inline-flex min-h-[44px] shrink-0 items-center gap-2 px-2 text-base font-bold text-primary hover:text-primary-hover"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Reset
          </button>
        )}
      </div>

      <button
        type="button"
        aria-expanded={filtersOpen}
        aria-controls="tutor-filter-panel"
        onClick={() => setFiltersOpen((open) => !open)}
        className="flex min-h-[48px] w-full items-center justify-between rounded-2xl border border-divider bg-cream-surface px-4 text-base font-bold text-ink md:hidden"
      >
        <span className="flex items-center gap-2">
          <SlidersHorizontal className="h-5 w-5" aria-hidden="true" />
          Filters
          {activeFilterCount > 0 && (
            <span className="rounded-full bg-cocoa px-2 py-0.5 text-xs font-bold text-white">{activeFilterCount}</span>
          )}
        </span>
        <ChevronDown className={`h-5 w-5 transition-transform ${filtersOpen ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>

      <div id="tutor-filter-panel" className={`space-y-6 ${filtersOpen ? "" : "hidden"} md:block`}>
      <fieldset>
        <legend className="mb-2 text-sm font-bold uppercase tracking-wider text-ink-muted">Accent</legend>
        <div className="flex flex-wrap gap-2">
          {ACCENT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              aria-pressed={filters.accent === opt.value}
              onClick={() => onFilterChange({ ...filters, accent: opt.value })}
              className={chip(filters.accent === opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-sm font-bold uppercase tracking-wider text-ink-muted">Topic</legend>
        <div className="flex flex-wrap gap-2">
          {SPECIALTY_OPTIONS.map((spec) => {
            const value = spec === "All topics" ? "" : spec;
            return (
              <button
                key={spec}
                type="button"
                aria-pressed={filters.specialty === value}
                onClick={() => onFilterChange({ ...filters, specialty: value })}
                className={chip(filters.specialty === value)}
              >
                {spec}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="grid grid-cols-1 gap-3 border-t border-divider pt-5 sm:grid-cols-2">
        <label
          className={`flex min-h-[52px] cursor-pointer items-center gap-3 rounded-2xl border px-4 text-base font-semibold transition-colors ${
            filters.only_power_guard ? "border-cocoa bg-cream-deep text-ink" : "border-divider bg-cream-surface text-ink hover:bg-cream-deep"
          }`}
        >
          <input
            type="checkbox"
            checked={filters.only_power_guard}
            onChange={(e) => onFilterChange({ ...filters, only_power_guard: e.target.checked })}
            className="h-5 w-5 accent-cocoa"
          />
          <Zap className="h-5 w-5" aria-hidden="true" />
          <span>Tutors reporting backup power</span>
        </label>

        <label
          className={`flex min-h-[52px] cursor-pointer items-center gap-3 rounded-2xl border px-4 text-base font-semibold transition-colors ${
            filters.only_today ? "border-cocoa bg-cream-deep text-ink" : "border-divider bg-cream-surface text-ink hover:bg-cream-deep"
          }`}
        >
          <input
            type="checkbox"
            checked={filters.only_today}
            onChange={(e) => onFilterChange({ ...filters, only_today: e.target.checked })}
            className="h-5 w-5 accent-cocoa"
          />
          <Calendar className="h-5 w-5" aria-hidden="true" />
          <span>Free in the next 24 hours</span>
        </label>
      </div>
      </div>

      <p className="text-base text-ink-muted" aria-live="polite">
        {loading ? <>Updating tutors…</> : <>Showing <strong className="text-ink">{totalCount}</strong> {totalCount === 1 ? "tutor" : "tutors"}</>}
      </p>
    </div>
  );
}
