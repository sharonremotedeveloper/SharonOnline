"use client";

import { useState } from "react";
import Link from "next/link";
import {
  History,
  FileText,
  Star,
  CheckCircle2,
  AlertCircle,
  Search,
  Filter,
  ChevronLeft,
  Calendar,
  Clock,
  Sparkles,
  BookOpen,
} from "lucide-react";
import { studentApi } from "@/lib/api";
import { StudentLessonItem } from "@/types/student";
import { LessonMemoModal } from "@/components/student/LessonMemoModal";
import { ReviewRubricModal } from "@/components/student/ReviewRubricModal";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";

export default function StudentHistoryPage() {
  const { data, error, loading: isLoading, reload } = useApiData<StudentLessonItem[]>(
    () => studentApi.getStudentLessons(),
    []
  );
  const lessons = data ?? [];
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "completed" | "interrupted">("all");

  // Modals state
  const [activeMemoLesson, setActiveMemoLesson] = useState<StudentLessonItem | null>(null);
  const [activeReviewLesson, setActiveReviewLesson] = useState<StudentLessonItem | null>(null);

  const filteredLessons = lessons.filter((lesson) => {
    if (statusFilter === "completed" && lesson.status !== "completed") return false;
    if (statusFilter === "interrupted" && lesson.status !== "interrupted_power") return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTeacher = lesson.teacher.name.toLowerCase().includes(q);
      const matchMaterial = lesson.material_title.toLowerCase().includes(q);
      const matchBooking = lesson.booking_reference.toLowerCase().includes(q);
      return matchTeacher || matchMaterial || matchBooking;
    }

    return true;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8 animate-fade-in">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Link
              href="/student/dashboard"
              className="p-1.5 text-ink-400 hover:text-ink-900 hover:bg-cream-100 rounded-xl transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-ink-900 tracking-tight">Lesson History & Memos</h1>
          </div>
          <p className="text-xs sm:text-sm text-ink-600 mt-1 pl-8">
            Access past 25-minute lesson summaries, review tutor feedback, and inspect acquired vocabulary notes.
          </p>
        </div>

        <Link
          href="/student/vocabulary"
          className="px-4 py-2.5 bg-white border border-cream-200 hover:bg-cream-50 text-teal-800 font-bold text-xs rounded-xl shadow-xs transition-colors flex items-center gap-2"
        >
          <Sparkles className="w-4 h-4 text-amber-500" /> Go to Vocabulary SRS Deck
        </Link>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white rounded-2xl border border-cream-200 p-4 shadow-sm flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by tutor name, lesson topic, or booking ID..."
            className="w-full pl-10 pr-4 py-2 bg-cream-50/50 border border-cream-200 rounded-xl text-xs sm:text-sm text-ink-900 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
          />
        </div>

        <div className="flex items-center gap-1.5 bg-cream-50 p-1 rounded-xl border border-cream-200 text-xs font-medium">
          <button
            onClick={() => setStatusFilter("all")}
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              statusFilter === "all" ? "bg-white text-ink-900 shadow-sm font-semibold" : "text-ink-600 hover:text-ink-900"
            }`}
          >
            All Lessons ({lessons.length})
          </button>
          <button
            onClick={() => setStatusFilter("completed")}
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              statusFilter === "completed"
                ? "bg-white text-teal-800 shadow-sm font-semibold"
                : "text-ink-600 hover:text-ink-900"
            }`}
          >
            Completed ({lessons.filter((l) => l.status === "completed").length})
          </button>
          <button
            onClick={() => setStatusFilter("interrupted")}
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              statusFilter === "interrupted"
                ? "bg-white text-amber-800 shadow-sm font-semibold"
                : "text-ink-600 hover:text-ink-900"
            }`}
          >
            Power / Interrupted ({lessons.filter((l) => l.status === "interrupted_power").length})
          </button>
        </div>
      </div>

      {/* Lesson List */}
      <div className="space-y-4">
        {error ? (
          <ErrorState error={error} title="We could not load your lesson history" onRetry={reload} />
        ) : isLoading ? (
          <div className="bg-white rounded-3xl border border-cream-200 p-12 text-center text-xs text-ink-500">
            Loading your lessons...
          </div>
        ) : filteredLessons.length === 0 ? (
          <div className="bg-white rounded-3xl border border-cream-200 p-12 text-center shadow-sm">
            <History className="w-12 h-12 text-ink-300 mx-auto mb-3" />
            <h3 className="text-base font-bold text-ink-900">No lessons found</h3>
            <p className="text-xs text-ink-500 max-w-sm mx-auto mt-1">
              {lessons.length === 0
                ? "You have no lessons yet. Once you book and take a lesson it will appear here."
                : "No completed or past lessons match your search criteria."}
            </p>
          </div>
        ) : (
          filteredLessons.map((lesson) => (
            <div
              key={lesson.id}
              className="bg-white rounded-3xl border border-cream-200 p-6 shadow-sm hover:shadow-md transition-shadow space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-cream-100 pb-4">
                <div className="flex items-center gap-4">
                  <img
                    src={lesson.teacher.avatar}
                    alt={lesson.teacher.name}
                    className="w-14 h-14 rounded-2xl object-cover border border-cream-200 shadow-xs"
                  />
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-extrabold text-base text-ink-900">{lesson.teacher.name}</h3>
                      <span className="text-xs bg-cream-100 text-ink-700 px-2 py-0.5 rounded-md font-medium">
                        {lesson.teacher.accent}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-ink-400 mt-1">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" /> {lesson.local_date}
                      </span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" /> {lesson.local_start_time} - {lesson.local_end_time} ({lesson.viewer_timezone})
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-start sm:self-auto">
                  <span className="text-xs font-mono text-ink-400 bg-cream-50 px-2.5 py-1 rounded-lg border border-cream-200">
                    {lesson.booking_reference}
                  </span>
                  {lesson.status === "completed" && (
                    <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Completed
                    </span>
                  )}
                  {lesson.status === "interrupted_power" && (
                    <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                      <AlertCircle className="w-3.5 h-3.5" /> Grid Interrupted (Credit Refunded)
                    </span>
                  )}
                  {lesson.status === "confirmed" && (
                    <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-teal-50 text-teal-700 border border-teal-200">
                      Scheduled
                    </span>
                  )}
                </div>
              </div>

              {/* Lesson Subject & Action Row */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-teal-100 text-teal-800 text-[11px] font-bold rounded-md">
                      CEFR {lesson.material_cefr}
                    </span>
                    <h4 className="font-bold text-sm text-ink-900">{lesson.material_title}</h4>
                  </div>
                  {lesson.memo && (
                    <p className="text-xs text-ink-600 line-clamp-1 italic max-w-xl">
                      &ldquo;{lesson.memo.feedback_text}&rdquo;
                    </p>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {lesson.memo ? (
                    <button
                      onClick={() => setActiveMemoLesson(lesson)}
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white text-xs font-bold rounded-xl transition-colors shadow-xs"
                    >
                      <FileText className="w-3.5 h-3.5" /> Read Memo & Vocab
                    </button>
                  ) : (
                    <span className="text-xs text-ink-400 italic">No memo available</span>
                  )}

                  {lesson.status === "completed" && (
                    <>
                      {lesson.review ? (
                        <span className="inline-flex items-center gap-1 px-3 py-2 bg-cream-50 border border-cream-200 text-xs font-semibold text-ink-700 rounded-xl">
                          <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-400" />
                          Rated {lesson.review.rating} / 5
                        </span>
                      ) : (
                        <button
                          onClick={() => setActiveReviewLesson(lesson)}
                          className="inline-flex items-center gap-1.5 px-4 py-2 bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-800 text-xs font-bold rounded-xl transition-colors"
                        >
                          <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-500" /> Review Tutor
                        </button>
                      )}
                    </>
                  )}

                  {lesson.material_slug && (
                    <Link
                      href={`/materials/${lesson.material_slug}`}
                      className="inline-flex items-center gap-1 px-3 py-2 bg-cream-100 hover:bg-cream-200 text-ink-700 text-xs font-medium rounded-xl transition-colors"
                    >
                      <BookOpen className="w-3.5 h-3.5" /> Open Sheet
                    </Link>
                  )}
                </div>
              </div>

              {/* Acquired Vocabulary Chip Bar */}
              {lesson.memo?.vocabulary_words && lesson.memo.vocabulary_words.length > 0 && (
                <div className="pt-2 border-t border-cream-100 flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] font-bold text-ink-400 uppercase tracking-wider">Acquired Vocab:</span>
                  {lesson.memo.vocabulary_words.map((item, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-0.5 bg-cream-50 text-teal-800 border border-cream-200 rounded-lg text-xs font-mono font-medium"
                    >
                      {item.word}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Lesson Memo Modal */}
      {activeMemoLesson && (
        <LessonMemoModal
          lesson={activeMemoLesson}
          isOpen={!!activeMemoLesson}
          onClose={() => setActiveMemoLesson(null)}
        />
      )}

      {/* Review Rubric Modal */}
      {activeReviewLesson && (
        <ReviewRubricModal
          bookingId={activeReviewLesson.id}
          teacherName={activeReviewLesson.teacher.name}
          isOpen={!!activeReviewLesson}
          onClose={() => setActiveReviewLesson(null)}
          onReviewSubmitted={() => {
            // Re-fetch so the rating shown is what the server actually stored.
            reload();
          }}
        />
      )}
    </div>
  );
}
