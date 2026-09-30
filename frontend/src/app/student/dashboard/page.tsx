"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Calendar,
  Clock,
  Video,
  BookOpen,
  Award,
  ChevronRight,
  ExternalLink,
  Star,
  Sparkles,
  Layers,
  History,
  User,
  CreditCard,
  CheckCircle2,
  AlertCircle,
  FileText,
} from "lucide-react";
import { studentApi, bookingApi } from "@/lib/api";
import { StudentLessonItem, StudentFlashcard } from "@/types/student";
import { LessonMemoModal } from "@/components/student/LessonMemoModal";
import { ReviewRubricModal } from "@/components/student/ReviewRubricModal";

export default function StudentDashboardPage() {
  const [lessons, setLessons] = useState<StudentLessonItem[]>([]);
  const [flashcards, setFlashcards] = useState<StudentFlashcard[]>([]);
  const [wallet, setWallet] = useState<{ available_credits: number } | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Modals state
  const [selectedMemoLesson, setSelectedMemoLesson] = useState<StudentLessonItem | null>(null);
  const [reviewLesson, setReviewLesson] = useState<StudentLessonItem | null>(null);

  useEffect(() => {
    async function loadDashboardData() {
      try {
        const [fetchedLessons, fetchedCards, fetchedWallet] = await Promise.all([
          studentApi.getStudentLessons(),
          studentApi.getStudentFlashcards(),
          bookingApi.getStudentWallet(),
        ]);
        setLessons(fetchedLessons);
        setFlashcards(fetchedCards);
        setWallet(fetchedWallet);
      } catch (err) {
        console.error("Error loading student dashboard:", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadDashboardData();
  }, []);

  const upcomingLesson = lessons.find((l) => l.status === "confirmed") || lessons[0];
  const completedLessons = lessons.filter((l) => l.status === "completed");
  const wordsDueCount = flashcards.filter((c) => c.mastery !== "mastered").length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8 animate-fade-in">
      {/* Top Banner / Welcome */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-ink-900 tracking-tight">Student Command Center</h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-teal-100 text-teal-800 border border-teal-200">
              Active Learner
            </span>
          </div>
          <p className="text-xs sm:text-sm text-ink-600 mt-1">
            Welcome back! Review your upcoming 25-min lessons, completed teacher memos, and spaced repetition flashcards.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-white border border-cream-200 px-4 py-2.5 rounded-2xl text-xs shadow-xs flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700">
              <CreditCard className="w-4 h-4" />
            </div>
            <div>
              <span className="text-ink-500 block text-[11px]">Available Credits</span>
              <strong className="text-teal-900 text-sm font-black">
                {wallet ? `${wallet.available_credits} Lessons` : "3 Lessons"}
              </strong>
            </div>
          </div>
          <Link
            href="/tutors"
            className="px-4 py-2.5 bg-teal-600 hover:bg-teal-700 text-white font-bold text-xs rounded-xl shadow-xs transition-colors flex items-center gap-1.5"
          >
            <Calendar className="w-3.5 h-3.5" /> Book Lesson
          </Link>
        </div>
      </div>

      {/* Navigation Sub-bar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-cream-200 pb-3">
        <Link
          href="/student/dashboard"
          className="px-3.5 py-1.5 bg-teal-50 text-teal-800 font-bold rounded-xl text-xs border border-teal-200"
        >
          Overview
        </Link>
        <Link
          href="/student/history"
          className="px-3.5 py-1.5 text-ink-600 hover:text-ink-900 hover:bg-cream-100 font-medium rounded-xl text-xs transition-colors flex items-center gap-1.5"
        >
          <History className="w-3.5 h-3.5" /> Lesson History & Memos
        </Link>
        <Link
          href="/student/vocabulary"
          className="px-3.5 py-1.5 text-ink-600 hover:text-ink-900 hover:bg-cream-100 font-medium rounded-xl text-xs transition-colors flex items-center gap-1.5"
        >
          <Layers className="w-3.5 h-3.5 text-amber-600" /> Flashcard Deck ({flashcards.length})
        </Link>
        <Link
          href="/student/profile"
          className="px-3.5 py-1.5 text-ink-600 hover:text-ink-900 hover:bg-cream-100 font-medium rounded-xl text-xs transition-colors flex items-center gap-1.5"
        >
          <User className="w-3.5 h-3.5" /> Learning Profile & Timezone
        </Link>
      </div>

      {/* Spotlight: Upcoming Lesson Card */}
      {upcomingLesson && (
        <div className="bg-gradient-to-r from-teal-950 via-teal-900 to-ink-950 text-white rounded-3xl p-6 sm:p-8 shadow-xl space-y-6 relative overflow-hidden">
          <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-radial-pattern opacity-10 pointer-events-none" />

          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-2 text-xs font-bold bg-white/10 border border-white/20 px-3 py-1 rounded-full text-accent-300">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Next Scheduled Lesson
            </span>
            <span className="text-xs text-white/70 font-medium">
              Reference: <strong className="text-white font-mono">{upcomingLesson.booking_reference}</strong>
            </span>
          </div>

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="flex items-center gap-4">
              <img
                src={upcomingLesson.teacher.avatar}
                alt={upcomingLesson.teacher.name}
                className="w-16 h-16 rounded-2xl object-cover border-2 border-teal-400/50 shadow-md"
              />
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h2 className="text-xl sm:text-2xl font-black text-white">{upcomingLesson.teacher.name}</h2>
                  <span className="text-xs bg-teal-800/80 text-teal-200 px-2 py-0.5 rounded-md border border-teal-700">
                    {upcomingLesson.teacher.accent}
                  </span>
                </div>
                <div className="text-xs text-accent-300 font-semibold flex items-center gap-1.5 mt-1">
                  <BookOpen className="w-3.5 h-3.5" />
                  <span>[{upcomingLesson.material_cefr}] {upcomingLesson.material_title}</span>
                </div>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <div className="bg-white/10 backdrop-blur-sm rounded-2xl px-5 py-3 border border-white/15 text-xs space-y-0.5 text-center sm:text-left">
                <div className="text-teal-200 font-medium">Scheduled Local Time</div>
                <div className="font-extrabold text-white text-sm">{upcomingLesson.local_date}</div>
                <div className="text-accent-300 font-bold">
                  {upcomingLesson.local_start_time} - {upcomingLesson.local_end_time} ({upcomingLesson.viewer_timezone})
                </div>
              </div>

              <Link
                href={`/student/classroom/${upcomingLesson.id}`}
                className="px-6 py-3.5 bg-accent-500 hover:bg-accent-600 text-ink-950 font-black rounded-2xl text-sm transition-all shadow-lg flex items-center justify-center gap-2 text-center"
              >
                <Video className="w-4 h-4 text-ink-950" /> Enter Classroom Staging
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Grid: Flashcard SRS Quick Practice & Learning Goals */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Flashcard Quick Widget */}
        <div className="md:col-span-2 bg-white rounded-3xl border border-cream-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-amber-50 border border-amber-200 text-amber-700 flex items-center justify-center">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-ink-900">Spaced Repetition Vocabulary</h3>
                <p className="text-xs text-ink-500">Auto-synced from your post-lesson memos</p>
              </div>
            </div>
            <Link
              href="/student/vocabulary"
              className="text-xs font-semibold text-teal-700 hover:text-teal-900 flex items-center gap-1"
            >
              Open Full Study Deck <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="bg-cream-50 rounded-2xl p-3.5 border border-cream-200/80 text-center">
              <span className="text-xs text-ink-500 block">Total Cards</span>
              <strong className="text-lg font-black text-ink-900">{flashcards.length}</strong>
            </div>
            <div className="bg-amber-50/60 rounded-2xl p-3.5 border border-amber-200/60 text-center">
              <span className="text-xs text-amber-700 block">Due for Review</span>
              <strong className="text-lg font-black text-amber-900">{wordsDueCount}</strong>
            </div>
            <div className="bg-emerald-50/60 rounded-2xl p-3.5 border border-emerald-200/60 text-center">
              <span className="text-xs text-emerald-700 block">Mastered</span>
              <strong className="text-lg font-black text-emerald-900">
                {flashcards.filter((c) => c.mastery === "mastered").length}
              </strong>
            </div>
          </div>

          <div className="space-y-2 pt-1">
            <span className="text-xs font-bold text-ink-500 uppercase tracking-wider block">Recently Added Words:</span>
            <div className="flex flex-wrap gap-2">
              {flashcards.slice(0, 4).map((card) => (
                <Link
                  key={card.id}
                  href="/student/vocabulary"
                  className="px-3 py-1.5 bg-cream-50 hover:bg-teal-50 border border-cream-200 hover:border-teal-200 rounded-xl text-xs font-semibold text-ink-800 flex items-center gap-2 transition-colors"
                >
                  <span className="font-mono text-teal-800">{card.word}</span>
                  <span className="text-[10px] text-ink-400 italic">({card.part_of_speech})</span>
                </Link>
              ))}
            </div>
          </div>
        </div>

        {/* Quick Profile Summary */}
        <div className="bg-white rounded-3xl border border-cream-200 p-6 shadow-sm space-y-4 flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-teal-50 border border-teal-200 text-teal-700 flex items-center justify-center">
                <User className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-ink-900">Learning Target</h3>
                <p className="text-xs text-teal-700 font-semibold">CEFR C1 - Advanced</p>
              </div>
            </div>

            <div className="bg-cream-50/60 border border-cream-200/70 p-3.5 rounded-2xl text-xs text-ink-700 leading-relaxed">
              &ldquo;Mastering cross-border corporate negotiations, tech executive presentation delivery, and natural conversational cadence.&rdquo;
            </div>
          </div>

          <Link
            href="/student/profile"
            className="w-full text-center py-2.5 px-4 bg-cream-100 hover:bg-cream-200 text-ink-800 text-xs font-semibold rounded-xl transition-colors block"
          >
            Update Goals & Timezone
          </Link>
        </div>
      </div>

      {/* Completed Lessons & Memos Section */}
      <div className="bg-white rounded-3xl border border-cream-200 p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-ink-900">Recent Completed Lessons</h3>
            <p className="text-xs text-ink-500">Access tutor feedback notes, vocabulary lists, and leave lesson ratings</p>
          </div>
          <Link
            href="/student/history"
            className="text-xs font-semibold text-teal-700 hover:text-teal-900 flex items-center gap-1"
          >
            Full Lesson Archive ({completedLessons.length}) <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="divide-y divide-cream-100">
          {completedLessons.map((item) => (
            <div
              key={item.id}
              className="py-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 hover:bg-cream-50/40 p-2 rounded-2xl transition-colors"
            >
              <div className="flex items-center gap-4">
                <img
                  src={item.teacher.avatar}
                  alt={item.teacher.name}
                  className="w-12 h-12 rounded-xl object-cover border border-cream-200"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="font-bold text-sm text-ink-900">{item.teacher.name}</h4>
                    <span className="text-xs text-ink-400">• {item.local_date}</span>
                    <span className="text-[11px] font-bold px-2 py-0.5 bg-cream-100 text-ink-700 rounded-md">
                      CEFR {item.material_cefr}
                    </span>
                  </div>
                  <p className="text-xs text-ink-600 font-medium mt-0.5">{item.material_title}</p>
                </div>
              </div>

              <div className="flex items-center gap-2 w-full md:w-auto justify-end">
                {item.memo && (
                  <button
                    onClick={() => setSelectedMemoLesson(item)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-teal-50 hover:bg-teal-100 border border-teal-200 text-teal-800 text-xs font-semibold rounded-xl transition-colors"
                  >
                    <FileText className="w-3.5 h-3.5" /> View Tutor Memo
                  </button>
                )}

                {item.review ? (
                  <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-medium rounded-xl">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Rated {item.review.rating}★
                  </span>
                ) : (
                  <button
                    onClick={() => setReviewLesson(item)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-800 text-xs font-semibold rounded-xl transition-colors"
                  >
                    <Star className="w-3.5 h-3.5 text-amber-600 fill-amber-500" /> Leave Review
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Lesson Memo Modal */}
      {selectedMemoLesson && (
        <LessonMemoModal
          lesson={selectedMemoLesson}
          isOpen={!!selectedMemoLesson}
          onClose={() => setSelectedMemoLesson(null)}
        />
      )}

      {/* Review Rubric Modal */}
      {reviewLesson && (
        <ReviewRubricModal
          bookingId={reviewLesson.id}
          teacherName={reviewLesson.teacher.name}
          isOpen={!!reviewLesson}
          onClose={() => setReviewLesson(null)}
          onReviewSubmitted={(rating, tags) => {
            setLessons((prev) =>
              prev.map((l) =>
                l.id === reviewLesson.id
                  ? {
                      ...l,
                      review: {
                        rating,
                        tags,
                        submitted_at: new Date().toISOString(),
                      },
                    }
                  : l
              )
            );
          }}
        />
      )}
    </div>
  );
}
