"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Star,
  ShieldCheck,
  ChevronLeft,
  CheckCircle2,
  Send,
  Sparkles,
  Calendar,
  Clock,
} from "lucide-react";
import { studentApi, submitLessonReview } from "@/lib/api";
import { StudentLessonItem } from "@/types/student";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

const RUBRIC_TAGS = [
  "Patience & Empathy",
  "Clear Pronunciation",
  "Great Corrections",
  "Conversational Flow",
  "Encouraging Atmosphere",
  "Deep Topic Expertise",
  "Ideal Pacing",
  "Helpful Examples",
];

export default function BookingReviewPage() {
  const params = useParams();
  const router = useRouter();
  const bookingId = params?.id as string;

  const [lesson, setLesson] = useState<StudentLessonItem | null>(null);
  const [rating, setRating] = useState<number>(5);
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([
    "Patience & Empathy",
    "Clear Pronunciation",
  ]);
  const [privateNotes, setPrivateNotes] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    async function loadLesson() {
      setIsLoading(true);
      setLoadError(null);
      try {
        const lessons = await studentApi.getStudentLessons();
        const found = lessons.find((l) => l.id === bookingId);
        if (!found) {
          setLesson(null);
          setLoadError("We could not find this lesson in your history.");
        } else {
          setLesson(found);
        }
      } catch (e) {
        console.error("Failed to load lesson for review:", e);
        setLesson(null);
        setLoadError(e);
      } finally {
        setIsLoading(false);
      }
    }
    loadLesson();
  }, [bookingId, reloadTick]);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await submitLessonReview(bookingId, rating, selectedTags, privateNotes);
      setIsSubmitted(true);
      setTimeout(() => {
        router.push("/student/history");
      }, 2000);
    } catch (err) {
      console.error("Failed to submit review:", err);
      setSubmitError(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center space-y-3">
        <div className="w-8 h-8 border-2 border-cocoa-600 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-ink-500">Loading lesson details...</p>
      </div>
    );
  }

  if (loadError || !lesson) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 space-y-4">
        <ErrorState
          error={loadError ?? "We could not find this lesson."}
          title="We could not load this lesson"
          onRetry={() => setReloadTick((t) => t + 1)}
        />
        <div className="text-center">
          <Link href="/student/history" className="text-sm font-semibold text-cocoa-700 hover:underline">
            Back to Lesson History
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-10 space-y-8 animate-fade-in">
      {/* Back button */}
      <div>
        <Link
          href="/student/history"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-500 hover:text-ink-900 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" /> Back to Lesson History
        </Link>
      </div>

      {isSubmitted ? (
        <div className="bg-white rounded-3xl border border-cream-200 p-12 text-center shadow-sm space-y-4">
          <div className="w-16 h-16 rounded-full bg-success-surface border border-success-border text-success flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-8 h-8" />
          </div>
          <h2 className="text-2xl font-extrabold text-ink-900">Review Submitted!</h2>
          <p className="text-sm text-ink-600 max-w-md mx-auto">
            Thank you for rating your lesson with{" "}
            <strong>{lesson?.teacher.name || "your tutor"}</strong>. Your feedback helps our teachers grow and maintains high marketplace standards.
          </p>
          <p className="text-sm text-ink-400">Redirecting to lesson history...</p>
        </div>
      ) : (
        <div className="bg-white rounded-3xl border border-cream-200 shadow-sm overflow-hidden">
          {/* Header */}
          <div className="bg-cream-50 border-b border-cream-200 p-6 sm:p-8 space-y-4">
            <span className="text-sm font-bold text-cocoa-700 uppercase tracking-wider">Lesson Feedback</span>
            <div className="flex items-center gap-4">
              {lesson?.teacher.avatar && (
                <img
                  src={lesson.teacher.avatar}
                  alt={lesson.teacher.name}
                  className="w-14 h-14 rounded-2xl object-cover border border-cream-200 shadow-xs"
                />
              )}
              <div>
                <h1 className="text-xl font-extrabold text-ink-900">
                  Review Lesson with {lesson?.teacher.name || "Tutor"}
                </h1>
                <p className="text-sm text-ink-500 mt-0.5">
                  {lesson?.material_title} • {lesson?.local_date}
                </p>
              </div>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="p-6 sm:p-8 space-y-8">
            {/* 5-Star Rubric */}
            <div className="text-center space-y-3">
              <p id="rating-label" className="text-sm font-bold text-ink-500 uppercase tracking-wider block">
                Overall Lesson Rating
              </p>
              <div role="group" aria-labelledby="rating-label" className="flex items-center justify-center gap-2">
                {[1, 2, 3, 4, 5].map((star) => {
                  const filled = (hoverRating !== null ? hoverRating : rating) >= star;
                  return (
                    <button
                      key={star}
                      type="button"
                      onMouseEnter={() => setHoverRating(star)}
                      onMouseLeave={() => setHoverRating(null)}
                      onClick={() => setRating(star)}
                      aria-label={`${star} ${star === 1 ? "star" : "stars"}`}
                      aria-pressed={rating === star}
                      className="p-1 transition-transform hover:scale-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-md"
                    >
                      <Star
                        className={`w-9 h-9 ${
                          filled
                            ? "fill-star text-star drop-shadow-sm"
                            : "text-cream-300 stroke-1"
                        }`}
                      />
                    </button>
                  );
                })}
              </div>
              <p className="text-sm font-medium text-ink-600">
                {rating === 5 && "⭐ Excellent - Flawless session, highly engaging"}
                {rating === 4 && "⭐ Very Good - Clear instruction & great atmosphere"}
                {rating === 3 && "⭐ Good - Standard lesson, met expectations"}
                {rating === 2 && "⭐ Fair - Several areas need improvement"}
                {rating === 1 && "⭐ Poor - Unmet expectations"}
              </p>
            </div>

            {/* Rubric Category Tags */}
            <div className="space-y-3">
              <p id="tags-label" className="text-sm font-bold text-ink-500 uppercase tracking-wider block">
                What did {lesson?.teacher.name || "the tutor"} do especially well?
              </p>
              <div role="group" aria-labelledby="tags-label" className="flex flex-wrap gap-2">
                {RUBRIC_TAGS.map((tag) => {
                  const isSelected = selectedTags.includes(tag);
                  return (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => toggleTag(tag)}
                      aria-pressed={isSelected}
                      className={`text-sm px-3.5 py-2 rounded-full border transition-all ${
                        isSelected
                          ? "bg-cocoa-600 border-cocoa-600 text-white font-semibold shadow-xs"
                          : "bg-cream-50 border-cream-200 text-ink-700 hover:border-cream-300"
                      }`}
                    >
                      {isSelected ? "✓ " : "+ "}
                      {tag}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Qualitative Constructive Feedback */}
            <div className="space-y-2">
              <label htmlFor="f-private-constructive-not" className="text-sm font-bold text-ink-500 uppercase tracking-wider block">
                Private Constructive Note for {lesson?.teacher.name || "Tutor"}
              </label>
              <textarea id="f-private-constructive-not"
                value={privateNotes}
                onChange={(e) => setPrivateNotes(e.target.value)}
                placeholder="Share any pacing notes, topics you'd like to dive into for your next session, or specific grammar focus..."
                rows={4}
                className="w-full text-base sm:text-sm rounded-2xl border border-strong p-4 focus:outline-none focus:ring-2 focus:ring-cocoa-500 focus:border-transparent text-ink-900 bg-cream-50/30"
              />
            </div>

            {/* Asymmetric Notice */}
            <div className="bg-cocoa-50/70 border border-cocoa-200/80 rounded-2xl p-4 flex items-start gap-3 text-sm text-cocoa-900">
              <ShieldCheck className="w-5 h-5 text-cocoa-700 shrink-0 mt-0.5" />
              <div>
                <strong className="font-semibold block mb-0.5">Asymmetric Privacy Protection</strong>
                <span>
                  Star ratings calculate public tutor averages. Your written feedback is confidential and visible only to {lesson?.teacher.name || "your tutor"} and Sharon Online academic mentors.
                </span>
              </div>
            </div>

            <InlineError error={submitError} />

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <Link
                href="/student/history"
                className="px-5 py-2.5 text-sm font-semibold text-ink-600 hover:text-ink-900 rounded-xl"
              >
                Skip for now
              </Link>
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center gap-2 px-7 py-3 bg-cocoa-600 hover:bg-cocoa-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-colors shadow-sm"
              >
                {isSubmitting ? (
                  <>Submitting...</>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" /> Submit Confidential Review
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
