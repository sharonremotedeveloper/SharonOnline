/**
 * "My lessons" list (Task 9.5): the server scopes to the caller and filters; this only builds the query string and
 * normalises the paginated response. Throws ApiError on failure (no fabricated data).
 */
import { request } from "./http";
import type { BookingDetail } from "@/types/booking";

export interface BookingListParams {
  status?: string[];
  when?: "upcoming" | "past";
  /** UTC date (YYYY-MM-DD) or ISO date-time; both ends inclusive. */
  from?: string;
  to?: string;
  ordering?: "start_time_utc" | "-start_time_utc";
  pageSize?: number;
}

export interface BookingPage {
  items: BookingDetail[];
  /** Total matches on the server, which can exceed items.length. */
  count: number;
  hasMore: boolean;
}

export function bookingListQuery(p: BookingListParams = {}): string {
  const q = new URLSearchParams();
  if (p.status?.length) q.set("status", p.status.join(","));
  if (p.when) q.set("when", p.when);
  if (p.from) q.set("from", p.from);
  if (p.to) q.set("to", p.to);
  if (p.ordering) q.set("ordering", p.ordering);
  if (p.pageSize) q.set("page_size", String(p.pageSize));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export async function listBookings(p: BookingListParams = {}): Promise<BookingPage> {
  const res = await request<BookingDetail[] | { results: BookingDetail[]; count?: number; next?: string | null }>(
    `/bookings/${bookingListQuery(p)}`
  );
  if (Array.isArray(res)) return { items: res, count: res.length, hasMore: false };
  const items = res.results ?? [];
  return { items, count: res.count ?? items.length, hasMore: Boolean(res.next) };
}

// ---------------------------------------------------------------- cancel + reschedule (Task 9.6)

export type CancelOutcome =
  | "released"
  | "full_refund"
  | "fee_forfeited"
  | "tutor_refund"
  | "tutor_refund_with_penalty"
  | "not_cancellable";

export interface CancelPreview {
  can_cancel: boolean;
  outcome: CancelOutcome;
  message: string;
  seconds_until_start: number;
  refund_amount: string | null;
  refund_currency: string | null;
  bonus_credits: number;
  strike: boolean;
  /** Students only: the last moment a cancellation is still free. */
  free_cancel_until?: string;
}

/** Machine-readable reason from a failed cancel / reschedule call (e.g. "acknowledgement_required", "reschedule_limit_reached"). */
export function errorCode(err: unknown): string | null {
  const body = (err as { body?: unknown } | null)?.body;
  const code = body && typeof body === "object" ? (body as { code?: unknown }).code : null;
  return typeof code === "string" ? code : null;
}

export const getCancelPreview = (bookingId: string) => request<CancelPreview>(`/bookings/${bookingId}/cancel-preview/`);

/** A student cancelling inside the free window must pass `acknowledgeForfeit: true` (show the preview first). */
export const cancelBooking = (bookingId: string, opts: { reason?: string; acknowledgeForfeit?: boolean } = {}) =>
  request<{ outcome: CancelOutcome; status: string; message: string }>(`/bookings/${bookingId}/cancel/`, {
    method: "POST",
    body: JSON.stringify({ reason: opts.reason ?? "", acknowledge_forfeit: Boolean(opts.acknowledgeForfeit) }),
  });

export const rescheduleBooking = (bookingId: string, startTimeUtc: string) =>
  request<BookingDetail>(`/bookings/${bookingId}/reschedule/`, {
    method: "POST",
    body: JSON.stringify({ start_time_utc: startTimeUtc }),
  });
