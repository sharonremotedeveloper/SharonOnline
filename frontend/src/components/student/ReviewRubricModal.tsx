"use client";

import { useState } from "react";
import { Star, ShieldCheck, CheckCircle2, X, Send, Sparkles } from "lucide-react";
import { submitLessonReview } from "@/lib/api";
import { InlineError } from "@/components/ui/ErrorState";

interface ReviewRubricModalProps {
  bookingId: string;
  teacherName: string;
  isOpen: boolean;
  onClose: () => void;
  onReviewSubmitted?: (rating: number, tags: string[]) => void;
}

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

export function ReviewRubricModal({
  bookingId,
  teacherName,
  isOpen,
  onClose,
  onReviewSubmitted,
}: ReviewRubricModalProps) {
  const [rating, setRating] = useState<number>(5);
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([
    "Patience & Empathy",
    "Clear Pronunciation",
  ]);
  const [privateNotes, setPrivateNotes] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isSuccess, setIsSuccess] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<unknown>(null);

  if (!isOpen) return null;

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
      setIsSuccess(true);
      if (onReviewSubmitted) {
        onReviewSubmitted(rating, selectedTags);
      }
      setTimeout(() => {
        setIsSuccess(false);
        onClose();
      }, 1500);
    } catch (err) {
      console.error("Failed to submit review:", err);
      setSubmitError(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in overflow-y-auto">
      <div className="relative w-full max-w-lg bg-white rounded-3xl border border-cream-200 shadow-2xl overflow-hidden animate-scale-up">
        {/* Header */}
        <div className="bg-cream-50 border-b border-cream-200 p-6 flex items-start justify-between">
          <div>
            <span className="text-sm font-bold text-cocoa-700 uppercase tracking-wider">Lesson Feedback</span>
            <h3 className="text-xl font-extrabold text-ink-900 mt-1">Review Lesson with {teacherName}</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-ink-400 hover:text-ink-700 hover:bg-cream-200/50 rounded-full transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {isSuccess ? (
          <div className="p-8 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <h4 className="text-xl font-bold text-ink-900">Review Submitted!</h4>
            <p className="text-sm text-ink-600 max-w-sm mx-auto">
              Thank you for supporting {teacherName}. Your private feedback helps our tutors continually refine their lessons.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-6">
            {/* Star Rating */}
            <div className="text-center space-y-2">
              <label className="text-sm font-bold text-ink-500 uppercase tracking-wider block">
                Overall Lesson Experience
              </label>
              <div className="flex items-center justify-center gap-2">
                {[1, 2, 3, 4, 5].map((star) => {
                  const filled = (hoverRating !== null ? hoverRating : rating) >= star;
                  return (
                    <button
                      key={star}
                      type="button"
                      onMouseEnter={() => setHoverRating(star)}
                      onMouseLeave={() => setHoverRating(null)}
                      onClick={() => setRating(star)}
                      className="p-1 transition-transform hover:scale-110 focus:outline-none"
                    >
                      <Star
                        className={`w-8 h-8 ${
                          filled
                            ? "fill-amber-400 text-amber-400 drop-shadow-sm"
                            : "text-cream-300 stroke-1"
                        }`}
                      />
                    </button>
                  );
                })}
              </div>
              <p className="text-sm font-medium text-ink-600">
                {rating === 5 && "⭐ Excellent - Flawless session"}
                {rating === 4 && "⭐ Very Good - Highly effective"}
                {rating === 3 && "⭐ Good - Standard session"}
                {rating === 2 && "⭐ Fair - Needs improvement"}
                {rating === 1 && "⭐ Poor - Unmet expectations"}
              </p>
            </div>

            {/* Rubric Category Tags */}
            <div className="space-y-2">
              <label className="text-sm font-bold text-ink-500 uppercase tracking-wider block">
                What did the tutor do especially well?
              </label>
              <div className="flex flex-wrap gap-2">
                {RUBRIC_TAGS.map((tag) => {
                  const isSelected = selectedTags.includes(tag);
                  return (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => toggleTag(tag)}
                      className={`text-sm px-3 py-1.5 rounded-full border transition-all ${
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

            {/* Private Qualitative Feedback */}
            <div className="space-y-2">
              <label className="text-sm font-bold text-ink-500 uppercase tracking-wider block">
                Private Note for {teacherName} (Optional)
              </label>
              <textarea
                value={privateNotes}
                onChange={(e) => setPrivateNotes(e.target.value)}
                placeholder="Share any specific pacing preferences, topics you'd like to dive into next time, or words of encouragement..."
                rows={3}
                className="w-full text-sm rounded-xl border border-cream-200 p-3 focus:outline-none focus:ring-2 focus:ring-cocoa-500 focus:border-transparent text-ink-900 bg-cream-50/30"
              />
            </div>

            {/* Asymmetric Confidentiality Notice */}
            <div className="bg-cocoa-50/70 border border-cocoa-200/80 rounded-2xl p-3.5 flex items-start gap-3 text-sm text-cocoa-900">
              <ShieldCheck className="w-5 h-5 text-cocoa-700 shrink-0 mt-0.5" />
              <div>
                <strong className="font-semibold block mb-0.5">Asymmetric Privacy Protection</strong>
                <span>
                  Your star rating updates the tutor&apos;s public profile score, but written comments remain confidential between you, {teacherName}, and platform academic admins.
                </span>
              </div>
            </div>

            <InlineError error={submitError} />

            {/* Submit Action */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm font-semibold text-ink-600 hover:text-ink-900 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-cocoa-600 hover:bg-cocoa-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-colors shadow-sm"
              >
                {isSubmitting ? (
                  <>Submitting...</>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" /> Submit Review
                  </>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
