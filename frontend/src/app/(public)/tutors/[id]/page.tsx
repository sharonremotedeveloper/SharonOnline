"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  Star,
  ShieldCheck,
  Zap,
  Globe,
  Award,
  Video,
  Clock,
  ArrowLeft,
  CheckCircle2,
  Calendar,
} from "lucide-react";
import { PublicTutor } from "@/types/tutor";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { StarRating } from "@/components/ui/StarRating";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import { VideoReelPlayer } from "@/components/tutors/VideoReelPlayer";
import { AudioSnippetButton } from "@/components/tutors/AudioSnippetButton";
import { TutorReviewList } from "@/components/tutors/TutorReviewList";
import { InlineSlotMatrix } from "@/components/tutors/InlineSlotMatrix";

const SAMPLE_TUTORS: Record<string, PublicTutor> = {
  "tut-1": {
    id: "tut-1",
    user_id: "usr-sharon",
    slug: "sharon-m",
    full_name: "Sharon M.",
    first_name: "Sharon",
    last_name: "M.",
    headline: "Senior ESL Specialist · 10+ Yrs Experience (Japan & Korea Focus)",
    bio: "Hi there! I am Sharon, an experienced ESL educator based in South Africa. Over the past decade, I have coached more than 1,800 students across Tokyo, Osaka, Seoul, and Munich.\n\nMy lessons are focused on building practical workplace fluency, mastering executive presentation delivery, and softening pronunciation hurdles. You will receive an extensive Lesson Memo after every 25-minute class detailing your exact grammar corrections and vocabulary cards.",
    accent: "ZA",
    accent_display: "South African (Neutral RP)",
    country: "South Africa",
    country_flag: "🇿🇦",
    timezone: "Africa/Johannesburg",
    avatar_url: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&q=80",
    intro_video_url: "https://assets.mixkit.co/videos/preview/mixkit-woman-talking-on-video-call-41292-large.mp4",
    intro_video_thumbnail: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=800&q=80",
    rating_avg: 4.98,
    rating_count: 142,
    lessons_completed: 1840,
    specialties: ["Business English", "Interview Prep", "FreeTalk", "Pronunciation & Accent"],
    learning_goals: ["business", "interview", "conversation"],
    learner_levels: "A2 to C2 All Levels",
    has_inverter_backup: true,
  },
  "tut-2": {
    id: "tut-2",
    user_id: "usr-david",
    slug: "david-k",
    full_name: "David K.",
    first_name: "David",
    last_name: "K.",
    headline: "Cambridge Certified CELTA Coach · IELTS Speaking Examiner",
    bio: "Welcome! I specialize in high-stakes English examinations and technical business roleplays. My teaching philosophy is pragmatic and outcome-driven.",
    accent: "ZA",
    accent_display: "South African (Standard)",
    country: "South Africa",
    country_flag: "🇿🇦",
    timezone: "Africa/Johannesburg",
    avatar_url: "https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&w=400&q=80",
    intro_video_url: "https://assets.mixkit.co/videos/preview/mixkit-man-having-a-video-call-on-a-laptop-41288-large.mp4",
    rating_avg: 4.95,
    rating_count: 98,
    lessons_completed: 1120,
    specialties: ["IELTS Prep", "Grammar Mastery", "Daily News", "Interview Prep"],
    learning_goals: ["interview", "presentation"],
    learner_levels: "B1 to C2 Intermediate to Advanced",
    has_inverter_backup: true,
  },
  "tut-3": {
    id: "tut-3",
    user_id: "usr-elena",
    slug: "elena-v",
    full_name: "Elena V.",
    first_name: "Elena",
    last_name: "V.",
    headline: "Conversational English Tutor · Beginners & Travel Specialist",
    bio: "Hello! My goal is to make speaking English joyful and stress-free. We practice real-life travel situations and everyday small talk.",
    accent: "UK",
    accent_display: "British / South African",
    country: "United Kingdom",
    country_flag: "🇬🇧",
    timezone: "Europe/London",
    avatar_url: "https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=400&q=80",
    intro_video_url: "https://assets.mixkit.co/videos/preview/mixkit-young-woman-in-online-meeting-41290-large.mp4",
    rating_avg: 4.92,
    rating_count: 86,
    lessons_completed: 780,
    specialties: ["FreeTalk", "Daily News", "Grammar Mastery"],
    learning_goals: ["conversation", "travel"],
    learner_levels: "A1 to B2 Beginner to Intermediate",
    has_inverter_backup: false,
  },
};

export default function TutorProfilePage() {
  const params = useParams();
  const router = useRouter();
  const tutorId = (params?.id as string) || "tut-1";

  const tutor: PublicTutor =
    SAMPLE_TUTORS[tutorId] ||
    Object.values(SAMPLE_TUTORS).find((t) => t.slug === tutorId) ||
    SAMPLE_TUTORS["tut-1"];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* Back button */}
      <div>
        <Link
          href="/tutors"
          className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to All Tutors
        </Link>
      </div>

      {/* Main Showcase Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Video Reel, Bio & Reviews */}
        <div className="lg:col-span-2 space-y-8">
          {/* Video Audition Player */}
          <VideoReelPlayer
            videoUrl={tutor.intro_video_url}
            posterUrl={tutor.intro_video_thumbnail || tutor.avatar_url}
            tutorName={tutor.full_name}
            headline={tutor.headline}
          />

          {/* Profile Overview Card */}
          <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-6">
              <div className="flex items-center gap-4">
                <Avatar src={tutor.avatar_url} name={tutor.full_name} size="xl" />
                <div>
                  <div className="flex items-center gap-2">
                    <h1 className="text-2xl font-extrabold text-ink font-serif">{tutor.full_name}</h1>
                    <span className="text-xl" title={tutor.country}>{tutor.country_flag}</span>
                  </div>
                  <div className="text-xs text-ink-muted font-medium mt-0.5">{tutor.accent_display}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <StarRating rating={tutor.rating_avg} size="sm" />
                    <span className="text-xs font-bold text-ink">
                      {tutor.rating_avg.toFixed(2)} ({tutor.rating_count} reviews)
                    </span>
                    <span className="text-xs text-ink-muted">· {tutor.lessons_completed} lessons</span>
                  </div>
                </div>
              </div>

              <div className="flex sm:flex-col items-center sm:items-end gap-2">
                <AudioSnippetButton audioUrl={tutor.intro_audio_url} tutorName={tutor.first_name} />
                <span className="text-[11px] text-ink-muted">15-sec accent sample</span>
              </div>
            </div>

            {/* Badges / Guarantees */}
            <div className="flex flex-wrap gap-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-cream-surface border border-cream-deep text-teal">
                <ShieldCheck className="w-3.5 h-3.5 text-accent" /> TEFL Certified & ID Verified
              </span>

              {tutor.has_inverter_backup && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-50 border border-amber-200 text-amber-900">
                  <Zap className="w-3.5 h-3.5 text-accent" /> 100% Load-Shedding Immune (Inverter Backup)
                </span>
              )}

              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-cream-surface border border-cream-deep text-ink-muted">
                <Award className="w-3.5 h-3.5 text-primary" /> Levels: {tutor.learner_levels}
              </span>
            </div>

            {/* About / Bio */}
            <div className="space-y-3">
              <h3 className="text-lg font-bold text-ink font-serif">About {tutor.first_name}</h3>
              <p className="text-xs sm:text-sm text-ink-muted leading-relaxed whitespace-pre-line">
                {tutor.bio}
              </p>
            </div>

            {/* Teaching Specialties */}
            <div className="space-y-3 pt-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-primary">Teaching Specialties</h3>
              <div className="flex flex-wrap gap-2">
                {tutor.specialties.map((spec) => (
                  <Badge key={spec} variant="neutral" size="md">
                    {spec}
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          {/* Student Reviews */}
          <TutorReviewList
            ratingAvg={tutor.rating_avg}
            ratingCount={tutor.rating_count}
          />
        </div>

        {/* Right Column: Booking Matrix & Guarantees */}
        <div className="space-y-6">
          {/* Quick Pricing Summary Card */}
          <div className="bg-teal text-white rounded-3xl p-6 shadow-card space-y-4">
            <div className="text-xs font-bold uppercase tracking-wider text-accent-surface">
              Private 1-on-1 Lesson Rate
            </div>
            <div className="flex items-baseline gap-2">
              <LessonPriceLabel className="text-4xl font-extrabold font-serif text-white" />
              <span className="text-xs text-white/70">USD / 25-minute class</span>
            </div>

            <p className="text-xs text-white/80 leading-relaxed">
              Or use <span className="font-bold text-accent">1 Lesson Credit</span> from your pack.
            </p>

            <div className="border-t border-white/10 pt-3 space-y-2 text-xs text-white/80">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-accent" />
                <span>Instant 1-Click Zoom meeting link</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-accent" />
                <span>Personalized Lesson Memo & Vocab Cards</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-accent" />
                <span>Free reschedule up to 2h prior</span>
              </div>
            </div>
          </div>

          {/* Inline 7-Day Slot Matrix */}
          <InlineSlotMatrix
            tutorId={tutor.id}
            tutorName={tutor.full_name}
          />
        </div>
      </div>
    </div>
  );
}
