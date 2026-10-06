"use client";

import { useState } from "react";
import { Send, Plus, X, Sparkles, CheckCircle2, BookOpen, Volume2, Award, FileText } from "lucide-react";
import { InlineError } from "@/components/ui/ErrorState";
import { api } from "@/lib/api";
import { PostLessonMemoInput, VocabularyTagItem } from "@/types/teacher";

interface MemoComposerProps {
  bookingId: string;
  studentName: string;
  lessonTitle?: string;
  initialScratchpad?: string;
  onSubmitted?: () => void;
}

export function MemoComposer({
  bookingId,
  studentName,
  lessonTitle = "No material linked",
  initialScratchpad = "",
  onSubmitted,
}: MemoComposerProps) {
  const [feedbackText, setFeedbackText] = useState(
    initialScratchpad ? `Notes from lesson:
${initialScratchpad}` : ""
  );

  const [vocabList, setVocabList] = useState<VocabularyTagItem[]>([]);

  const [newWord, setNewWord] = useState("");
  const [newDef, setNewDef] = useState("");

  const [pronunciationNotes, setPronunciationNotes] = useState("");

  const [grammarNotes, setGrammarNotes] = useState("");

  const [homework, setHomework] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const addVocabWord = () => {
    if (!newWord.trim()) return;
    const item: VocabularyTagItem = {
      id: `v-${Date.now()}`,
      word: newWord.trim(),
      definition: newDef.trim(),
    };
    setVocabList([...vocabList, item]);
    setNewWord("");
    setNewDef("");
  };

  const removeVocabWord = (id: string) => {
    setVocabList(vocabList.filter((v) => v.id !== id));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!feedbackText.trim()) {
      setError("Please provide overall feedback for the student.");
      return;
    }

    setSubmitting(true);
    setError(null);

    const payload: PostLessonMemoInput = {
      booking_id: bookingId,
      feedback_text: feedbackText,
      vocabulary_words: vocabList,
      pronunciation_notes: pronunciationNotes,
      grammar_notes: grammarNotes,
      homework,
      next_steps: "",
    };

    try {
      await api.submitLessonMemo(payload);
      setSubmitted(true);
      if (onSubmitted) onSubmitted();
    } catch (err) {
      console.error("Failed to submit memo:", err);
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="bg-white rounded-3xl p-8 border border-divider shadow-card text-center space-y-6">
        <div className="w-16 h-16 rounded-full bg-success-surface text-success-hover flex items-center justify-center mx-auto">
          <CheckCircle2 className="w-8 h-8" />
        </div>

        <div className="space-y-2">
          <h3 className="text-2xl font-black text-ink font-serif">Lesson Memo Published!</h3>
          <p className="text-xs text-ink-muted max-w-md mx-auto leading-relaxed">
            Your detailed evaluation, vocabulary bank, and pronunciation tips have been sent to{" "}
            <strong>{studentName}</strong> and added to their study portal.
          </p>
        </div>

        <div className="p-4 rounded-2xl bg-cream-surface border border-divider max-w-sm mx-auto text-xs space-y-1">
          <span className="font-bold text-ink">Smart Flashcards Activated</span>
          <p className="text-xs text-ink-muted">
            The {vocabList.length} vocabulary words were automatically ingested into the student&apos;s spaced repetition deck.
          </p>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-3xl p-6 sm:p-10 border border-divider shadow-card space-y-8">
      {/* Header */}
      <div className="border-b border-divider pb-6 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold text-cocoa bg-cocoa/10 px-2.5 py-0.5 rounded-full">
            BOOKING: {bookingId}
          </span>
          <span className="text-xs font-bold text-ink-muted">Post-Lesson Memo Studio</span>
        </div>
        <h2 className="text-2xl font-black text-ink font-serif">
          Evaluate Session with {studentName}
        </h2>
        <p className="text-xs text-ink-muted">
          Lesson Material: <span className="font-semibold text-ink">{lessonTitle}</span>
        </p>
      </div>

      <InlineError error={error} />

      {/* 1. Overall Feedback */}
      <div className="space-y-2">
        <label className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-2">
          <Award className="w-4 h-4 text-cocoa" aria-hidden="true" />
          <span>Overall Feedback &amp; Speaking Fluency</span>
        </label>
        <p className="text-xs text-ink-muted">
          Praise strengths, evaluate conversational confidence, and summarize key conversational highlights.
        </p>
        <textarea
          rows={4}
          value={feedbackText}
          onChange={(e) => setFeedbackText(e.target.value)}
          className="w-full p-4 bg-cream-surface rounded-2xl border border-strong text-base sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cocoa/30 focus:border-cocoa leading-relaxed font-sans"
          placeholder="Write thorough feedback for the student..."
          required
        />
      </div>

      {/* 2. Interactive Vocabulary Tag Builder */}
      <div className="space-y-4">
        <label className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-cocoa" />
          <span>Target Vocabulary Words ({vocabList.length})</span>
        </label>
        <p className="text-xs text-ink-muted">
          Add newly introduced or practiced vocabulary. These will convert into spaced-repetition student flashcards.
        </p>

        {/* Existing Vocab Chips */}
        <div className="flex flex-wrap gap-2.5">
          {vocabList.map((item) => (
            <div
              key={item.id}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-cocoa/10 border border-cocoa/20 text-xs font-bold text-cocoa shadow-2xs"
            >
              <span>{item.word}</span>
              <button
                type="button"
                onClick={() => removeVocabWord(item.id)}
                className="hover:text-error transition-colors p-0.5"
                title="Remove word"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        {/* Add Word Row */}
        <div className="flex flex-col sm:flex-row items-center gap-2 pt-1">
          <input
            type="text"
            value={newWord}
            onChange={(e) => setNewWord(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addVocabWord();
              }
            }}
            placeholder="New word (e.g. Asynchronous)..."
            className="min-h-11 w-full sm:w-1/3 p-2.5 bg-cream-surface rounded-xl border border-strong text-base sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cocoa/30"
          />
          <input
            type="text"
            value={newDef}
            onChange={(e) => setNewDef(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addVocabWord();
              }
            }}
            placeholder="Definition or example sentence..."
            className="min-h-11 w-full sm:flex-1 p-2.5 bg-cream-surface rounded-xl border border-strong text-base sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cocoa/30"
          />
          <button
            type="button"
            onClick={addVocabWord}
            className="w-full sm:w-auto px-4 py-2.5 bg-cocoa hover:bg-cocoa-hover text-white text-xs font-bold rounded-xl flex items-center justify-center gap-1.5 transition-colors shrink-0"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Word</span>
          </button>
        </div>
      </div>

      {/* 3. Pronunciation & Phonetics */}
      <div className="space-y-2">
        <label className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-2">
          <Volume2 className="w-4 h-4 text-cocoa" />
          <span>Pronunciation &amp; Accent Notes</span>
        </label>
        <textarea
          rows={3}
          value={pronunciationNotes}
          onChange={(e) => setPronunciationNotes(e.target.value)}
          className="w-full p-4 bg-cream-surface rounded-2xl border border-strong text-base sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cocoa/30 focus:border-cocoa leading-relaxed font-sans"
          placeholder="Phonetic symbols, syllable stress, or tongue placement tips..."
        />
      </div>

      {/* 4. Grammar Corrections */}
      <div className="space-y-2">
        <label className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-2">
          <FileText className="w-4 h-4 text-plum" />
          <span>Grammar Slips &amp; Corrections</span>
        </label>
        <textarea
          rows={3}
          value={grammarNotes}
          onChange={(e) => setGrammarNotes(e.target.value)}
          className="w-full p-4 bg-cream-surface rounded-2xl border border-strong text-base sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cocoa/30 focus:border-cocoa leading-relaxed font-sans"
          placeholder="Write 'Student said' vs 'More natural native phrasing'..."
        />
      </div>

      {/* 5. Homework & Follow-up */}
      <div className="space-y-2">
        <label className="text-xs font-bold text-ink uppercase tracking-wider flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-cocoa" aria-hidden="true" />
          <span>Homework Assignment &amp; Next Session Objectives</span>
        </label>
        <textarea
          rows={2}
          value={homework}
          onChange={(e) => setHomework(e.target.value)}
          className="w-full p-4 bg-cream-surface rounded-2xl border border-strong text-base sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-cocoa/30 focus:border-cocoa leading-relaxed font-sans"
          placeholder="Recommended reading or speaking drills for next class..."
        />
      </div>

      {/* Submit Action Bar */}
      <div className="pt-4 border-t border-divider flex items-center justify-end gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="px-8 py-3.5 bg-cocoa hover:bg-cocoa-hover text-white text-xs font-black rounded-2xl flex items-center gap-2 shadow-md transition-all hover:scale-[1.01]"
        >
          <Send className="w-4 h-4" />
          <span>{submitting ? "Publishing Memo..." : "Submit Memo & Send to Student"}</span>
        </button>
      </div>
    </form>
  );
}
