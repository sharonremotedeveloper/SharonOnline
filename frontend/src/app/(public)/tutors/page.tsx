"use client";

import { useState, useEffect, Suspense, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Users, Sparkles, Filter } from "lucide-react";
import { TutorFilters } from "@/components/tutors/TutorFilters";
import { TutorGrid } from "@/components/tutors/TutorGrid";
import { PublicTutor, TutorFilterState } from "@/types/tutor";
import { api } from "@/lib/api";

const FULL_TUTORS: PublicTutor[] = [
  {
    id: "tut-1",
    user_id: "usr-sharon",
    slug: "sharon-m",
    full_name: "Sharon M.",
    first_name: "Sharon",
    last_name: "M.",
    headline: "Senior ESL Specialist · 10+ Yrs Experience (Japan & Korea Focus)",
    bio: "Certified TEFL educator specializing in conversational fluency, business presentations, and accent softening for Japanese and Korean executives. Patient, structured, and warm.",
    accent: "ZA",
    accent_display: "South African (Neutral RP)",
    country: "South Africa",
    country_flag: "🇿🇦",
    timezone: "Africa/Johannesburg",
    avatar_url: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&q=80",
    intro_video_url: "https://assets.mixkit.co/videos/preview/mixkit-woman-talking-on-video-call-41292-large.mp4",
    intro_audio_url: "https://actions.google.com/sounds/v1/ambiences/outdoor_festival_crowd_distant.ogg",
    rating_avg: 4.98,
    rating_count: 142,
    lessons_completed: 1840,
    specialties: ["Business English", "Interview Prep", "FreeTalk", "Pronunciation & Accent"],
    learning_goals: ["business", "interview", "conversation"],
    learner_levels: "A2 to C2 All Levels",
    has_inverter_backup: true,
    next_available_slot: {
      start_time_utc: new Date(Date.now() + 3600000).toISOString(),
      local_display: "Today · 17:30 JST",
    },
  },
  {
    id: "tut-2",
    user_id: "usr-david",
    slug: "david-k",
    full_name: "David K.",
    first_name: "David",
    last_name: "K.",
    headline: "Cambridge Certified CELTA Coach · IELTS Speaking Examiner",
    bio: "Focuses on structured IELTS Band 7.5+ preparation, technical vocabulary acquisition, and formal job interview roleplays. Strict, insightful, with concrete correction notes.",
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
    next_available_slot: {
      start_time_utc: new Date(Date.now() + 7200000).toISOString(),
      local_display: "Today · 19:00 JST",
    },
  },
  {
    id: "tut-3",
    user_id: "usr-elena",
    slug: "elena-v",
    full_name: "Elena V.",
    first_name: "Elena",
    last_name: "V.",
    headline: "Conversational English Tutor · Beginners & Travel Specialist",
    bio: "Passionate about helping timid English learners build natural speaking confidence. Uses engaging visual flashcards, daily news articles, and cultural idioms.",
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
    next_available_slot: {
      start_time_utc: new Date(Date.now() + 86400000).toISOString(),
      local_display: "Tomorrow · 14:00 JST",
    },
  },
  {
    id: "tut-4",
    user_id: "usr-thabo",
    slug: "thabo-n",
    full_name: "Thabo N.",
    first_name: "Thabo",
    last_name: "N.",
    headline: "Tech & Corporate Communications Coach (Johannesburg)",
    bio: "Software engineering background. Specializes in assisting developers and tech product managers in Tokyo and Berlin with agile ceremonies, sprint demos, and executive standups.",
    accent: "ZA",
    accent_display: "South African (Neutral)",
    country: "South Africa",
    country_flag: "🇿🇦",
    timezone: "Africa/Johannesburg",
    avatar_url: "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?auto=format&fit=crop&w=400&q=80",
    rating_avg: 4.96,
    rating_count: 64,
    lessons_completed: 530,
    specialties: ["Business English", "Interview Prep", "Pronunciation & Accent"],
    learning_goals: ["business", "presentation"],
    learner_levels: "B2 to C2 Advanced",
    has_inverter_backup: true,
    next_available_slot: {
      start_time_utc: new Date(Date.now() + 10800000).toISOString(),
      local_display: "Today · 20:30 JST",
    },
  },
];

function TutorsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [filters, setFilters] = useState<TutorFilterState>({
    search: searchParams.get("search") || "",
    accent: searchParams.get("accent") || "",
    specialty: searchParams.get("specialty") || "",
    learning_goal: searchParams.get("goal") || "",
    max_price: searchParams.get("max_price") ? parseFloat(searchParams.get("max_price")!) : null,
    only_power_guard: searchParams.get("power_guard") === "true",
    only_today: searchParams.get("today") === "true",
  });

  const [tutors, setTutors] = useState<PublicTutor[]>(FULL_TUTORS);
  const [loading, setLoading] = useState(false);

  // Sync state to URL params for shareable search
  const handleFilterChange = (newFilters: TutorFilterState) => {
    setFilters(newFilters);
    const params = new URLSearchParams();
    if (newFilters.search) params.set("search", newFilters.search);
    if (newFilters.accent) params.set("accent", newFilters.accent);
    if (newFilters.specialty) params.set("specialty", newFilters.specialty);
    if (newFilters.learning_goal) params.set("goal", newFilters.learning_goal);
    if (newFilters.max_price) params.set("max_price", newFilters.max_price.toString());
    if (newFilters.only_power_guard) params.set("power_guard", "true");
    if (newFilters.only_today) params.set("today", "true");

    router.replace(`/tutors?${params.toString()}`);
  };

  // Filter computation
  const filteredTutors = useMemo(() => {
    return tutors.filter((t) => {
      // Search term
      if (filters.search) {
        const q = filters.search.toLowerCase();
        const matchesName = t.full_name.toLowerCase().includes(q);
        const matchesHeadline = t.headline.toLowerCase().includes(q);
        const matchesBio = t.bio.toLowerCase().includes(q);
        const matchesSpecialty = t.specialties.some((s) => s.toLowerCase().includes(q));
        if (!matchesName && !matchesHeadline && !matchesBio && !matchesSpecialty) {
          return false;
        }
      }

      // Accent filter
      if (filters.accent && t.accent !== filters.accent) {
        return false;
      }

      // Specialty filter
      if (filters.specialty && !t.specialties.includes(filters.specialty)) {
        return false;
      }

      // Power guard filter
      if (filters.only_power_guard && !t.has_inverter_backup) {
        return false;
      }

      // Today filter
      if (filters.only_today && !t.next_available_slot?.local_display.includes("Today")) {
        return false;
      }

      return true;
    });
  }, [tutors, filters]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Page Header */}
      <div className="space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cream-surface border border-divider text-xs font-bold text-teal">
          <Users className="w-3.5 h-3.5 text-accent" />
          <span>Vetted English Tutors · 100% Native & South African Accent Verification</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-ink font-serif tracking-tight">
          Find Your Perfect 25-Minute Tutor
        </h1>
        <p className="text-xs sm:text-sm text-ink-muted max-w-2xl">
          Watch 60-second video introductions, listen to 15-second accent samples, and book discrete 25-minute slots with instant 10-minute hold confirmation.
        </p>
      </div>

      {/* Faceted Filters Component */}
      <TutorFilters
        filters={filters}
        onFilterChange={handleFilterChange}
        totalCount={filteredTutors.length}
      />

      {/* Results Grid */}
      <TutorGrid
        tutors={filteredTutors}
        loading={loading}
        onResetFilters={() =>
          handleFilterChange({
            search: "",
            accent: "",
            specialty: "",
            learning_goal: "",
            max_price: null,
            only_power_guard: false,
            only_today: false,
          })
        }
      />
    </div>
  );
}

export default function TutorsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-xs text-ink-muted">Loading tutor directory...</div>}>
      <TutorsContent />
    </Suspense>
  );
}
