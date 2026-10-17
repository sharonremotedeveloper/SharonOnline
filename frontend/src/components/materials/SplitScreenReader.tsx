"use client";

import { useState, useEffect, useRef } from "react";
import { MaterialDetail } from "@/types/material";
import { CefrLevelBadge } from "./CefrLevelBadge";
import { BookOpen, MessageSquare, Volume2, Type, Compass, Sparkles } from "lucide-react";

export type ReaderTab = "article" | "vocab" | "questions";

export interface SplitScreenReaderProps {
  material: MaterialDetail;
  className?: string;

  // --- Milestone 3 Controlled Props ---
  activeTab?: ReaderTab;
  onTabChange?: (tab: ReaderTab) => void;
  highlightedVocabIndex?: number | null;
  onHighlightVocab?: (index: number | null) => void;
  followTutor?: boolean;
  onToggleFollowTutor?: (enabled: boolean) => void;
  isTeacher?: boolean;
}

export function SplitScreenReader({
  material,
  className = "",
  activeTab: controlledTab,
  onTabChange,
  highlightedVocabIndex: controlledVocabIndex,
  onHighlightVocab,
  followTutor: controlledFollowTutor,
  onToggleFollowTutor,
  isTeacher = false,
}: SplitScreenReaderProps) {
  // Local fallbacks when rendered uncontrolled
  const [localTab, setLocalTab] = useState<ReaderTab>("article");
  const [localVocabIndex, setLocalVocabIndex] = useState<number | null>(null);
  const [localFollowTutor, setLocalFollowTutor] = useState<boolean>(true);
  const [fontSize, setFontSize] = useState<"sm" | "base" | "lg">("base");

  // Effective values
  const activeTab: ReaderTab = controlledTab !== undefined ? controlledTab : localTab;
  const highlightedVocabIndex: number | null =
    controlledVocabIndex !== undefined ? controlledVocabIndex : localVocabIndex;
  const followTutor: boolean =
    controlledFollowTutor !== undefined ? controlledFollowTutor : localFollowTutor;

  const vocabRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Action Handlers
  const handleTabChange = (tab: ReaderTab) => {
    setLocalTab(tab);
    onTabChange?.(tab);
  };

  const handleVocabClick = (idx: number) => {
    const nextIdx = highlightedVocabIndex === idx ? null : idx;
    setLocalVocabIndex(nextIdx);
    onHighlightVocab?.(nextIdx);
  };

  const handleToggleFollow = () => {
    const nextVal = !followTutor;
    setLocalFollowTutor(nextVal);
    onToggleFollowTutor?.(nextVal);
  };

  // Auto-scroll to active vocabulary card (headless/SSR safe)
  useEffect(() => {
    if (activeTab === "vocab" && highlightedVocabIndex !== null && highlightedVocabIndex !== undefined) {
      const cardEl = vocabRefs.current[highlightedVocabIndex];
      if (cardEl && typeof cardEl.scrollIntoView === "function") {
        cardEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  }, [activeTab, highlightedVocabIndex]);

  const fontClass = {
    sm: "text-sm leading-relaxed",
    base: "text-sm leading-relaxed",
    lg: "text-base leading-relaxed",
  }[fontSize];

  return (
    <div className={`bg-white rounded-3xl border border-divider shadow-card flex flex-col h-full overflow-hidden ${className}`}>
      {/* Header bar */}
      <div className="p-4 bg-cream-surface border-b border-divider flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 truncate">
          <CefrLevelBadge level={material.cefr_level} size="sm" />
          <h3 className="text-sm font-bold text-ink truncate font-serif">{material.title}</h3>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Teacher Broadcast Indicator */}
          {isTeacher && (
            <div className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-cocoa/10 text-cocoa text-xs font-bold border border-cocoa/20">
              <span className="w-2 h-2 rounded-full bg-cocoa animate-pulse" />
              <span>Broadcasting</span>
            </div>
          )}

          {/* Student "Follow Tutor" Toggle Badge */}
          {!isTeacher && (
            <button
              type="button"
              onClick={handleToggleFollow}
              aria-pressed={followTutor}
              aria-label={followTutor ? "Tutor sync active. Click to browse independently." : "Independent browsing. Click to follow tutor."}
              className={`min-h-9 px-3 py-1 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 shadow-2xs ${
                followTutor
                  ? "bg-cocoa text-white hover:bg-cocoa-hover border border-cocoa shadow-xs"
                  : "bg-white text-ink-muted hover:text-ink border border-divider hover:bg-cream-surface"
              }`}
              title={
                followTutor
                  ? "Tutor view synchronization active (Click to browse independently)"
                  : "Independent reading mode (Click to snap back to tutor)"
              }
            >
              <Compass className={`w-3.5 h-3.5 ${followTutor ? "text-amber-300" : "text-ink-muted"}`} />
              <span>{followTutor ? "Follow Tutor: ON" : "Follow Tutor: OFF"}</span>
            </button>
          )}

          {/* Font Resizing */}
          <div className="flex items-center bg-white rounded-xl border border-divider p-0.5">
            <button
              onClick={() => setFontSize(fontSize === "lg" ? "base" : "sm")}
              title="Decrease font"
              className="px-2 py-0.5 text-sm font-bold text-ink-muted hover:text-ink"
            >
              A-
            </button>
            <button
              onClick={() => setFontSize(fontSize === "sm" ? "base" : "lg")}
              title="Increase font"
              className="px-2 py-0.5 text-sm font-bold text-ink hover:text-cocoa"
            >
              A+
            </button>
          </div>
        </div>
      </div>

      {/* Tabs bar */}
      <div className="flex border-b border-divider bg-white text-sm font-bold">
        <button
          onClick={() => handleTabChange("article")}
          className={`flex-1 py-2.5 text-center transition-colors flex items-center justify-center gap-1.5 ${
            activeTab === "article"
              ? "text-cocoa border-b-2 border-cocoa bg-cream-surface/40"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span>Article</span>
        </button>

        <button
          onClick={() => handleTabChange("vocab")}
          className={`flex-1 py-2.5 text-center transition-colors flex items-center justify-center gap-1.5 ${
            activeTab === "vocab"
              ? "text-cocoa border-b-2 border-cocoa bg-cream-surface/40"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          <Type className="w-3.5 h-3.5" />
          <span>Vocabulary ({material.vocabulary?.length || 0})</span>
        </button>

        <button
          onClick={() => handleTabChange("questions")}
          className={`flex-1 py-2.5 text-center transition-colors flex items-center justify-center gap-1.5 ${
            activeTab === "questions"
              ? "text-cocoa border-b-2 border-cocoa bg-cream-surface/40"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          <span>Questions ({material.discussion_questions?.length || 0})</span>
        </button>
      </div>

      {/* Body content scroll area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {activeTab === "article" && (
          <div className="space-y-4 font-serif text-ink">
            <p className="text-sm text-ink-muted font-sans italic border-l-2 border-cocoa pl-3">
              {material.summary}
            </p>

            <div
              className={`prose prose-stone max-w-none ${fontClass}`}
              dangerouslySetInnerHTML={{ __html: material.content_html }}
            />
          </div>
        )}

        {activeTab === "vocab" && (
          <div className="space-y-3">
            {material.vocabulary?.map((v, idx) => {
              const isHighlighted = highlightedVocabIndex === idx;
              return (
                <div
                  key={v.id || idx}
                  ref={(el) => { vocabRefs.current[idx] = el; }}
                  onClick={() => handleVocabClick(idx)}
                  className={`p-3.5 rounded-2xl border transition-all cursor-pointer select-none space-y-1.5 ${
                    isHighlighted
                      ? "bg-amber-50/80 border-cocoa ring-2 ring-cocoa/30 shadow-xs"
                      : "bg-cream-surface border-cream-deep hover:border-cocoa/40"
                  }`}
                >
                  {isHighlighted && (
                    <div className="flex items-center gap-1.5 text-xs font-bold text-cocoa">
                      <Sparkles className="w-3.5 h-3.5 text-cocoa animate-pulse" />
                      <span>Active Vocabulary Focus</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-ink font-serif">{v.word}</span>
                    <span className="text-sm text-cocoa font-semibold">
                      {v.phonetic} · {v.part_of_speech}
                    </span>
                  </div>
                  <p className="text-sm text-ink leading-relaxed">{v.definition}</p>
                  <p className="text-sm text-ink-muted italic">&ldquo;{v.example_sentence}&rdquo;</p>
                </div>
              );
            })}
          </div>
        )}

        {activeTab === "questions" && (
          <div className="space-y-3">
            {material.discussion_questions?.map((q, idx) => (
              <div key={idx} className="p-3.5 rounded-xl bg-cream-surface border border-cream-deep flex gap-2.5">
                <span className="w-5 h-5 rounded-full bg-cocoa text-white flex items-center justify-center text-sm font-bold shrink-0 mt-0.5">
                  {idx + 1}
                </span>
                <p className="text-sm font-bold text-ink leading-relaxed">{q}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
