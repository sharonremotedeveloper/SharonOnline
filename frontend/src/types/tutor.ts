export type AccentType = "ZA" | "UK" | "US" | "OTHER";

export interface PublicTutor {
  id: string;
  user_id: string;
  slug?: string;
  full_name: string;
  first_name: string;
  last_name: string;
  headline: string;
  bio: string;
  accent: AccentType;
  accent_display: string;
  country: string;
  country_flag: string;
  timezone: string;
  avatar_url?: string;
  intro_video_url?: string;
  intro_video_thumbnail?: string;
  intro_audio_url?: string;
  rating_avg: number;
  rating_count: number;
  lessons_completed: number;
  specialties: string[];
  learning_goals: Array<"business" | "interview" | "conversation" | "presentation" | "travel">;
  learner_levels: string;
  has_inverter_backup: boolean;
  next_available_slot?: {
    start_time_utc: string;
    local_display: string;
  };
}

export interface TutorFilterState {
  search: string;
  accent: string;
  specialty: string;
  learning_goal: string;
  only_power_guard: boolean;
  only_today: boolean;
}

export interface TutorReview {
  id: string;
  student_name: string;
  student_country: string;
  student_flag: string;
  rating: number;
  date: string;
  comment: string;
  lesson_topic: string;
}
