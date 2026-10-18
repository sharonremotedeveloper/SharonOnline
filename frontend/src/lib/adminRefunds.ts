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

/** Staff wording for a refund's status (the student page uses friendlier text in `refunds.ts`). */
const STATUS_LABELS: Record<string, string> = {
  awaiting_clearance: "Waiting for the payment to clear",
  void: "Not needed (payment never cleared)",
  pending_gateway: "Waiting for the gateway",
  submitted: "On its way",
  processed: "Paid back",
  converted: "Converted to wallet credit",
  failed: "Failed - needs a person",
};

export function adminRefundStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status.replace(/_/g, " ");
}

/**
 * Failures where we cannot tell whether PayPal already paid: a retry must carry the admin's confirmation that they checked
 * the gateway (the API answers 409 confirmation_required otherwise). docs/RUNBOOK_REFUNDS.md, Actions.
 */
const AMBIGUOUS = new Set(["exhausted", "replay_window", "already_refunded"]);

export function retryNeedsConfirmation(failureKind: string | null | undefined): boolean {
  return !!failureKind && AMBIGUOUS.has(failureKind);
}

/** One-line runbook guidance per failure kind (docs/RUNBOOK_REFUNDS.md, Alert codes). */
const FAILURE_HELP: Record<string, string> = {
  rejected: "PayPal refused it. If the cause is fixed, retry; if not, pay the student another way and mark it paid.",
  already_refunded: "PayPal says it is already refunded. Check PayPal: if it went to this student, mark it paid - do not retry.",
  guard: "A safety check refused it. Fix the problem the note names, then retry.",
  exhausted: "Kept failing for days. Check PayPal for a refund first; if there is none, retry with confirmation.",
  replay_window: "Too old to tell whether PayPal paid. Check PayPal, then mark paid or retry with confirmation.",
  provider_failed: "PayPal accepted it, then failed it. Retry.",
};

export function failureHelp(failureKind: string | null | undefined): string | null {
  return failureKind ? FAILURE_HELP[failureKind] ?? null : null;
}

/** The queue views shown as tabs. "Needs action" is what the runbook triages first. */
export const REFUND_VIEWS = [
  { key: "failed", label: "Needs action", params: { status: "failed" } },
  { key: "manual", label: "Waiting for manual payment", params: { waiting_manual: true } },
  { key: "pending", label: "Waiting for gateway", params: { status: "pending_gateway" } },
  { key: "submitted", label: "On its way", params: { status: "submitted" } },
  { key: "all", label: "All", params: {} },
] as const satisfies readonly { key: string; label: string; params: AdminRefundParams }[];

const REASON_LABELS: Record<string, string> = {
  student_cancel: "Student cancelled in time",
  teacher_cancel: "Tutor cancelled",
  teacher_no_show: "Tutor did not attend",
  outage: "Power cut interrupted the lesson",
  dispute: "Dispute decided for the student",
};

export function refundReasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason.replace(/_/g, " ");
}

/** "PayPal" / "PayFast" for display; anything else as given. */
export function gatewayName(gateway: string | null | undefined): string {
  const g = (gateway || "").toLowerCase();
  return g === "paypal" ? "PayPal" : g === "payfast" ? "PayFast" : gateway || "the gateway";
}

/** The retry endpoint's 409 body is {error, code}: show the sentence, not the machine code after it. */
export function retryErrorText(err: unknown): unknown {
  const body = (err as { body?: unknown } | null)?.body;
  const text = body && typeof body === "object" ? (body as { error?: unknown }).error : null;
  return typeof text === "string" && text.trim() ? text : err;
}
