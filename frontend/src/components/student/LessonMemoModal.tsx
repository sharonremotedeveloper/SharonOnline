"use client";

import { useState } from "react";
import {
  X,
  BookOpen,
  Award,
  Volume2,
  FileText,
  CheckCircle2,
  BookmarkCheck,
  Share2,
  Printer,
  Sparkles,
} from "lucide-react";
import { StudentLessonItem } from "@/types/student";

interface LessonMemoModalProps {
  lesson: StudentLessonItem;
  isOpen: boolean;
  onClose: () => void;
}

export function LessonMemoModal({ lesson, isOpen, onClose }: LessonMemoModalProps) {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !lesson.memo) return null;

  const memo = lesson.memo;

  const handleCopyNotes = () => {
    const text = `Lesson: ${lesson.material_title} (${lesson.material_cefr})
Tutor: ${lesson.teacher.name}
Date: ${lesson.local_date}

TUTOR FEEDBACK:
${memo.feedback_text}

VOCABULARY:
${memo.vocabulary_words.map((v) => `• ${v.word}: ${v.definition}`).join("\n")}

PRONUNCIATION:
${memo.pronunciation_notes}

GRAMMAR CORRECTIONS:
${memo.grammar_notes}

HOMEWORK:
${memo.homework}
`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in overflow-y-auto">
      <div className="relative w-full max-w-2xl bg-white rounded-3xl border border-cream-200 shadow-2xl overflow-hidden my-8 animate-scale-up">
        {/* Header */}
        <div className="bg-gradient-to-r from-cocoa-900 via-cocoa-800 to-ink-900 text-white p-6 sm:p-8">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <img
                src={lesson.teacher.avatar}
                alt={lesson.teacher.name}
                className="w-12 h-12 rounded-full border-2 border-cocoa-400 object-cover"
              />
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-lg text-white">{lesson.teacher.name}</h3>
                  <span className="text-sm bg-cocoa-700/60 text-cocoa-200 px-2 py-0.5 rounded-full border border-cocoa-600/40">
                    Tutor Memo
                  </span>
                </div>
                <p className="text-sm text-cocoa-200">
                  {lesson.local_date} • {lesson.local_start_time} - {lesson.local_end_time} ({lesson.viewer_timezone})
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="min-w-11 justify-center min-h-11 inline-flex items-center p-2 text-cocoa-200 hover:text-white hover:bg-white/10 rounded-full transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="mt-5 pt-4 border-t border-cocoa-700/60 flex items-center justify-between flex-wrap gap-2">
            <div>
              <span className="text-sm font-semibold text-cocoa-300 uppercase tracking-wider">Lesson Material</span>
              <h2 className="text-xl font-bold text-white mt-0.5">{lesson.material_title}</h2>
            </div>
            <span className="px-3 py-1 bg-accent-500/20 text-accent-300 border border-accent-400/30 text-sm font-bold rounded-lg">
              CEFR {lesson.material_cefr}
            </span>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 sm:p-8 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Feedback */}
          <div>
            <div className="flex items-center gap-2 mb-2 text-ink-900 font-bold text-sm uppercase tracking-wider">
              <Sparkles className="w-4 h-4 text-cocoa-600" />
              <span>Tutor Feedback</span>
            </div>
            <div className="bg-cocoa-50/50 border border-cocoa-100 p-4 rounded-2xl text-ink-800 text-sm leading-relaxed">
              {memo.feedback_text}
            </div>
          </div>

          {/* Vocabulary */}
          {memo.vocabulary_words && memo.vocabulary_words.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-ink-900 font-bold text-sm uppercase tracking-wider">
                  <BookOpen className="w-4 h-4 text-cocoa" aria-hidden="true" />
                  <span>Vocabulary Acquired ({memo.vocabulary_words.length})</span>
                </div>
                <span className="text-sm text-ink-500 flex items-center gap-1 font-medium">
                  <BookmarkCheck className="w-3.5 h-3.5 text-cocoa-600" /> Synced to Flashcards
                </span>
              </div>

              <div className="space-y-2.5">
                {memo.vocabulary_words.map((item, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-cream-200 bg-cream-50/50 hover:bg-cream-50 transition-colors flex flex-col sm:flex-row sm:items-baseline justify-between gap-1"
                  >
                    <span className="font-bold text-cocoa-900 font-mono text-sm capitalize">{item.word}</span>
                    <span className="text-sm text-ink-700 sm:text-right">{item.definition}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pronunciation Notes */}
          {memo.pronunciation_notes && (
            <div>
              <div className="flex items-center gap-2 mb-2 text-ink-900 font-bold text-sm uppercase tracking-wider">
                <Volume2 className="w-4 h-4 text-ink-muted" />
                <span>Pronunciation & Phonetics</span>
              </div>
              <div className="bg-sky-soft border border-sky p-4 rounded-2xl text-ink-800 text-sm leading-relaxed">
                {memo.pronunciation_notes}
              </div>
            </div>
          )}

          {/* Grammar Corrections */}
          {memo.grammar_notes && (
            <div>
              <div className="flex items-center gap-2 mb-2 text-ink-900 font-bold text-sm uppercase tracking-wider">
                <Award className="w-4 h-4 text-warning" />
                <span>Grammar & Nuances</span>
              </div>
              <div className="bg-warning-surface/50 border border-warning-surface p-4 rounded-2xl text-ink-800 text-sm leading-relaxed">
                {memo.grammar_notes}
              </div>
            </div>
          )}

          {/* Homework Assignment */}
          {memo.homework && (
            <div>
              <div className="flex items-center gap-2 mb-2 text-ink-900 font-bold text-sm uppercase tracking-wider">
                <FileText className="w-4 h-4 text-info" />
                <span>Next Lesson Prep / Homework</span>
              </div>
              <div className="bg-info-surface/50 border border-info-surface p-4 rounded-2xl text-ink-800 text-sm leading-relaxed">
                {memo.homework}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 sm:p-6 bg-cream-50 border-t border-cream-200 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyNotes}
              className="min-h-11 inline-flex items-center gap-1.5 px-3 py-2 text-sm font-semibold text-ink-700 hover:text-ink-900 bg-white border border-cream-200 rounded-xl transition-colors shadow-xs"
            >
              {copied ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5 text-success" /> Copied!
                </>
              ) : (
                <>
                  <Share2 className="w-3.5 h-3.5" /> Copy Notes
                </>
              )}
            </button>
            <button
              onClick={handlePrint}
              className="min-h-11 inline-flex items-center gap-1.5 px-3 py-2 text-sm font-semibold text-ink-700 hover:text-ink-900 bg-white border border-cream-200 rounded-xl transition-colors shadow-xs"
            >
              <Printer className="w-3.5 h-3.5" /> Print
            </button>
          </div>

          <button
            onClick={onClose}
            className="min-h-11 inline-flex items-center px-5 py-2 bg-ink-900 hover:bg-ink-800 text-white text-sm font-semibold rounded-xl transition-colors shadow-sm"
          >
            Close Memo
          </button>
        </div>
      </div>
    </div>
  );
}
