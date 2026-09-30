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

export interface TeacherPayoutBankAccount {
  bank_name: string;
  account_holder_name: string;
  account_number: string;
  account_number_masked?: string;
  branch_code: string;
  account_type: "cheque" | "savings";
  id_number?: string;
}

export interface TeacherTransaction {
  id: string;
  date: string;
  booking_ref: string;
  student_name: string;
  gross_usd: number;
  net_zar: number;
  status: "pending" | "cleared" | "paid_out";
}

export interface TeacherWalletData {
  pending_escrow_usd: number;
  cleared_balance_usd: number;
  cleared_balance_zar: number;
  fx_rate_usd_to_zar: number;
  payout_bank_account?: TeacherPayoutBankAccount;
  transactions: TeacherTransaction[];
}

export interface WeeklyScheduleBlock {
  day_of_week: number; // 0 = Mon, 6 = Sun
  time_range: string; // "08:00 - 10:00"
  is_open: boolean;
}
