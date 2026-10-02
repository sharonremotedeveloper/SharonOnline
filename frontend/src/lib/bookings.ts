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
