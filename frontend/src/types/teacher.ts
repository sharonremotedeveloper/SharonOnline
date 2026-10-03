import type { components } from "./api.generated";

export type EskomStatus = components["schemas"]["EskomStatus"];
export type PowerBackupInput = components["schemas"]["PatchedPowerBackupRequest"];

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
