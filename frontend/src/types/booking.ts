import type { components } from "./api.generated";

export type BookingStatus = components["schemas"]["BookingStatusEnum"];

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

type GeneratedBookingDetail = components["schemas"]["BookingDetail"];
type GeneratedTeacher = GeneratedBookingDetail["teacher"];

/** API-generated booking contract with the one intentional runtime normalization: Decimal -> number. */
export type BookingDetail = Omit<GeneratedBookingDetail, "teacher"> & {
  teacher: Omit<GeneratedTeacher, "price_per_25min_usd" | "rating_avg"> & {
    price_per_25min_usd?: number;
    rating_avg?: number;
  };
};

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

export type CreditLedgerEntry = components["schemas"]["CreditLedgerEntry"];
