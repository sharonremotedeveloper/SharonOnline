/** Refunds owed to the signed-in student (Task 9.6). The money goes back to the original payment method; while it is pending it can become wallet credit. */
import { request } from "./http";

export interface Refund {
  id: string;
  booking_id: string;
  amount: string;
  currency: string;
  reason: "student_cancel" | "teacher_cancel" | "teacher_no_show" | "outage" | "dispute";
  /** `submitted` = the gateway accepted it and it is on its way (cannot be converted to credit any more). */
  status: "pending_gateway" | "submitted" | "processed" | "converted" | "failed";
  created_at: string;
  processed_at: string | null;
}

export async function listRefunds(): Promise<Refund[]> {
  const res = await request<Refund[] | { results: Refund[] }>("/refunds/");
  return Array.isArray(res) ? res : res.results ?? [];
}

export const convertRefundToWallet = (refundId: string) =>
  request<Refund>(`/refunds/${refundId}/convert-to-wallet/`, { method: "POST" });
