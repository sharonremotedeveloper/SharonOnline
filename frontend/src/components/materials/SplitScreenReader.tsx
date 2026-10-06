"use client";

import { useState } from "react";
import { MaterialDetail } from "@/types/material";
import { CefrLevelBadge } from "./CefrLevelBadge";
import { BookOpen, MessageSquare, Volume2, Type } from "lucide-react";

interface SplitScreenReaderProps {
  material: MaterialDetail;
  className?: string;
}

export function SplitScreenReader({ material, className = "" }: SplitScreenReaderProps) {
  const [activeTab, setActiveTab] = useState<"article" | "vocab" | "questions">("article");
  const [fontSize, setFontSize] = useState<"sm" | "base" | "lg">("base");

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
          onClick={() => setActiveTab("article")}
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
          onClick={() => setActiveTab("vocab")}
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
          onClick={() => setActiveTab("questions")}
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
            {material.vocabulary?.map((v) => (
              <div key={v.id} className="p-3 rounded-xl bg-cream-surface border border-cream-deep space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-ink font-serif">{v.word}</span>
                  <span className="text-sm text-cocoa font-semibold">
                    {v.phonetic} · {v.part_of_speech}
                  </span>
                </div>
                <p className="text-sm text-ink leading-relaxed">{v.definition}</p>
                <p className="text-sm text-ink-muted italic">"{v.example_sentence}"</p>
              </div>
            ))}
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
