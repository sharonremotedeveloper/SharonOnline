"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Zap } from "lucide-react";
import { api } from "@/lib/api";
import type { PublicTutor } from "@/types/tutor";
import { toPublicTutor } from "@/lib/tutorsDirectory";
import { errorMessage } from "@/lib/http";
import { LessonScheduler } from "@/components/booking/LessonScheduler";
import { Avatar } from "@/components/ui/Avatar";
import { StarRating } from "@/components/ui/StarRating";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import { formatRating } from "@/lib/rating";

export default function StudentBookingPage() {
  const params = useParams();
  const tutorId = params?.tutorId as string;
  const [tutor, setTutor] = useState<PublicTutor | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!tutorId) return;
    let active = true;
    void api
      .getTutor(tutorId)
      .then((row) => {
        if (active) setTutor(toPublicTutor(row as Record<string, unknown>));
      })
      .catch((err) => {
        if (active) setError(errorMessage(err, "This tutor could not be loaded."));
      });
    return () => {
      active = false;
    };
  }, [tutorId]);

  const hasReviews = !!tutor && tutor.rating_count > 0 && tutor.rating_avg > 0;

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-6 lg:py-10">
      <Link
        href={`/tutors/${tutorId}`}
        className="inline-flex min-h-[44px] items-center gap-2 text-base font-semibold text-cocoa hover:text-cocoa-hover"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to tutor profile
      </Link>

      <h1 className="font-serif text-3xl font-bold text-ink sm:text-4xl">Choose your lesson time</h1>

      {error && <p role="alert" className="rounded-2xl border border-error/30 bg-error-surface p-4 text-base text-error">{error}</p>}

      {tutor && (
        <div className="flex flex-col gap-4 rounded-3xl border border-divider bg-white p-5 shadow-card sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <Avatar src={tutor.avatar_url} name={tutor.full_name} size="lg" />
            <div>
              <p className="font-serif text-xl font-bold text-ink">{tutor.full_name}</p>
              {tutor.headline && <p className="line-clamp-1 text-base text-ink-muted">{tutor.headline}</p>}
              {hasReviews && (
                <div className="mt-1 flex items-center gap-1.5">
                  <StarRating rating={tutor.rating_avg} size="sm" showNumber={false} />
                  <span className="text-sm font-semibold text-ink">
                    {formatRating(tutor.rating_avg)} <span className="font-normal text-ink-muted">({tutor.rating_count})</span>
                  </span>
                </div>
              )}
            </div>
          </div>
          <div className="border-t border-divider pt-3 text-left sm:border-t-0 sm:pt-0 sm:text-right">
            <LessonPriceLabel className="font-serif text-2xl font-bold text-ink" />
            <span className="ml-1 text-sm text-ink-muted">per 25-minute lesson</span>
            {tutor.has_inverter_backup && (
              <p className="mt-1 flex items-center gap-1.5 text-sm text-ink-muted sm:justify-end">
                <Zap className="h-4 w-4 text-cocoa" aria-hidden="true" /> Tutor has backup power
              </p>
            )}
          </div>
        </div>
      )}

      <div className="rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-8">
        {tutorId && (
          <LessonScheduler
            tutorId={tutorId}
            tutorName={tutor ? tutor.first_name || tutor.full_name : "your tutor"}
            returnTo={`/student/book/${tutorId}`}
          />
        )}
      </div>
    </div>
  );
}
