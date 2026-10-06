"use client";

import Link from "next/link";
import { ArrowRight, Clock, Zap } from "lucide-react";
import type { PublicTutor } from "@/types/tutor";
import { StarRating } from "@/components/ui/StarRating";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import { TutorPortrait } from "@/components/public/TutorPortrait";
import { AudioSnippetButton } from "./AudioSnippetButton";

const ACCENT_NAMES: Record<string, string> = { ZA: "South African tutor", UK: "British tutor", US: "American tutor", OTHER: "International tutor" };

/** The API may send a code ("ZA") or a ready name; show a name either way. */
function accentName(value: string | undefined): string {
  if (!value) return "Tutor";
  return ACCENT_NAMES[value] ?? value;
}

interface TutorCardProps {
  tutor: PublicTutor;
}

/** Photo-first card, the same look as the home page. Only real review numbers are shown. */
export function TutorCard({ tutor }: TutorCardProps) {
  const profileUrl = `/tutors/${tutor.slug || tutor.id}`;
  const hasReviews = tutor.rating_count > 0 && tutor.rating_avg > 0;

  return (
    <article className="group flex flex-col overflow-hidden rounded-3xl border border-divider bg-white shadow-card transition-shadow hover:shadow-card-hover">
      <div className="relative">
        <Link href={profileUrl} tabIndex={-1} aria-label={`View ${tutor.full_name}'s profile`} className="block">
          <TutorPortrait
            src={tutor.avatar_url}
            name={tutor.full_name}
            className="aspect-[4/5] w-full"
            sizes="(min-width: 1024px) 30vw, (min-width: 640px) 45vw, 92vw"
          />
        </Link>
        {tutor.intro_audio_url && (
          <div className="absolute right-3 top-3">
            <AudioSnippetButton audioUrl={tutor.intro_audio_url} tutorName={tutor.first_name} size="sm" />
          </div>
        )}
        {tutor.has_inverter_backup && (
          <span className="absolute bottom-3 left-3 inline-flex items-center gap-1.5 rounded-full bg-sun px-3 py-1 text-sm font-bold text-ink">
            <Zap className="h-4 w-4" aria-hidden="true" /> Backup power
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-5">
        <div>
          <h3 className="font-serif text-xl font-bold text-ink">
            <Link href={profileUrl} className="inline-flex min-h-[44px] items-center hover:text-primary">
              {tutor.full_name}
            </Link>
          </h3>
          <p className="text-sm text-ink-muted">{accentName(tutor.accent_display || tutor.accent)}</p>
          {hasReviews && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <StarRating rating={tutor.rating_avg} size="sm" showNumber={false} />
              <span className="text-sm font-semibold text-ink">
                {tutor.rating_avg.toFixed(1)} <span className="font-normal text-ink-muted">({tutor.rating_count} reviews)</span>
              </span>
            </div>
          )}
        </div>

        {tutor.headline && <p className="line-clamp-2 text-base font-medium leading-snug text-ink">{tutor.headline}</p>}

        {tutor.specialties.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label="Lesson topics">
            {tutor.specialties.slice(0, 3).map((spec) => (
              <li key={spec} className="rounded-full bg-peach-soft px-3 py-1 text-sm font-medium text-ink">
                {spec}
              </li>
            ))}
          </ul>
        )}

        {tutor.next_available_slot && (
          <p className="flex items-center gap-2 rounded-2xl bg-sky-soft px-3 py-2 text-sm text-ink">
            <Clock className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              Next time: <strong>{tutor.next_available_slot.local_display}</strong>
            </span>
          </p>
        )}

        <div className="mt-auto flex flex-col gap-3 border-t border-divider pt-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="leading-tight">
            <LessonPriceLabel className="font-serif text-lg font-bold text-ink" />
            <div className="text-sm text-ink-muted">per 25 minutes</div>
          </div>
          <Link
            href={profileUrl}
            className="inline-flex min-h-[44px] items-center justify-center gap-1.5 whitespace-nowrap rounded-full bg-primary px-5 text-base font-bold text-white transition-colors hover:bg-primary-hover"
          >
            See times <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </article>
  );
}
