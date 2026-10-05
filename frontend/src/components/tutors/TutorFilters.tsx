"use client";

import { useState, useEffect } from "react";
import { Search, Filter, RotateCcw, Zap, Calendar, DollarSign } from "lucide-react";
import { TutorFilterState } from "@/types/tutor";

interface TutorFiltersProps {
  filters: TutorFilterState;
  onFilterChange: (newFilters: TutorFilterState) => void;
  totalCount: number;
}

const ACCENT_OPTIONS = [
  { value: "", label: "All Accents" },
  { value: "ZA", label: "🇿🇦 South African (Native)" },
  { value: "UK", label: "🇬🇧 British (RP / London)" },
  { value: "US", label: "🇺🇸 American (General)" },
  { value: "OTHER", label: "🌐 International Native" },
];

const SPECIALTY_OPTIONS = [
  "All Focus Areas",
  "Business English",
  "Interview Prep",
  "FreeTalk",
  "Daily News",
  "IELTS Prep",
  "Grammar Mastery",
  "Pronunciation & Accent",
];

export function TutorFilters({ filters, onFilterChange, totalCount }: TutorFiltersProps) {
  const [searchTerm, setSearchTerm] = useState(filters.search);

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
    onFilterChange({
      search: "",
      accent: "",
      specialty: "",
      learning_goal: "",
      only_power_guard: false,
      only_today: false,
    });
  };

  const hasActiveFilters =
    filters.search ||
    filters.accent ||
    filters.specialty ||
    filters.learning_goal ||
    filters.only_power_guard ||
    filters.only_today;

  return (
    <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-6">
      {/* Search Bar & Reset Header */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="relative w-full">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search tutors by name, keyword, accent, or specialty..."
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-divider text-xs text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-teal"
          />
        </div>

        {hasActiveFilters && (
          <button
            onClick={handleReset}
            className="text-xs font-bold text-primary hover:text-primary-hover flex items-center gap-1 shrink-0"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Filters</span>
          </button>
        )}
      </div>

      {/* Accent Filters */}
      <div className="space-y-2">
        <label className="text-[11px] font-bold text-ink-muted uppercase tracking-wider flex items-center gap-1.5">
          <Filter className="w-3.5 h-3.5 text-teal" /> Accent & Origin
        </label>
        <div className="flex flex-wrap gap-2">
          {ACCENT_OPTIONS.map((opt) => {
            const isActive = filters.accent === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => onFilterChange({ ...filters, accent: opt.value })}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                  isActive
                    ? "bg-teal text-white shadow-sm"
                    : "bg-cream-surface text-ink-muted hover:bg-cream-deep hover:text-ink border border-divider"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Specialty Filter */}
      <div className="space-y-2">
        <label className="text-[11px] font-bold text-ink-muted uppercase tracking-wider">
          Teaching Specialty
        </label>
        <div className="flex flex-wrap gap-2">
          {SPECIALTY_OPTIONS.map((spec) => {
            const value = spec === "All Focus Areas" ? "" : spec;
            const isActive = filters.specialty === value;
            return (
              <button
                key={spec}
                onClick={() => onFilterChange({ ...filters, specialty: value })}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                  isActive
                    ? "bg-primary text-white shadow-sm font-bold"
                    : "bg-cream-surface text-ink-muted hover:bg-cream-deep hover:text-ink border border-divider"
                }`}
              >
                {spec}
              </button>
            );
          })}
        </div>
      </div>

      {/* Fast Toggles: Power Guard & Today's Availability */}
      <div className="pt-2 border-t border-divider grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label
          className={`flex items-center gap-2.5 p-3 rounded-2xl border cursor-pointer transition-all ${
            filters.only_power_guard
              ? "bg-amber-50/70 border-accent text-ink"
              : "bg-cream-surface border-divider text-ink-muted hover:bg-cream-deep"
          }`}
        >
          <input
            type="checkbox"
            checked={filters.only_power_guard}
            onChange={(e) => onFilterChange({ ...filters, only_power_guard: e.target.checked })}
            className="accent-teal rounded"
          />
          <div className="text-xs font-bold flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-accent" />
            <span>Power Guard Immune (UPS/Solar)</span>
          </div>
        </label>

        <label
          className={`flex items-center gap-2.5 p-3 rounded-2xl border cursor-pointer transition-all ${
            filters.only_today
              ? "bg-teal-surface border-teal text-teal"
              : "bg-cream-surface border-divider text-ink-muted hover:bg-cream-deep"
          }`}
        >
          <input
            type="checkbox"
            checked={filters.only_today}
            onChange={(e) => onFilterChange({ ...filters, only_today: e.target.checked })}
            className="accent-teal rounded"
          />
          <div className="text-xs font-bold flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5" />
            <span>Available Next 24 Hours</span>
          </div>
        </label>
      </div>

      {/* Result Count Status */}
      <div className="pt-2 text-xs text-ink-muted font-medium flex items-center justify-between">
        <span>Showing <strong className="text-ink">{totalCount}</strong> verified tutors</span>
        <span className="text-[11px] text-ink-faint">25-min discrete slots</span>
      </div>
    </div>
  );
}
