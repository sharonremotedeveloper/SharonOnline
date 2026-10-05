export interface AdminTelemetry {
  gmv_today_usd: string;
  gmv_month_usd: string;
  active_zoom_sessions_count: number;
  open_disputes_count: number;
  pending_vetting_count: number;
  escrow_liability_usd: string;
  escrow_liability_zar: string;
  total_students_count: number;
  total_teachers_count: number;
}

export interface PendingTeacherApplication {
  id: string;
  full_name: string;
  email: string;
  country: string;
  accent: string;
  bio: string;
  specialties: string[];
  video_url: string;
  tefl_certificate_url?: string;
  eskom_area?: string;
  has_inverter?: boolean;
  applied_at: string;
  // The tutor's real lifecycle status (slice T1b, docs/TUTOR_STATUS_MACHINE.md); the queue lists applied | submitted | in_review.
  status: "applied" | "submitted" | "in_review" | "changes_requested" | "approved" | "rejected" | "suspended";
}

export interface LiveSessionRadarItem {
  id: string;
  booking_ref: string;
  teacher_name: string;
  student_name: string;
  material_title: string;
  start_time_utc: string;
  elapsed_minutes: number;
  student_joined_at?: string;
  teacher_joined_at?: string;
  zoom_meeting_id: string;
  status: "active" | "staging" | "wrap_up";
}

export interface DisputeCase {
  id: string;
  booking_ref: string;
  student_name: string;
  teacher_name: string;
  lesson_date: string;
  amount_usd: string;
  amount_zar: string;
  student_statement: string;
  teacher_statement: string;
  zoom_telemetry: {
    student_dwell_minutes: number;
    teacher_dwell_minutes: number;
    call_connected: boolean;
    interrupted_reason?: string;
  };
  status: "open" | "resolved";
  resolution?: "full_refund_student" | "release_tutor" | "split_50_50";
  admin_notes?: string;
}

export interface FinanceEscrowItem {
  id: string;
  booking_ref: string;
  student_name: string;
  teacher_name: string;
  lesson_date: string;
  amount_usd: string;
  amount_zar: string;
  platform_fee_usd: string;
  teacher_net_zar: string;
  escrow_status: "holding" | "cleared" | "refunded";
  release_date: string;
}

export interface PayoutBatchItem {
  id: string;
  teacher_id: string;
  teacher_name: string;
  bank_name: string;
  account_number_masked: string;
  branch_code: string;
  cleared_lessons_count: number;
  payout_amount_zar: string;
  status: "pending" | "exported" | "processed";
}
