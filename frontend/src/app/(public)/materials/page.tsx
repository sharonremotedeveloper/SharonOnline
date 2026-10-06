"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Search, BookOpen, Clock, ArrowRight, Download, Sparkles, X, MessageSquare } from "lucide-react";
import { api } from "@/lib/api";
import { ErrorState } from "@/components/ui/ErrorState";
import { MaterialDetail } from "@/types/material";
import { CefrLevelBadge } from "@/components/materials/CefrLevelBadge";
import { MaterialCategoryTabs } from "@/components/materials/MaterialCategoryTabs";

const CEFR_LEVELS = ["All Levels", "A1", "A2", "B1", "B2", "C1", "C2"];

export default function MaterialsPage() {
  const [materials, setMaterials] = useState<MaterialDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [cefr, setCefr] = useState("All Levels");

  useEffect(() => {
    let cancelled = false;
    async function loadMaterials() {
      setLoading(true);
      setLoadError(null);
      try {
        const data = await api.getMaterials({
          category: category || undefined,
          cefr: cefr !== "All Levels" ? cefr : undefined,
          search: search.trim() || undefined,
        });
        if (cancelled) return;
        setMaterials(Array.isArray(data) ? data : data?.results || []);
      } catch (err) {
        if (cancelled) return;
        setMaterials([]);
        setLoadError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    const timer = setTimeout(() => {
      loadMaterials();
    }, 200);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [category, cefr, search, reloadTick]);

  const clearFilters = () => {
    setSearch("");
    setCategory("");
    setCefr("All Levels");
  };

  const hasActiveFilters = search.trim() !== "" || category !== "" || cefr !== "All Levels";

  return (
    <div className="min-h-screen bg-cream py-10 sm:py-16">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
        {/* Header Hero */}
        <div className="space-y-4 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-cocoa/10 text-cocoa text-sm font-bold border border-cocoa/20">
            <Sparkles className="w-3.5 h-3.5" />
            <span>CEFR-Aligned ESL Curriculum</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-black text-ink tracking-tight font-serif">
            Curriculum & Materials Library
          </h1>
          <p className="text-base sm:text-lg text-ink-muted leading-relaxed font-sans">
            Structured English lesson plans designed for 25-minute synchronous private sessions. Browse daily news,
            business case studies, interview drills, and conversation starters.
          </p>
        </div>

        {/* Filter Controls Bar */}
        <div className="bg-white p-6 sm:p-8 rounded-3xl shadow-card border border-divider space-y-6">
          {/* Search + Clear bar */}
          <div className="flex flex-col sm:flex-row items-center gap-4">
            <div className="relative flex-1 w-full">
              <Search className="w-4 h-4 text-ink-muted absolute left-4 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search lessons by topic, title, or keywords (e.g. remote work, interview, negotiation)..."
                className="w-full pl-11 pr-10 py-3 bg-cream-surface rounded-2xl border border-divider text-sm sm:text-sm text-ink placeholder:text-ink-muted/60 focus:outline-none focus:ring-2 focus:ring-cocoa/30 focus:border-cocoa transition-all"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-sm font-bold text-ink-muted hover:text-cocoa underline underline-offset-4 shrink-0 transition-colors"
              >
                Reset All Filters
              </button>
            )}
          </div>

          {/* Category Tabs */}
          <div className="space-y-2">
            <span className="text-sm font-bold text-ink-muted uppercase tracking-wider block">Category</span>
            <MaterialCategoryTabs selectedCategory={category} onSelectCategory={setCategory} />
          </div>

          {/* CEFR Level Selector */}
          <div className="space-y-2 pt-2 border-t border-divider">
            <span className="text-sm font-bold text-ink-muted uppercase tracking-wider block">CEFR Proficiency Level</span>
            <div className="flex flex-wrap items-center gap-2">
              {CEFR_LEVELS.map((lvl) => {
                const isActive = cefr === lvl;
                return (
                  <button
                    key={lvl}
                    onClick={() => setCefr(lvl)}
                    className={`px-3.5 py-1.5 rounded-xl text-sm font-bold transition-all ${
                      isActive
                        ? "bg-ink text-white shadow-sm"
                        : "bg-cream-surface text-ink-muted hover:bg-cream-deep hover:text-ink border border-divider"
                    }`}
                  >
                    {lvl}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Catalog Grid */}
        {loading ? (
          <div className="py-24 text-center space-y-4">
            <div className="w-10 h-10 border-4 border-cocoa border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-sm font-bold text-ink-muted">Loading curriculum materials...</p>
          </div>
        ) : loadError ? (
          <ErrorState
            error={loadError}
            title="We couldn't load the curriculum"
            onRetry={() => setReloadTick((t) => t + 1)}
          />
        ) : materials.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-3xl border border-divider p-8 space-y-4">
            <BookOpen className="w-12 h-12 text-ink-muted/50 mx-auto" />
            <h3 className="text-lg font-bold text-ink">No lesson materials found</h3>
            <p className="text-sm text-ink-muted max-w-sm mx-auto">
              We couldn&apos;t find any curriculum matching your criteria. Try adjusting your search keywords or CEFR level.
            </p>
            <button
              onClick={clearFilters}
              className="px-4 py-2 bg-cocoa text-white rounded-xl text-sm font-bold hover:bg-cocoa-hover transition-colors"
            >
              Reset Filters
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8">
            {materials.map((mat) => (
              <div
                key={mat.id}
                className="bg-white rounded-3xl border border-divider shadow-card hover:shadow-card-hover transition-all duration-300 p-6 sm:p-7 flex flex-col justify-between group space-y-5"
              >
                <div className="space-y-4">
                  {/* Badges Bar */}
                  <div className="flex items-center justify-between gap-2">
                    <CefrLevelBadge level={mat.cefr_level} size="sm" />
                    <span className="text-sm font-bold text-ink-muted bg-cream-surface px-2.5 py-1 rounded-full border border-divider">
                      {mat.category_display}
                    </span>
                  </div>

                  {/* Title & Summary */}
                  <div className="space-y-2">
                    <h3 className="text-xl font-extrabold text-ink font-serif leading-snug group-hover:text-cocoa transition-colors">
                      <Link href={`/materials/${mat.slug}`}>{mat.title}</Link>
                    </h3>
                    <p className="text-sm text-ink-muted line-clamp-3 leading-relaxed font-sans">{mat.summary}</p>
                  </div>

                  {/* Meta Details */}
                  <div className="flex items-center gap-4 text-sm font-medium text-ink-muted pt-1">
                    <span className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-cocoa" />
                      {mat.estimated_minutes || 25} mins
                    </span>
                    <span className="flex items-center gap-1.5">
                      <BookOpen className="w-3.5 h-3.5 text-gold-bright" />
                      {mat.vocabulary?.length || 0} Vocab Target
                    </span>
                    {mat.discussion_questions?.length ? (
                      <span className="flex items-center gap-1.5">
                        <MessageSquare className="w-3.5 h-3.5 text-plum" />
                        {mat.discussion_questions.length} Questions
                      </span>
                    ) : null}
                  </div>
                </div>

                {/* Actions Footer */}
                <div className="pt-4 border-t border-divider space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <Link
                      href={`/materials/${mat.slug}`}
                      className="px-4 py-2.5 rounded-xl bg-cream-surface hover:bg-cocoa hover:text-white text-sm font-bold text-ink border border-divider flex items-center gap-1.5 transition-all"
                    >
                      <BookOpen className="w-3.5 h-3.5" />
                      <span>Study Lesson</span>
                      <ArrowRight className="w-3.5 h-3.5 ml-1" />
                    </Link>

                    {mat.pdf_file_url && (
                      <a
                        href={mat.pdf_file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        download
                        title="Download printable worksheet"
                        className="p-2.5 rounded-xl bg-cream-surface hover:bg-cream-deep text-ink-muted hover:text-ink border border-divider transition-colors"
                      >
                        <Download className="w-4 h-4" />
                      </a>
                    )}
                  </div>

                  <div className="pt-1 text-center">
                    <Link
                      href="/tutors"
                      className="text-sm font-bold text-gold-bright hover:text-warning-hover transition-colors inline-flex items-center gap-1"
                    >
                      Practice with a Verified Native Tutor <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
