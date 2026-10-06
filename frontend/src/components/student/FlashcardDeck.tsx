"use client";

import { useState } from "react";
import {
  Volume2,
  RotateCw,
  ChevronLeft,
  ChevronRight,
  Shuffle,
  Sparkles,
  CheckCircle,
  Clock,
  Layers,
  Award,
} from "lucide-react";
import { StudentFlashcard } from "@/types/student";

interface FlashcardDeckProps {
  initialCards: StudentFlashcard[];
  onGradeCard?: (cardId: string, grade: "again" | "good" | "easy") => Promise<void> | void;
}

export function FlashcardDeck({ initialCards, onGradeCard }: FlashcardDeckProps) {
  const [cards, setCards] = useState<StudentFlashcard[]>(initialCards);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [filter, setFilter] = useState<"all" | "learning" | "mastered">("all");
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [reviewCountSession, setReviewCountSession] = useState(0);

  const filteredCards = cards.filter((card) => {
    if (filter === "all") return true;
    if (filter === "learning") return card.mastery === "learning" || card.mastery === "new";
    if (filter === "mastered") return card.mastery === "mastered";
    return true;
  });

  const activeCard = filteredCards[currentIndex] || filteredCards[0];

  const handleNext = () => {
    setIsFlipped(false);
    if (currentIndex < filteredCards.length - 1) {
      setCurrentIndex((prev) => prev + 1);
    } else {
      setCurrentIndex(0);
    }
  };

  const handlePrev = () => {
    setIsFlipped(false);
    if (currentIndex > 0) {
      setCurrentIndex((prev) => prev - 1);
    } else {
      setCurrentIndex(filteredCards.length - 1);
    }
  };

  const handleShuffle = () => {
    setIsFlipped(false);
    const shuffled = [...cards].sort(() => Math.random() - 0.5);
    setCards(shuffled);
    setCurrentIndex(0);
  };

  const handleSpeak = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!activeCard || typeof window === "undefined" || !("speechSynthesis" in window)) return;

    setIsSpeaking(true);
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(activeCard.word);
    utterance.lang = "en-US";
    utterance.rate = 0.85;
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
  };

  const handleGrade = async (grade: "again" | "good" | "easy") => {
    if (!activeCard) return;

    const updatedMastery = grade === "easy" ? "mastered" : grade === "good" ? "learning" : "new";
    const daysToAdd = grade === "easy" ? 7 : grade === "good" ? 3 : 1;
    const nextDate = new Date(Date.now() + daysToAdd * 86400000).toISOString().split("T")[0];

    // Optimistically update card in state
    setCards((prev) =>
      prev.map((c) =>
        c.id === activeCard.id
          ? {
              ...c,
              mastery: updatedMastery,
              review_count: c.review_count + 1,
              next_review_due: nextDate,
            }
          : c
      )
    );

    setReviewCountSession((prev) => prev + 1);

    if (onGradeCard) {
      await onGradeCard(activeCard.id, grade);
    }

    // Advance to next card smoothly
    handleNext();
  };

  if (filteredCards.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-cream-200 p-12 text-center shadow-sm">
        <div className="w-16 h-16 rounded-full bg-cocoa-50 border border-cocoa-200 text-cocoa-600 flex items-center justify-center mx-auto mb-4">
          <Award className="w-8 h-8" />
        </div>
        <h3 className="text-xl font-bold text-ink-900 mb-2">Deck Fully Reviewed!</h3>
        <p className="text-ink-600 max-w-md mx-auto mb-6 text-sm">
          No vocabulary cards match the current filter ({filter}). All target words are mastered or scheduled for future review.
        </p>
        <button
          onClick={() => {
            setFilter("all");
            setCurrentIndex(0);
          }}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-cocoa-600 hover:bg-cocoa-700 text-white font-medium rounded-xl text-sm transition-colors shadow-sm"
        >
          <Layers className="w-4 h-4" /> Reset Filter to All Words
        </button>
      </div>
    );
  }

  const masteryBadgeColor =
    activeCard.mastery === "mastered"
      ? "bg-success-surface text-success-hover border-success-border"
      : activeCard.mastery === "learning"
      ? "bg-warning-surface text-warning-hover border-warning-border"
      : "bg-info-surface text-info-hover border-info-border";

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-3 rounded-2xl border border-cream-200 shadow-sm">
        <div className="flex items-center gap-1.5 bg-cream-50 p-1 rounded-xl border border-cream-200 text-sm font-medium">
          <button
            onClick={() => {
              setFilter("all");
              setCurrentIndex(0);
              setIsFlipped(false);
            }}
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              filter === "all" ? "bg-white text-ink-900 shadow-sm font-semibold" : "text-ink-600 hover:text-ink-900"
            }`}
          >
            All ({cards.length})
          </button>
          <button
            onClick={() => {
              setFilter("learning");
              setCurrentIndex(0);
              setIsFlipped(false);
            }}
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              filter === "learning" ? "bg-white text-warning-hover shadow-sm font-semibold" : "text-ink-600 hover:text-ink-900"
            }`}
          >
            Due / Learning ({cards.filter((c) => c.mastery !== "mastered").length})
          </button>
          <button
            onClick={() => {
              setFilter("mastered");
              setCurrentIndex(0);
              setIsFlipped(false);
            }}
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              filter === "mastered" ? "bg-white text-success-hover shadow-sm font-semibold" : "text-ink-600 hover:text-ink-900"
            }`}
          >
            Mastered ({cards.filter((c) => c.mastery === "mastered").length})
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleShuffle}
            title="Shuffle Deck"
            className="p-2 text-ink-600 hover:text-ink-900 hover:bg-cream-100 rounded-xl transition-colors"
          >
            <Shuffle className="w-4 h-4" />
          </button>
          <span className="text-sm font-semibold text-ink-500 bg-cream-100 px-2.5 py-1 rounded-lg">
            {currentIndex + 1} / {filteredCards.length}
          </span>
        </div>
      </div>

      {/* 3D Flip Card Container */}
      <div
        onClick={() => setIsFlipped(!isFlipped)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === " " || e.key === "Enter") {
            e.preventDefault();
            setIsFlipped(!isFlipped);
          }
        }}
        className="relative min-h-[360px] cursor-pointer group focus:outline-none"
      >
        <div
          className={`w-full min-h-[360px] bg-white rounded-3xl border-2 border-cream-200 p-8 shadow-sm transition-all duration-300 flex flex-col justify-between hover:border-cocoa-400 hover:shadow-md ${
            isFlipped ? "bg-gradient-to-br from-white to-cocoa-50/30" : ""
          }`}
        >
          {/* Card Header */}
          <div className="flex items-center justify-between">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold border ${masteryBadgeColor}`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              {activeCard.mastery.toUpperCase()}
            </span>

            <div className="flex items-center gap-2 text-sm text-ink-400">
              <span>Reviewed {activeCard.review_count}x</span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" /> Due {activeCard.next_review_due}
              </span>
            </div>
          </div>

          {/* Card Body */}
          {!isFlipped ? (
            /* FRONT: Word & Phonetics */
            <div className="my-auto text-center space-y-4 py-8">
              <div className="flex items-center justify-center gap-3">
                <h2 className="text-4xl font-extrabold text-ink-900 tracking-tight">{activeCard.word}</h2>
                <button
                  type="button"
                  onClick={handleSpeak}
                  className={`p-2.5 rounded-full border border-cocoa-200 bg-cocoa-50 text-cocoa-700 hover:bg-cocoa-100 transition-colors shadow-xs ${
                    isSpeaking ? "animate-pulse ring-2 ring-cocoa-400" : ""
                  }`}
                  title="Listen to American / Neutral Audio Pronunciation"
                >
                  <Volume2 className="w-5 h-5" />
                </button>
              </div>

              <div className="flex items-center justify-center gap-2 text-sm text-ink-500 font-mono">
                <span>{activeCard.phonetic}</span>
                <span>•</span>
                <span className="italic font-sans text-ink-600 bg-cream-100 px-2 py-0.5 rounded-md text-sm font-medium">
                  {activeCard.part_of_speech}
                </span>
              </div>

              <p className="text-sm text-ink-400 max-w-sm mx-auto">
                Source: <span className="font-medium text-ink-600">{activeCard.lesson_source}</span>
              </p>

              <div className="pt-4">
                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-cocoa-600 bg-cocoa-50 px-3 py-1.5 rounded-xl border border-cocoa-100">
                  <RotateCw className="w-3.5 h-3.5 animate-spin-reverse" />
                  Click or press Space to reveal definition & example
                </span>
              </div>
            </div>
          ) : (
            /* BACK: Definition & Sentence */
            <div className="my-auto space-y-5 py-4">
              <div>
                <span className="text-sm font-bold text-cocoa-600 uppercase tracking-wider">Definition</span>
                <p className="text-lg font-semibold text-ink-900 mt-1 leading-snug">{activeCard.definition}</p>
              </div>

              <div className="bg-cream-50 p-4 rounded-2xl border border-cream-200/80">
                <span className="text-sm font-bold text-ink-500 uppercase tracking-wider">Contextual Example</span>
                <p className="text-ink-800 italic mt-1 text-sm leading-relaxed">&ldquo;{activeCard.example_sentence}&rdquo;</p>
              </div>

              <div className="flex items-center justify-between text-sm text-ink-500 pt-1">
                <span>Part of speech: <strong className="text-ink-700 font-medium">{activeCard.part_of_speech}</strong></span>
                <button
                  type="button"
                  onClick={handleSpeak}
                  className="flex items-center gap-1 text-cocoa-700 hover:text-cocoa-900 font-medium"
                >
                  <Volume2 className="w-3.5 h-3.5" /> Replay audio
                </button>
              </div>
            </div>
          )}

          {/* Card Footer: Flip hint */}
          <div className="border-t border-cream-100 pt-3 flex items-center justify-between text-sm text-ink-400">
            <span>Sharon Online Spaced Repetition (SRS)</span>
            <span className="flex items-center gap-1">
              <RotateCw className="w-3 h-3" /> {isFlipped ? "Flip to word" : "Flip to answer"}
            </span>
          </div>
        </div>
      </div>

      {/* Spaced Repetition Grading Actions (Available when flipped or always) */}
      <div className="bg-white rounded-2xl border border-cream-200 p-4 shadow-sm space-y-3">
        <div className="text-center text-sm font-semibold text-ink-500 uppercase tracking-wider">
          {isFlipped ? "How easily did you recall this word?" : "Flip card above to test your recall & rate mastery"}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <button
            onClick={() => handleGrade("again")}
            className="flex flex-col items-center justify-center py-3 px-2 rounded-xl border border-error-border bg-error-surface/50 hover:bg-error-surface/70 text-error-hover font-medium transition-colors"
          >
            <span className="text-sm font-bold">Again</span>
            <span className="text-sm text-error/80">&lt; 1 day</span>
          </button>

          <button
            onClick={() => handleGrade("good")}
            className="flex flex-col items-center justify-center py-3 px-2 rounded-xl border border-warning-border bg-warning-surface/50 hover:bg-warning-surface/70 text-warning-hover font-medium transition-colors"
          >
            <span className="text-sm font-bold">Good</span>
            <span className="text-sm text-warning/80">3 days</span>
          </button>

          <button
            onClick={() => handleGrade("easy")}
            className="flex flex-col items-center justify-center py-3 px-2 rounded-xl border border-success-border bg-success-surface/50 hover:bg-success-surface/70 text-success-hover font-medium transition-colors"
          >
            <span className="text-sm font-bold flex items-center gap-1">
              <CheckCircle className="w-3.5 h-3.5" /> Easy
            </span>
            <span className="text-sm text-success/80">7 days</span>
          </button>
        </div>
      </div>

      {/* Navigation Controls */}
      <div className="flex items-center justify-between">
        <button
          onClick={handlePrev}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-cream-50 text-ink-700 border border-cream-200 rounded-xl text-sm font-medium transition-colors shadow-xs"
        >
          <ChevronLeft className="w-4 h-4" /> Previous Card
        </button>

        <span className="text-sm text-ink-400">
          Reviewed <strong className="text-ink-700">{reviewCountSession}</strong> cards in this session
        </span>

        <button
          onClick={handleNext}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-cream-50 text-ink-700 border border-cream-200 rounded-xl text-sm font-medium transition-colors shadow-xs"
        >
          Next Card <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
