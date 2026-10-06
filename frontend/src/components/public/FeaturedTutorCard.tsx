import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { FeaturedTeacher } from "@/lib/api";
import { StarRating } from "@/components/ui/StarRating";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import { TutorPortrait } from "./TutorPortrait";

/** Photo-first tutor card: big portrait, rating only when there are real reviews, price and one clear action. */
export function FeaturedTutorCard({ tutor }: { tutor: FeaturedTeacher }) {
  const href = `/tutors/${tutor.slug || tutor.id}`;
  const hasReviews = tutor.review_count > 0 && tutor.rating > 0;

  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl border border-divider bg-white shadow-card transition-shadow hover:shadow-card-hover">
      <Link href={href} className="relative block" aria-label={`View ${tutor.name}'s profile`} tabIndex={-1}>
        <TutorPortrait
          src={tutor.avatar}
          name={tutor.name}
          className="aspect-[4/5] w-full"
          sizes="(min-width: 768px) 30vw, 92vw"
        />
      </Link>

      <div className="flex flex-1 flex-col gap-3 p-5">
        <div>
          <h3 className="font-serif text-xl font-bold text-ink">
            <Link href={href} className="inline-flex min-h-[44px] items-center hover:text-primary">
              {tutor.name}
            </Link>
          </h3>
          <p className="text-sm text-ink-muted">South African tutor</p>
          {hasReviews && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <StarRating rating={tutor.rating} size="sm" showNumber={false} />
              <span className="text-sm font-semibold text-ink">
                {tutor.rating.toFixed(1)} <span className="font-normal text-ink-muted">({tutor.review_count} reviews)</span>
              </span>
            </div>
          )}
        </div>

        {tutor.bio && <p className="line-clamp-3 text-sm leading-relaxed text-ink-muted">{tutor.bio}</p>}

        {tutor.specialties.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label="Lesson topics">
            {tutor.specialties.slice(0, 3).map((spec) => (
              <li key={spec} className="rounded-full bg-cream-surface px-3 py-1 text-sm font-medium text-ink">
                {spec}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-auto flex flex-col gap-3 border-t border-divider pt-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="leading-tight">
            <LessonPriceLabel className="font-serif text-lg font-bold text-ink" />
            <div className="text-sm text-ink-muted">per 25 minutes</div>
          </div>
          <Link
            href={href}
            className="inline-flex min-h-[44px] items-center justify-center gap-1.5 whitespace-nowrap rounded-xl bg-teal px-5 text-sm font-bold text-white transition-colors hover:bg-teal-hover"
          >
            View profile <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </article>
  );
}
