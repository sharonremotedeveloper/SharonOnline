"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Layers,
  ChevronLeft,
  Volume2,
  Sparkles,
  BookOpen,
  Search,
  CheckCircle2,
  Clock,
  HelpCircle,
} from "lucide-react";
import { studentApi } from "@/lib/api";
import { StudentFlashcard } from "@/types/student";
import { FlashcardDeck } from "@/components/student/FlashcardDeck";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";
import { errorMessage } from "@/lib/http";

export default function StudentVocabularyPage() {
  const { data, error, loading: isLoading, reload } = useApiData<StudentFlashcard[]>(
    () => studentApi.getStudentFlashcards(),
    []
  );
  const cards = data ?? [];
  const [gradeError, setGradeError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"flashcards" | "wordbank">("flashcards");

  const handleGradeCard = async (cardId: string, grade: "again" | "good" | "easy") => {
    setGradeError(null);
    try {
      await studentApi.updateFlashcardMastery(cardId, grade);
    } catch (err) {
      console.error("Failed to update mastery:", err);
      setGradeError(`Your last rating was not saved, so this card's schedule has not changed. ${errorMessage(err)}`);
    }
  };

  const filteredCards = cards.filter((card) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return card.word.toLowerCase().includes(q) || card.definition.toLowerCase().includes(q);
  });

  const speakWord = (word: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(word);
    utterance.lang = "en-US";
    utterance.rate = 0.85;
    window.speechSynthesis.speak(utterance);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Link
              href="/student/dashboard"
              className="p-1.5 text-ink-400 hover:text-ink-900 hover:bg-cream-100 rounded-xl transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-ink-900 tracking-tight">
              Spaced Repetition Flashcards
            </h1>
          </div>
          <p className="text-sm sm:text-sm text-ink-600 mt-1 pl-8">
            Review vocabulary acquired in your lessons using Sharon Online&apos;s adaptive SRS recall engine.
          </p>
        </div>

        {/* Tab switch between deck and word bank */}
        <div className="flex items-center gap-1.5 bg-cream-100 p-1 rounded-2xl border border-cream-200 text-sm font-semibold">
          <button
            onClick={() => setActiveTab("flashcards")}
            className={`px-4 py-2 rounded-xl transition-all ${
              activeTab === "flashcards"
                ? "bg-white text-cocoa-900 shadow-xs font-bold"
                : "text-ink-600 hover:text-ink-900"
            }`}
          >
            Study Deck
          </button>
          <button
            onClick={() => setActiveTab("wordbank")}
            className={`px-4 py-2 rounded-xl transition-all ${
              activeTab === "wordbank"
                ? "bg-white text-cocoa-900 shadow-xs font-bold"
                : "text-ink-600 hover:text-ink-900"
            }`}
          >
            Word Bank List{data ? ` (${cards.length})` : ""}
          </button>
        </div>
      </div>

      {gradeError && <InlineError error={gradeError} />}

      {error ? (
        <ErrorState error={error} title="We could not load your vocabulary deck" onRetry={reload} />
      ) : isLoading ? (
        <div className="py-20 text-center space-y-3">
          <div className="w-8 h-8 border-2 border-cocoa-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm text-ink-500">Loading your vocabulary deck...</p>
        </div>
      ) : activeTab === "flashcards" ? (
        <div className="space-y-8">
          {/* Flashcard Component */}
          <FlashcardDeck initialCards={cards} onGradeCard={handleGradeCard} />

          {/* SRS Explanation Banner */}
          <div className="max-w-2xl mx-auto bg-cocoa-50/50 border border-cocoa-200/60 rounded-3xl p-6 text-sm text-cocoa-900 space-y-2">
            <div className="flex items-center gap-2 font-bold text-sm text-cocoa-950">
              <Sparkles className="w-4 h-4 text-cocoa-600" />
              <span>How Sharon Online Spaced Repetition Works</span>
            </div>
            <p className="leading-relaxed text-cocoa-800">
              Target words captured in tutor memos automatically populate your deck. When you rate a card as <strong>Again</strong>, it reappears within 24 hours. Rating <strong>Good</strong> schedules it for 3 days, and <strong>Easy</strong> schedules it for 7 days to solidify long-term neurological retention.
            </p>
          </div>
        </div>
      ) : (
        /* Word Bank Table View */
        <div className="bg-white rounded-3xl border border-cream-200 shadow-sm overflow-hidden space-y-4 p-6">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search vocabulary words or definitions..."
                className="w-full pl-10 pr-4 py-2 bg-cream-50/50 border border-cream-200 rounded-xl text-sm sm:text-sm text-ink-900 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
              />
            </div>

            <div className="text-sm text-ink-500 font-medium">
              Showing {filteredCards.length} of {cards.length} vocabulary words
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-cream-200 text-ink-400 uppercase tracking-wider font-bold text-sm">
                  <th className="py-3 px-4">Word & Phonetic</th>
                  <th className="py-3 px-4">Part of Speech</th>
                  <th className="py-3 px-4">Definition & Example</th>
                  <th className="py-3 px-4">Source Lesson</th>
                  <th className="py-3 px-4">Mastery</th>
                  <th className="py-3 px-4 text-right">Audio</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cream-100">
                {filteredCards.map((card) => (
                  <tr key={card.id} className="hover:bg-cream-50/50 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="font-bold text-sm text-ink-900">{card.word}</div>
                      <div className="text-sm font-mono text-ink-400">{card.phonetic}</div>
                    </td>
                    <td className="py-3.5 px-4 font-medium text-ink-600">{card.part_of_speech}</td>
                    <td className="py-3.5 px-4 max-w-md">
                      <div className="font-medium text-ink-800">{card.definition}</div>
                      <div className="text-sm text-ink-500 italic mt-0.5">&ldquo;{card.example_sentence}&rdquo;</div>
                    </td>
                    <td className="py-3.5 px-4 text-ink-600 font-medium max-w-xs truncate">
                      {card.lesson_source}
                    </td>
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-sm font-semibold border ${
                          card.mastery === "mastered"
                            ? "bg-success-surface text-success-hover border-success-border"
                            : card.mastery === "learning"
                            ? "bg-warning-surface text-warning-hover border-warning-border"
                            : "bg-info-surface text-info-hover border-info-border"
                        }`}
                      >
                        {card.mastery}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => speakWord(card.word)}
                        className="p-1.5 text-cocoa-700 hover:text-cocoa-900 hover:bg-cocoa-50 rounded-lg transition-colors"
                        title="Listen"
                      >
                        <Volume2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
