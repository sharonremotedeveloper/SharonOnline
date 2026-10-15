import type { PublicTutor, TutorFilterState } from "@/types/tutor";

export function getTutorDirectoryEmptyState(filters: TutorFilterState) {
  const hasActiveFilters = Boolean(
    filters.search.trim() || filters.accent || filters.specialty || filters.only_power_guard || filters.only_today,
  );
  return hasActiveFilters
    ? {
        heading: "No tutors match these filters",
        description: "Try changing your search or removing a filter.",
        showReset: true,
      }
    : {
        heading: "No tutors available yet",
        description: "We're preparing the tutor directory. Please check back soon.",
        showReset: false,
      };
}

export function buildTutorQuery(input: Partial<Pick<TutorFilterState, "search" | "accent" | "specialty" | "only_power_guard" | "only_today">> & { page?: number; pageSize?: number }): string {
  const query = new URLSearchParams();
  if (input.search?.trim()) query.set("search", input.search.trim());
  if (input.accent) query.set("accent", input.accent);
  if (input.specialty) query.set("specialty", input.specialty);
  if (input.only_power_guard) query.set("backup_power", "true");
  if (input.only_today) query.set("free_next_24h", "true");
  if (input.page && input.page > 1) query.set("page", String(input.page));
  if (input.pageSize) query.set("page_size", String(input.pageSize));
  return query.toString();
}

export function toPublicTutor(raw: Record<string, unknown>): PublicTutor {
  const name = String(raw.full_name || `${raw.first_name || ""} ${raw.last_name || ""}`).trim() || "Tutor";
  const specialties = Array.isArray(raw.specialties) ? raw.specialties.map(String) : [];
  return {
    id: String(raw.id), user_id: String(raw.user_id || ""), full_name: name,
    first_name: String(raw.first_name || name.split(" ")[0] || ""), last_name: String(raw.last_name || ""),
    headline: String(raw.headline || "English tutor"), bio: String(raw.bio || raw.headline || ""),
    accent: (String(raw.accent || "OTHER") as PublicTutor["accent"]), accent_display: String(raw.accent_display || raw.accent || ""),
    country: String(raw.country || ""), country_flag: String(raw.country_flag || ""), timezone: String(raw.timezone || "UTC"),
    avatar_url: typeof raw.avatar_url === "string" ? raw.avatar_url : undefined,
    intro_video_url: typeof raw.intro_video_url === "string" ? raw.intro_video_url : undefined,
    intro_video_thumbnail: typeof raw.intro_video_thumbnail === "string" ? raw.intro_video_thumbnail : undefined,
    intro_audio_url: typeof raw.intro_audio_url === "string" ? raw.intro_audio_url : undefined,
    rating_avg: Number(raw.rating_avg || 0), rating_count: Number(raw.rating_count || 0), lessons_completed: Number(raw.lessons_completed || 0),
    specialties, learning_goals: [], learner_levels: "All levels", has_inverter_backup: Boolean(raw.has_inverter_backup),
  };
}
