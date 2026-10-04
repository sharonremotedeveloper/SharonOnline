/** Types and query builder for the staff refund queue (Task 10.7). Types come from the generated OpenAPI contract. */
import type { components } from "@/types/api.generated";

export type AdminRefund = components["schemas"]["AdminRefund"];
export type AdminRefundPage = components["schemas"]["AdminRefundPage"];
export type AdminRefundAttempt = components["schemas"]["AdminRefundAttempt"];

export interface AdminRefundParams {
  status?: string;
  failure_kind?: string;
  gateway?: string;
  in_flight?: boolean;
  waiting_manual?: boolean;
  page?: number;
  page_size?: number;
}

/** `?a=b&...` from the filters that are actually set (booleans are sent only when true or false, never as undefined). */
export function adminRefundQuery(params: AdminRefundParams): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    q.set(key, String(value));
  }
  const text = q.toString();
  return text ? `?${text}` : "";
}
