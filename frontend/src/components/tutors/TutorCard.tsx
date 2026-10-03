"use client";

import Link from "next/link";
import { Star, ShieldCheck, Zap, ArrowRight, Clock, Video } from "lucide-react";
import { PublicTutor } from "@/types/tutor";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { StarRating } from "@/components/ui/StarRating";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import { AudioSnippetButton } from "./AudioSnippetButton";

interface TutorCardProps {
  tutor: PublicTutor;
}

export function TutorCard({ tutor }: TutorCardProps) {
  const profileUrl = `/tutors/${tutor.slug || tutor.id}`;

  return (
    <div className="bg-white rounded-3xl border border-divider shadow-card hover:shadow-card-hover transition-all flex flex-col justify-between overflow-hidden group">
      {/* Header section with photo, accent & audio */}
      <div className="p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <Link href={profileUrl}>
              <Avatar
                src={tutor.avatar_url}
                name={tutor.full_name}
                size="lg"
                className="ring-2 ring-cream-deep group-hover:scale-105 transition-transform"
              />
            </Link>

            <div>
              <div className="flex items-center gap-1.5">
                <Link href={profileUrl}>
                  <h3 className="text-lg font-bold text-ink font-serif hover:text-teal transition-colors">
                    {tutor.full_name}
                  </h3>
                </Link>
                <span title={`From ${tutor.country}`}>{tutor.country_flag}</span>
              </div>

              <div className="text-xs text-ink-muted font-medium mt-0.5">
                {tutor.accent_display || tutor.accent}
              </div>

              <div className="flex items-center gap-1.5 mt-1">
                <StarRating rating={tutor.rating_avg} size="sm" />
                <span className="text-xs font-bold text-ink">
                  {tutor.rating_avg.toFixed(2)} ({tutor.rating_count})
                </span>
                <span className="text-[10px] text-ink-faint">· {tutor.lessons_completed} lessons</span>
              </div>
            </div>
          </div>

          <AudioSnippetButton
            audioUrl={tutor.intro_audio_url}
            tutorName={tutor.first_name}
            size="sm"
          />
        </div>

        {/* Headline & Bio */}
        <div>
          <h4 className="text-xs font-bold text-teal line-clamp-1">{tutor.headline}</h4>
          <p className="text-xs text-ink-muted line-clamp-2 mt-1 leading-relaxed">{tutor.bio}</p>
        </div>

        {/* Specialties / Badges */}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {tutor.specialties.slice(0, 3).map((spec) => (
            <Badge key={spec} variant="neutral" size="sm">
              {spec}
            </Badge>
          ))}
          {tutor.has_inverter_backup && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
              <Zap className="w-3 h-3 text-accent" /> Power Guard
            </span>
          )}
        </div>

        {/* Next Available Slot Preview */}
        {tutor.next_available_slot && (
          <div className="bg-cream-surface rounded-xl px-3 py-2 border border-cream-deep flex items-center justify-between text-[11px]">
            <span className="text-ink-muted flex items-center gap-1 font-medium">
              <Clock className="w-3.5 h-3.5 text-teal" /> Next Open:
            </span>
            <span className="font-bold text-ink">{tutor.next_available_slot.local_display}</span>
          </div>
        )}
      </div>

      {/* Footer CTA & Pricing */}
      <div className="p-4 bg-cream-surface/60 border-t border-divider flex items-center justify-between">
        <div>
          <LessonPriceLabel className="text-base font-extrabold text-ink font-serif" />
          <span className="text-[11px] text-ink-muted"> / 25 min</span>
        </div>

        <div className="flex items-center gap-2">
          {tutor.intro_video_url && (
            <Link
              href={profileUrl}
              title="Watch 60s video intro"
              className="p-2 rounded-xl bg-white hover:bg-cream-deep border border-divider text-ink-muted hover:text-ink transition-colors"
            >
              <Video className="w-4 h-4 text-primary" />
            </Link>
          )}

          <Link
            href={profileUrl}
            className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl transition-all shadow-sm flex items-center gap-1"
          >
            <span>Book Slot</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}
