import { StarRating } from "@/components/ui/StarRating";
import { TutorReview } from "@/types/tutor";
import { CheckCircle2, MessageSquare } from "lucide-react";

interface TutorReviewListProps {
  ratingAvg: number;
  ratingCount: number;
  reviews?: TutorReview[];
}

const DEFAULT_REVIEWS: TutorReview[] = [
  {
    id: "rev-1",
    student_name: "Kenji S.",
    student_country: "Japan",
    student_flag: "🇯🇵",
    rating: 5,
    date: "2 days ago",
    comment:
      "Sharon's pronunciation feedback was outstanding! She pointed out exactly how to position my tongue for the 'R' and 'L' sounds in my business presentation.",
    lesson_topic: "Business Presentation Mastery",
  },
  {
    id: "rev-2",
    student_name: "Min-ji P.",
    student_country: "South Korea",
    student_flag: "🇰🇷",
    rating: 5,
    date: "1 week ago",
    comment:
      "Very patient and enthusiastic tutor. The 25 minutes flew by and I received a detailed vocabulary memo right after class.",
    lesson_topic: "Job Interview Practice",
  },
  {
    id: "rev-3",
    student_name: "Matthias B.",
    student_country: "Germany",
    student_flag: "🇩🇪",
    rating: 5,
    date: "2 weeks ago",
    comment:
      "Her South African neutral accent is so clear and easy to understand. Great conversation about global remote work trends.",
    lesson_topic: "Daily News & Discussion",
  },
];

export function TutorReviewList({ ratingAvg, ratingCount, reviews = DEFAULT_REVIEWS }: TutorReviewListProps) {
  return (
    <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
      {/* Rating Overview */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 border-b border-divider pb-6">
        <div className="space-y-1">
          <h3 className="text-xl font-extrabold text-ink font-serif">Verified Student Reviews</h3>
          <p className="text-sm text-ink-muted">All reviews are from students who completed a 25-minute lesson</p>
        </div>

        <div className="flex items-center gap-4 bg-cream-surface p-4 rounded-2xl border border-cream-deep">
          <div className="text-3xl font-extrabold text-cocoa font-serif">{ratingAvg.toFixed(2)}</div>
          <div>
            <StarRating rating={ratingAvg} size="md" />
            <div className="text-sm text-ink-muted font-medium mt-0.5">Based on {ratingCount} ratings</div>
          </div>
        </div>
      </div>

      {/* Individual Review Items */}
      <div className="space-y-4">
        {reviews.map((rev) => (
          <div key={rev.id} className="p-4 rounded-2xl bg-cream-surface/60 border border-divider space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-base">{rev.student_flag}</span>
                <span className="text-sm font-bold text-ink">{rev.student_name}</span>
                <span className="inline-flex items-center gap-1 text-sm text-success font-semibold">
                  <CheckCircle2 className="w-3 h-3" /> Verified Lesson
                </span>
              </div>
              <span className="text-sm text-ink-muted">{rev.date}</span>
            </div>

            <div className="flex items-center gap-2">
              <StarRating rating={rev.rating} size="sm" />
              <span className="text-sm font-bold text-primary">Topic: {rev.lesson_topic}</span>
            </div>

            <p className="text-sm text-ink-muted leading-relaxed pt-1">{rev.comment}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
