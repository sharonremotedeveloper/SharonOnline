export interface StudentLessonItem {
  id: string;
  booking_reference: string;
  teacher: {
    id: string;
    name: string;
    avatar: string;
    accent: string;
  };
  start_time_utc: string;
  end_time_utc: string;
  local_date: string;
  local_start_time: string;
  local_end_time: string;
  viewer_timezone: string;
  material_title: string;
  material_cefr: string;
  material_slug?: string;
  status: "confirmed" | "completed" | "interrupted_power";
  zoom_url?: string;
  memo?: {
    id: string;
    feedback_text: string;
    vocabulary_words: Array<{ word: string; definition: string }>;
    pronunciation_notes: string;
    grammar_notes: string;
    homework: string;
    submitted_at: string;
  };
  review?: {
    rating: number;
    tags: string[];
    submitted_at: string;
  };
}

export interface StudentFlashcard {
  id: string;
  word: string;
  phonetic: string;
  part_of_speech: string;
  definition: string;
  example_sentence: string;
  lesson_source: string;
  mastery: "new" | "learning" | "mastered";
  review_count: number;
  next_review_due: string;
}

export interface StudentProfileData {
  id: string;
  full_name: string;
  email: string;
  country: string;
  timezone: string;
  target_level: string;
  learning_goals: string;
}

export interface TeacherStudentDossierItem {
  id: string;
  student_id: string;
  student_name: string;
  student_email: string;
  student_country: string;
  target_level: string;
  lessons_completed_count: number;
  last_lesson_date: string;
  private_pedagogical_notes: string;
  common_grammar_mistakes: string[];
}
