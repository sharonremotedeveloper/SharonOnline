"use client";

import { useState } from "react";
import { Volume2, Bookmark, Check, Sparkles } from "lucide-react";
import { VocabularyItem } from "@/types/material";

interface InteractiveWordTooltipProps {
  vocab: VocabularyItem;
  children?: React.ReactNode;
}

export function InteractiveWordTooltip({ vocab, children }: InteractiveWordTooltipProps) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSpeak = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(vocab.word);
      utterance.lang = "en-US";
      utterance.rate = 0.9;
      window.speechSynthesis.speak(utterance);
    }
  };

  const handleSaveToBank = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="font-bold text-teal underline decoration-teal/40 decoration-2 underline-offset-4 hover:decoration-teal hover:bg-teal/10 px-1 rounded transition-colors cursor-pointer"
      >
        {children || vocab.word}
      </button>

      {open && (
        <span
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 p-4 bg-white rounded-2xl border border-divider shadow-card text-left space-y-2 block ring-1 ring-black/5"
          onClick={(e) => e.stopPropagation()}
        >
          <span className="flex items-start justify-between gap-2 border-b border-divider pb-2 block">
            <span>
              <span className="text-sm font-extrabold text-ink font-serif block">{vocab.word}</span>
              <span className="text-[11px] text-ink-muted block">
                {vocab.phonetic} · <em className="text-teal">{vocab.part_of_speech}</em>
              </span>
            </span>

            <span className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleSpeak}
                title="Hear Pronunciation"
                className="p-1 rounded-lg bg-cream-surface hover:bg-cream-deep text-ink-muted hover:text-ink transition-colors"
              >
                <Volume2 className="w-3.5 h-3.5" />
              </button>

              <button
                type="button"
                onClick={handleSaveToBank}
                title="Save to My Vocab Bank"
                className={`p-1 rounded-lg transition-colors ${
                  saved
                    ? "bg-success text-white"
                    : "bg-cream-surface hover:bg-cream-deep text-ink-muted hover:text-ink"
                }`}
              >
                {saved ? <Check className="w-3.5 h-3.5" /> : <Bookmark className="w-3.5 h-3.5" />}
              </button>
            </span>
          </span>

          <span className="text-xs text-ink leading-relaxed block">{vocab.definition}</span>

          {vocab.example_sentence && (
            <span className="p-2 rounded-xl bg-cream-surface border border-cream-deep text-[11px] text-ink-muted italic leading-snug block">
              "{vocab.example_sentence}"
            </span>
          )}

          {saved && (
            <span className="text-[10px] font-bold text-success flex items-center gap-1 block">
              <Sparkles className="w-3 h-3" /> Saved to Student Study Bank
            </span>
          )}
        </span>
      )}
    </span>
  );
}
