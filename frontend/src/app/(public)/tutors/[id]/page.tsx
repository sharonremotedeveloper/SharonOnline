"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ShieldCheck, Star, Zap, Globe2, BookOpen } from "lucide-react";
import type { PublicTutor } from "@/types/tutor";
import { api } from "@/lib/api";
import { toPublicTutor } from "@/lib/tutorsDirectory";
import { errorMessage } from "@/lib/http";
import { LessonScheduler } from "@/components/booking/LessonScheduler";
import { VideoReelPlayer } from "@/components/tutors/VideoReelPlayer";
import { AudioSnippetButton } from "@/components/tutors/AudioSnippetButton";
import { TutorPortrait } from "@/components/public/TutorPortrait";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";

/** "ZA" becomes "South Africa"; a value that is already a name is left alone. */
function countryName(value: string): string {
  if (!/^[A-Za-z]{2}$/.test(value)) return value;
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(value.toUpperCase()) ?? value;
  } catch {
    return value;
  }
}

function ProfileSkeleton() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8" role="status" aria-label="Loading tutor">
      <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
        <div className="h-[28rem] animate-pulse rounded-3xl bg-cream-deep/60" />
        <div className="h-[34rem] animate-pulse rounded-3xl bg-cream-deep/60" />
      </div>
    </div>
  );
}

export default function TutorProfilePage() {
  const { id } = useParams<{ id: string }>();
  const [tutor, setTutor] = useState<PublicTutor | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void api
      .getTutor(id)
      .then((row) => {
        if (active) setTutor(toPublicTutor(row as Record<string, unknown>));
      })
      .catch((err) => {
        if (active) setError(errorMessage(err, "This tutor could not be loaded."));
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 text-center">
        <h1 className="font-serif text-3xl font-bold text-ink">We could not open this tutor</h1>
        <p className="mt-3 text-base text-ink-muted">{error}</p>
        <Link href="/tutors" className="mt-6 inline-flex min-h-[48px] items-center rounded-xl bg-cocoa px-6 font-bold text-white hover:bg-cocoa-hover">
          See all tutors
        </Link>
      </div>
    );
  }

  if (!tutor) return <ProfileSkeleton />;

  const hasReviews = tutor.rating_count > 0 && tutor.rating_avg > 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <Link href="/tutors" className="inline-flex min-h-[44px] items-center gap-2 text-base font-semibold text-cocoa hover:text-cocoa-hover">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> All tutors
      </Link>

      <div className="mt-4 grid items-start gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          {/* Only a real intro video is played; otherwise the tutor's photo is shown */}
          {tutor.intro_video_url ? (
            <VideoReelPlayer
              videoUrl={tutor.intro_video_url}
              posterUrl={tutor.intro_video_thumbnail || tutor.avatar_url}
              tutorName={tutor.full_name}
              headline={tutor.headline}
            />
          ) : (
            <div className="overflow-hidden rounded-3xl border border-divider shadow-card">
              <TutorPortrait
                src={tutor.avatar_url}
                name={tutor.full_name}
                className="aspect-[16/10] w-full"
                sizes="(min-width: 1024px) 55vw, 100vw"
                priority
              />
            </div>
          )}

          <article className="rounded-3xl border border-divider bg-white p-6 shadow-card sm:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h1 className="font-serif text-3xl font-bold text-ink sm:text-4xl">{tutor.full_name}</h1>
                {tutor.headline && <p className="mt-2 text-lg text-ink-muted">{tutor.headline}</p>}
              </div>
              {tutor.intro_audio_url && <AudioSnippetButton audioUrl={tutor.intro_audio_url} tutorName={tutor.full_name} />}
            </div>

            <ul className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-base text-ink">
              {hasReviews && (
                <li className="flex items-center gap-1.5">
                  <Star className="h-5 w-5 fill-star text-star" aria-hidden="true" />
                  <span className="font-bold">{tutor.rating_avg.toFixed(1)}</span>
                  <span className="text-ink-muted">({tutor.rating_count} reviews)</span>
                </li>
              )}
              <li className="flex items-center gap-1.5">
                <ShieldCheck className="h-5 w-5 text-cocoa" aria-hidden="true" /> Checked by our team
              </li>
              {tutor.country && (
                <li className="flex items-center gap-1.5">
                  <Globe2 className="h-5 w-5 text-cocoa" aria-hidden="true" /> Teaches from {countryName(tutor.country)}
                </li>
              )}
              {tutor.has_inverter_backup && (
                <li className="flex items-center gap-1.5">
                  <Zap className="h-5 w-5 text-cocoa" aria-hidden="true" /> Backup power
                </li>
              )}
            </ul>

            {tutor.specialties.length > 0 && (
              <div className="mt-6">
                <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-primary">
                  <BookOpen className="h-4 w-4" aria-hidden="true" /> Lesson topics
                </h2>
                <ul className="mt-2 flex flex-wrap gap-2">
                  {tutor.specialties.map((s) => (
                    <li key={s} className="rounded-full bg-cream-surface px-3.5 py-1.5 text-base font-medium text-ink">
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {tutor.bio && (
              <div className="mt-6">
                <h2 className="text-sm font-bold uppercase tracking-wider text-primary">About {tutor.first_name || tutor.full_name}</h2>
                <p className="mt-2 max-w-prose whitespace-pre-line text-lg leading-relaxed text-ink-muted">{tutor.bio}</p>
              </div>
            )}
          </article>
        </div>

        {/* Booking: stays in view while the profile scrolls on large screens */}
        <aside aria-labelledby="book-heading" className="min-w-0 rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-6 lg:sticky lg:top-24">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-2 border-b border-divider pb-4">
            <div>
              <h2 id="book-heading" className="font-serif text-2xl font-bold text-ink">
                Book a lesson
              </h2>
              <p className="text-base text-ink-muted">25 minutes, 1-on-1, by video</p>
            </div>
            <p className="text-right leading-tight">
              <LessonPriceLabel className="font-serif text-2xl font-bold text-ink" />
              <span className="block text-sm text-ink-muted">per lesson</span>
            </p>
          </div>
          <LessonScheduler tutorId={tutor.id} tutorName={tutor.first_name || tutor.full_name} returnTo={`/tutors/${id}`} />
        </aside>
      </div>
    </div>
  );
}
