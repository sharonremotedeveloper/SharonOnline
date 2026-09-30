export type CEFRLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2";

export type MaterialCategory =
  | "daily_news"
  | "business"
  | "freetalk"
  | "test_prep"
  | "pronunciation"
  | "grammar";

export interface VocabularyItem {
  id: string;
  word: string;
  phonetic: string;
  part_of_speech: string;
  definition: string;
  example_sentence: string;
}

export interface MaterialDetail {
  id: string;
  title: string;
  slug: string;
  category: MaterialCategory;
  category_display: string;
  cefr_level: CEFRLevel;
  cefr_display: string;
  estimated_minutes: number;
  summary: string;
  content_html: string;
  vocabulary: VocabularyItem[];
  discussion_questions: string[];
  pdf_file_url?: string;
  downloads_count?: number;
  created_at?: string;
}

export interface MaterialFilterState {
  search: string;
  category: string;
  cefr_level: string;
}
