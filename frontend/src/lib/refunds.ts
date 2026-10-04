/** Refunds owed to the signed-in student (Task 9.6). The money goes back to the original payment method; while it is pending it can become wallet credit. */
import { errorMessage, request } from "./http";
import { errorCode } from "./bookings";

export type RefundStatus = "pending_gateway" | "submitted" | "processed" | "converted" | "failed";

export interface Refund {
  id: string;
  booking_id: string;
  amount: string;
  currency: string;
  reason: "student_cancel" | "teacher_cancel" | "teacher_no_show" | "outage" | "dispute";
  /** `submitted` = the gateway accepted it and it is on its way (cannot be converted to credit any more). */
  status: RefundStatus;
  created_at: string;
  processed_at: string | null;
}

export async function listRefunds(): Promise<Refund[]> {
  const res = await request<Refund[] | { results: Refund[] }>("/refunds/");
  return Array.isArray(res) ? res : res.results ?? [];
}

export const convertRefundToWallet = (refundId: string) =>
  request<Refund>(`/refunds/${refundId}/convert-to-wallet/`, { method: "POST" });

const STATUS_LABELS: Record<RefundStatus, string> = {
  pending_gateway: "Waiting to be sent",
  submitted: "On its way",
  processed: "Paid to your original payment method",
  converted: "Converted to lesson credit",
  failed: "Being looked at by our team",
};

/** What the student sees for a refund status. An unknown status (a newer server) is neutral: it is NEVER shown as paid. */
export function refundStatusLabel(status: string): string {
  return Object.prototype.hasOwnProperty.call(STATUS_LABELS, status) ? STATUS_LABELS[status as RefundStatus] : "Status being updated";
}

/** Only a refund that has not been handed to the gateway can become wallet credit; once it is `submitted` the button is hidden. */
export function canConvertRefund(refund: Pick<Refund, "status">): boolean {
  return refund.status === "pending_gateway";
}

/** Message for a failed "convert to wallet": 409 `refund_in_progress` means the refund already started, so credit is no longer possible. */
export function convertRefundErrorMessage(err: unknown): string {
  const code = errorCode(err);
  if (code === "refund_in_progress") {
    return "This refund has already been sent to your original payment method, so it can no longer be turned into lesson credit. It should arrive shortly.";
  }
  if (code === "already_processed") {
    return "This refund has already been completed, so there is nothing to convert.";
  }
  return errorMessage(err);
}
