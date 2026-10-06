import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { FeaturedTeacher } from "@/lib/api";
import { StarRating } from "@/components/ui/StarRating";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import { TutorPortrait } from "./TutorPortrait";

/**
 * Compact tutor card: a square photo beside the details, so three fit on one row without the page becoming a wall of
 * portraits. The full portrait lives on the tutor's own page. Rating only shows when there are real reviews.
 */
export function FeaturedTutorCard({ tutor }: { tutor: FeaturedTeacher }) {
  const href = `/tutors/${tutor.slug || tutor.id}`;
  const hasReviews = tutor.review_count > 0 && tutor.rating > 0;

  return (
    <article className="flex gap-4 rounded-3xl border border-divider bg-white p-4 shadow-card transition-shadow hover:shadow-card-hover">
      <Link href={href} tabIndex={-1} aria-label={`View ${tutor.name}'s profile`} className="shrink-0 self-start">
        <TutorPortrait
          src={tutor.avatar}
          name={tutor.name}
          className="aspect-square w-24 rounded-2xl sm:w-28"
          sizes="112px"
        />
      </Link>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div>
          <h3 className="font-serif text-lg font-bold leading-tight text-ink">
            <Link href={href} className="hover:text-primary">
              {tutor.name}
            </Link>
          </h3>
          <p className="text-sm text-ink-muted">South African tutor</p>
          {hasReviews && (
            <div className="mt-1 flex items-center gap-1.5">
              <StarRating rating={tutor.rating} size="sm" showNumber={false} />
              <span className="text-sm font-semibold text-ink">
                {tutor.rating.toFixed(1)} <span className="font-normal text-ink-muted">({tutor.review_count})</span>
              </span>
            </div>
          )}
        </div>

        {tutor.bio && <p className="line-clamp-2 text-sm leading-snug text-ink-muted">{tutor.bio}</p>}

        {tutor.specialties.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Lesson topics">
            {tutor.specialties.slice(0, 2).map((spec) => (
              <li key={spec} className="rounded-full bg-peach-soft px-2.5 py-0.5 text-sm font-medium text-ink">
                {spec}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-auto flex items-center justify-between gap-2 pt-1">
          <p className="leading-tight">
            <LessonPriceLabel className="font-serif text-base font-bold text-ink" />
            <span className="text-sm text-ink-muted"> / 25 min</span>
          </p>
          <Link
            href={href}
            className="inline-flex min-h-[44px] items-center gap-1 whitespace-nowrap rounded-full bg-cocoa px-4 text-sm font-bold text-white transition-colors hover:bg-cocoa-hover"
          >
            View <ArrowRight className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only"> {tutor.name}&apos;s profile</span>
          </Link>
        </div>
      </div>
    </article>
  );
}
