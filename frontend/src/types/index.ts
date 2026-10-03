import type { components } from './api.generated';

export type UserRole = 'student' | 'teacher' | 'admin';

export interface User {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  country: string;
  timezone: string;
  phone_number?: string;
  created_at: string;
}

export interface TeacherAvailability {
  id: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
}

export type TeacherAccent = 'ZA' | 'UK' | 'US' | 'OTHER';

export interface Teacher {
  id: string;
  user_id: string;
  full_name: string;
  first_name: string;
  last_name: string;
  headline?: string;
  bio?: string;
  accent: TeacherAccent;
  avatar_url?: string;
  intro_video_url?: string;
  intro_video_thumbnail?: string;
  rating_avg: number | string;
  rating_count: number;
  price_per_25min_usd: number | string;
  specialties: string[];
  country: string;
  is_verified: boolean;
  timezone?: string;
  availabilities?: TeacherAvailability[];
}

export interface Slot {
  start_time_utc: string;
  end_time_utc: string;
  local_date: string;
  local_start_time: string;
  local_end_time: string;
  viewer_timezone: string;
  status: 'available' | 'booked' | 'reserved';
  is_bookable: boolean;
}

export interface TeacherSlotsResponse {
  teacher_id: string;
  teacher_name: string;
  viewer_timezone: string;
  slot_count: number;
  slots: Slot[];
}

export type BookingStatus = components['schemas']['BookingStatusEnum'];

export interface LessonMemo {
  id: string;
  booking: string;
  feedback_text: string;
  vocabulary_words: Array<{ word: string; definition?: string } | string>;
  pronunciation_notes?: string;
  homework?: string;
  submitted_at: string;
}

export interface Booking {
  id: string;
  teacher: Teacher;
  student: User;
  material?: Material;
  status: BookingStatus;
  start_time_utc: string;
  end_time_utc: string;
  zoom_url?: string;
  zoom_password?: string;
  student_rating?: number;
  student_review?: string;
  memo?: LessonMemo;
  created_at: string;
}

import { CEFRLevel } from './material';
export * from './material';

export interface Material {
  id: string;
  title: string;
  slug: string;
  category: 'daily_news' | 'freetalk' | 'business' | 'test_prep' | 'pronunciation' | 'grammar';
  category_display: string;
  cefr_level: CEFRLevel;
  cefr_display: string;
  description: string;
  content_html?: string;
  pdf_file_url?: string;
}

export * from './teacher';
export * from './admin';
export * from './student';
