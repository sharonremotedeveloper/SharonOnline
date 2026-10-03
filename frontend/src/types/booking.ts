import { PublicTutor } from "./tutor";

export type BookingStatus =
  | "pending_payment"
  | "confirmed"
  | "in_progress"
  | "completed"
  | "completed_pending_memo"
  | "completed_memo_forfeited"
  | "cancelled"
  | "cancelled_by_student"
  | "student_late_cancelled"
  | "cancelled_by_teacher"
  | "disputed"
  | "interrupted_power"
  | "student_no_show"
  | "teacher_no_show";

export interface BookingSlot {
  id: string;
  start_time_utc: string;
  end_time_utc: string;
  local_date: string;
  local_start_time: string;
  local_end_time: string;
  viewer_timezone: string;
  status: "available" | "booked" | "reserved";
  is_bookable: boolean;
  period?: "morning" | "afternoon" | "evening" | "night";
}

export interface DaySlots {
  date: string;
  day_name: string;
  is_today: boolean;
  slots: BookingSlot[];
}

export interface ReservationResponse {
  booking_id: string;
  lock_ttl_seconds: number;
  status: BookingStatus;
  expires_at?: string;
}

export interface BookingDetail {
  id: string;
  booking_reference: string;
  teacher: {
    id: string;
    full_name: string;
    first_name: string;
    avatar_url?: string;
    accent: string;
    price_per_25min_usd: number;
    headline?: string;
  };
  student: {
    id: string;
    full_name: string;
    email: string;
    target_level?: string;
    learning_goals?: string;
  };
  start_time_utc: string;
  end_time_utc: string;
  local_date: string;
  local_start_time: string;
  local_end_time: string;
  viewer_timezone: string;
  status: BookingStatus;
  price_usd: number;
  price_zar: number;
  lock_expires_at: string;
  zoom_url?: string;
  zoom_password?: string;
  zoom_meeting_id?: string;
  zoom_start_url?: string;
  zoom_join_url?: string;
  material_slug?: string;
  material_title?: string;
  created_at: string;
  cancelled_at?: string | null;
  reschedule_count?: number;
  original_start_time_utc?: string | null;
}

export type PaymentGatewayType = "credit" | "payfast" | "paypal";

export interface PayFastInitResponse {
  merchant_id: string;
  merchant_key: string;
  return_url: string;
  cancel_url: string;
  notify_url: string;
  amount: string;
  item_name: string;
  signature: string;
  action_url: string;
}

export interface CreditLedgerEntry {
  id: string;
  description: string;
  credits_delta: number;
  date: string;
  type: "purchase" | "redemption" | "refund" | "bonus";
}
