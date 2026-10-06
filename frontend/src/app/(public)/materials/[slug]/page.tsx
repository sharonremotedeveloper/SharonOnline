"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Download,
  BookOpen,
  Clock,
  Volume2,
  Calendar,
  Sparkles,
  Share2,
  Check,
  Bookmark,
  ChevronRight,
  ExternalLink,
} from "lucide-react";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { ErrorState } from "@/components/ui/ErrorState";
import { MaterialDetail, VocabularyItem } from "@/types/material";
import { CefrLevelBadge } from "@/components/materials/CefrLevelBadge";
import { DiscussionSection } from "@/components/materials/DiscussionSection";
import { InteractiveWordTooltip } from "@/components/materials/InteractiveWordTooltip";

export default function MaterialReaderPage() {
  const params = useParams();
  const router = useRouter();
  const slug = (params?.slug as string) || "";

  const [material, setMaterial] = useState<MaterialDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [fontSize, setFontSize] = useState<"sm" | "base" | "lg">("base");
  const [copied, setCopied] = useState(false);
  const [savedVocabIds, setSavedVocabIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      if (!slug) return;
      setLoading(true);
      setLoadError(null);
      try {
        const item = await api.getMaterialBySlug(slug);
        if (cancelled) return;
        setMaterial(item);
      } catch (err) {
        if (cancelled) return;
        setMaterial(null);
        // A 404 means the lesson doesn't exist (not-found state below); anything else is a load failure.
        if (!(err instanceof ApiError && err.status === 404)) setLoadError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadData();
    return () => {
      cancelled = true;
    };
  }, [slug, reloadTick]);

  const handleShare = () => {
    if (typeof window !== "undefined") {
      navigator.clipboard
        .writeText(window.location.href)
        .then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        })
        .catch(() => setCopied(false));
    }
  };

  const handleSpeakWord = (word: string) => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(word);
      utterance.lang = "en-US";
      utterance.rate = 0.9;
      window.speechSynthesis.speak(utterance);
    }
  };

  const toggleSaveVocab = (id: string) => {
    setSavedVocabIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const fontClass = {
    sm: "text-sm leading-relaxed sm:text-base",
    base: "text-base leading-relaxed sm:text-lg sm:leading-8",
    lg: "text-lg leading-relaxed sm:text-xl sm:leading-9",
  }[fontSize];

  if (loading) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center py-20">
        <div className="text-center space-y-4">
          <div className="w-12 h-12 border-4 border-cocoa border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-bold text-ink-muted">Loading interactive lesson...</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="min-h-screen bg-cream py-20 px-4">
        <ErrorState
          error={loadError}
          title="We couldn't load this lesson"
          onRetry={() => setReloadTick((t) => t + 1)}
        />
      </div>
    );
  }

  if (!material) {
    return (
      <div className="min-h-screen bg-cream py-20">
        <div className="max-w-2xl mx-auto px-4 text-center space-y-6">
          <h1 className="text-2xl font-black text-ink font-serif">Curriculum Material Not Found</h1>
          <p className="text-sm text-ink-muted">
            The requested lesson could not be found or may have been updated.
          </p>
          <Link
            href="/materials"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-cocoa text-white text-sm font-bold hover:bg-cocoa-hover transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> Return to Catalog
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Navigation Breadcrumb Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <nav className="flex items-center gap-2 text-sm font-semibold text-ink-muted">
            <Link href="/materials" className="hover:text-cocoa flex items-center gap-1 transition-colors">
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Materials Library</span>
            </Link>
            <ChevronRight className="w-3 h-3 text-ink-muted/40" />
            <span className="text-ink-muted/80">{material.category_display}</span>
            <ChevronRight className="w-3 h-3 text-ink-muted/40" />
            <span className="text-ink font-bold truncate max-w-[200px] sm:max-w-xs">{material.title}</span>
          </nav>

          <div className="flex items-center gap-2">
            <button
              onClick={handleShare}
              className="px-3 py-1.5 rounded-xl bg-white border border-divider text-sm font-bold text-ink hover:bg-cream-surface transition-colors flex items-center gap-1.5 shadow-sm"
              title="Copy lesson link"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Share2 className="w-3.5 h-3.5" />}
              <span>{copied ? "Link Copied" : "Share"}</span>
            </button>

            {material.pdf_file_url && (
              <a
                href={material.pdf_file_url}
                target="_blank"
                rel="noopener noreferrer"
                download
                className="px-3.5 py-1.5 rounded-xl bg-white border border-divider text-sm font-bold text-cocoa hover:bg-cocoa hover:text-white transition-all flex items-center gap-1.5 shadow-sm"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Worksheet PDF</span>
              </a>
            )}
          </div>
        </div>

        {/* Hero Header Card */}
        <div className="bg-white rounded-3xl p-6 sm:p-10 border border-divider shadow-card space-y-6">
          <div className="flex flex-wrap items-center gap-3">
            <CefrLevelBadge level={material.cefr_level} size="md" />
            <span className="text-sm font-bold text-ink-muted bg-cream-surface px-3 py-1 rounded-full border border-divider">
              {material.category_display}
            </span>
            <span className="text-sm font-medium text-ink-muted flex items-center gap-1 ml-auto">
              <Clock className="w-3.5 h-3.5 text-cocoa" />
              Estimated {material.estimated_minutes || 25} minutes
            </span>
          </div>

          <h1 className="text-2xl sm:text-4xl lg:text-5xl font-black text-ink font-serif tracking-tight leading-tight">
            {material.title}
          </h1>

          <p className="text-sm sm:text-base text-ink-muted leading-relaxed font-sans italic border-l-4 border-cocoa pl-4 bg-cream-surface/50 py-3 rounded-r-2xl">
            {material.summary}
          </p>
        </div>

        {/* Main Content Layout: Article + Sidebar */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Main Column (8 cols): Typography Controls + Article + Discussion */}
          <div className="lg:col-span-8 space-y-8">
            {/* Interactive Article Card */}
            <div className="bg-white rounded-3xl p-6 sm:p-10 border border-divider shadow-card space-y-6">
              {/* Reader Controls Toolbar */}
              <div className="flex items-center justify-between border-b border-divider pb-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-ink uppercase tracking-wider">Lesson Reading</span>
                  <span className="text-sm text-cocoa font-semibold hidden sm:inline">
                    (Click highlighted words for definitions & audio)
                  </span>
                </div>

                <div className="flex items-center gap-1.5 bg-cream-surface rounded-xl border border-divider p-1">
                  <span className="text-sm font-bold text-ink-muted px-1.5">Text Size:</span>
                  <button
                    onClick={() => setFontSize("sm")}
                    className={`px-2 py-0.5 text-sm font-bold rounded-lg transition-colors ${
                      fontSize === "sm" ? "bg-white text-cocoa shadow-xs" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    A-
                  </button>
                  <button
                    onClick={() => setFontSize("base")}
                    className={`px-2 py-0.5 text-sm font-bold rounded-lg transition-colors ${
                      fontSize === "base" ? "bg-white text-cocoa shadow-xs" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    A
                  </button>
                  <button
                    onClick={() => setFontSize("lg")}
                    className={`px-2 py-0.5 text-sm font-bold rounded-lg transition-colors ${
                      fontSize === "lg" ? "bg-white text-cocoa shadow-xs" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    A+
                  </button>
                </div>
              </div>

              {/* Article Content with Typography */}
              <div
                className={`prose prose-stone max-w-none text-ink font-serif ${fontClass} leading-relaxed space-y-4`}
                dangerouslySetInnerHTML={{ __html: material.content_html }}
              />

              {/* Interactive Vocabulary Inline Pills */}
              {material.vocabulary && material.vocabulary.length > 0 && (
                <div className="pt-6 border-t border-divider space-y-3">
                  <span className="text-sm font-bold text-ink-muted uppercase tracking-wider block">
                    Key Vocabulary In This Article
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {material.vocabulary.map((item) => (
                      <InteractiveWordTooltip key={item.id} vocab={item}>
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cocoa/10 hover:bg-cocoa/20 text-cocoa text-sm font-bold border border-cocoa/20 transition-colors">
                          <BookOpen className="w-3 h-3" />
                          <span>{item.word}</span>
                          <span className="text-sm text-cocoa/70 font-normal">({item.part_of_speech})</span>
                        </span>
                      </InteractiveWordTooltip>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Discussion & Debate Section */}
            <DiscussionSection questions={material.discussion_questions} />
          </div>

          {/* Sidebar Column (4 cols): Vocabulary Bank + Live Booking CTA */}
          <div className="lg:col-span-4 space-y-6">
            {/* Live Lesson Booking Callout */}
            <div className="bg-gradient-to-br from-ink to-ink-muted text-white rounded-3xl p-6 sm:p-7 shadow-card space-y-5">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/20 text-gold-bright text-sm font-bold border border-accent/30">
                <Sparkles className="w-3.5 h-3.5" />
                <span>1-on-1 Practice</span>
              </div>

              <div className="space-y-2">
                <h3 className="text-xl font-bold font-serif leading-snug">
                  Practice this material live with Sharon
                </h3>
                <p className="text-sm text-cream/80 leading-relaxed font-sans">
                  Book a 25-minute synchronous Zoom lesson. Get real-time pronunciation corrections and natural
                  conversation feedback.
                </p>
              </div>

              <div className="pt-2">
                <Link
                  href="/tutors"
                  className="w-full py-3 px-4 rounded-2xl bg-accent hover:bg-warning text-ink font-extrabold text-sm flex items-center justify-center gap-2 transition-all shadow-md"
                >
                  <Calendar className="w-4 h-4" />
                  <span>Choose Date & Book Session</span>
                </Link>
              </div>
            </div>

            {/* Target Vocabulary Bank */}
            <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-4">
              <div className="flex items-center justify-between border-b border-divider pb-3">
                <h3 className="text-sm font-extrabold text-ink font-serif flex items-center gap-2">
                  <BookOpen className="w-4 h-4 text-cocoa" />
                  <span>Target Vocabulary ({material.vocabulary?.length || 0})</span>
                </h3>
                <span className="text-sm text-ink-muted">Audio guides</span>
              </div>

              <div className="space-y-3 max-h-[550px] overflow-y-auto pr-1">
                {material.vocabulary?.map((vocab) => {
                  const isSaved = savedVocabIds.has(vocab.id);
                  return (
                    <div
                      key={vocab.id}
                      className="p-4 rounded-2xl bg-cream-surface border border-cream-deep space-y-2 hover:border-cocoa/40 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-sm font-extrabold text-ink font-serif block">
                            {vocab.word}
                          </span>
                          <span className="text-sm text-ink-muted">
                            {vocab.phonetic} · <em className="text-cocoa font-medium">{vocab.part_of_speech}</em>
                          </span>
                        </div>

                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => handleSpeakWord(vocab.word)}
                            title="Hear pronunciation"
                            className="p-1.5 rounded-lg bg-white hover:bg-cream-deep text-ink-muted hover:text-ink transition-colors border border-divider"
                          >
                            <Volume2 className="w-3.5 h-3.5" />
                          </button>

                          <button
                            type="button"
                            onClick={() => toggleSaveVocab(vocab.id)}
                            title={isSaved ? "Saved to your list" : "Save vocabulary"}
                            className={`p-1.5 rounded-lg transition-colors border ${
                              isSaved
                                ? "bg-success text-white border-success"
                                : "bg-white hover:bg-cream-deep text-ink-muted hover:text-ink border-divider"
                            }`}
                          >
                            {isSaved ? <Check className="w-3.5 h-3.5" /> : <Bookmark className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                      </div>

                      <p className="text-sm text-ink leading-relaxed">{vocab.definition}</p>

                      {vocab.example_sentence && (
                        <p className="p-2.5 rounded-xl bg-white border border-divider text-sm text-ink-muted italic leading-snug">
                          &ldquo;{vocab.example_sentence}&rdquo;
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Cloudflare R2 Download Card */}
            {material.pdf_file_url && (
              <div className="p-5 rounded-3xl bg-white border border-divider shadow-card space-y-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-2xl bg-cocoa/10 text-cocoa flex items-center justify-center shrink-0">
                    <Download className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-ink">Printable PDF Worksheet</h4>
                    <p className="text-sm text-ink-muted">High-res offline study handout</p>
                  </div>
                </div>

                <a
                  href={material.pdf_file_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  download
                  className="w-full py-2.5 px-4 rounded-xl bg-cream-surface hover:bg-cream-deep border border-divider text-ink text-sm font-bold flex items-center justify-center gap-2 transition-colors"
                >
                  <ExternalLink className="w-3.5 h-3.5 text-cocoa" />
                  <span>Download R2 Worksheet</span>
                </a>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
