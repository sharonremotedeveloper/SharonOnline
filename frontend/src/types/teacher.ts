import type { components } from "./api.generated";

export interface EskomStatus {
  stage: number; // 0 to 6
  area_name: string; // e.g. "City of Johannesburg Block 3 - Rosebank/Sandton"
  next_outage_start?: string;
  next_outage_end?: string;
  has_inverter_backup: boolean;
  has_lte_failover: boolean;
  last_updated?: string;
}

export interface VocabularyTagItem {
  id: string;
  word: string;
  definition: string;
}

export interface PostLessonMemoInput {
  booking_id: string;
  feedback_text: string;
  vocabulary_words: VocabularyTagItem[];
  pronunciation_notes: string;
  grammar_notes: string;
  homework: string;
  next_steps: string;
}

export type TeacherPayoutBankAccountInput = components["schemas"]["PayoutAccountWriteRequest"];
export type TeacherPayoutBankAccount = components["schemas"]["PayoutAccountMasked"];
export type TeacherTransaction = components["schemas"]["TutorWalletTransaction"];
export type TeacherWalletData = components["schemas"]["TutorWallet"];

export interface WeeklyScheduleBlock {
  day_of_week: number; // 0 = Mon, 6 = Sun
  time_range: string; // "08:00 - 10:00"
  is_open: boolean;
}
