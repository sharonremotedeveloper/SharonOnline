/**
 * Pure mapping from the PayPal capture endpoint's result (or HTTP error) to what the checkout UI shows and does.
 * The browser never decides that something is paid: it only reports what the server (which re-reads the capture
 * from PayPal) said, and an unknown or incomplete answer is always an error, never a success.
 */
import { ApiError } from "./http";

export type CaptureOutcome = "confirmed" | "pending_confirmed" | "pending" | "declined" | "failed";

/** POST /api/v1/payments/paypal/capture/ 200 body. Hand-written until the OpenAPI schema carries this path. */
export interface CaptureResponse {
  outcome: CaptureOutcome;
  booking_id: string | null;
  credit_purchase_id: string | null;
  message: string;
  retryable: boolean;
}

export type CaptureTarget = "booking" | "credit_pack";

export type NextAction =
  | { type: "go_confirmed"; bookingId: string; pendingNotice: boolean }
  | { type: "pack_credited"; purchaseId: string }
  | { type: "poll"; target: "booking" | "credit_purchase"; id: string }
  | { type: "restart" }
  | { type: "back_to_tutor" }
  | { type: "check_then_retry" }
  | { type: "none" };

export type OutcomeKind =
  | "success"
  | "success_pending"
  | "under_review"
  | "retry"
  | "retryable"
  | "unavailable_slot"
  | "error";

export interface OutcomeView {
  kind: OutcomeKind;
  message: string;
  nextAction: NextAction;
}

export const PENDING_NOTICE =
  "PayPal is still verifying this payment. Your lesson is booked. If it cannot be completed we will contact you by e-mail.";

const UNDER_REVIEW =
  "Payment under review. PayPal has not finished checking this payment yet. We will e-mail you the result, and this page updates by itself.";

const none: NextAction = { type: "none" };

const fail = (message: string): OutcomeView => ({ kind: "error", message, nextAction: none });

export function interpretCaptureResponse(resp: CaptureResponse, target: CaptureTarget): OutcomeView {
  const isBooking = target === "booking";
  const id = isBooking ? resp.booking_id : resp.credit_purchase_id;
  const serverMessage = resp.message?.trim();

  switch (resp.outcome) {
    case "confirmed":
      if (!id) return fail("PayPal reported success but we could not match it to your order. Please contact support before paying again.");
      return {
        kind: "success",
        message: serverMessage || "Payment confirmed.",
        nextAction: isBooking
          ? { type: "go_confirmed", bookingId: id, pendingNotice: false }
          : { type: "pack_credited", purchaseId: id },
      };

    case "pending_confirmed":
      // Only lessons get a grace booking. A pack in this state is not credited: wait for the server to say so.
      if (!isBooking) {
        if (!id) return fail("Your payment is pending, but we could not match it to your order. Please contact support.");
        return { kind: "under_review", message: UNDER_REVIEW, nextAction: { type: "poll", target: "credit_purchase", id } };
      }
      if (!id) return fail("Your payment is pending, but we could not match it to your booking. Please contact support.");
      return {
        kind: "success_pending",
        message: PENDING_NOTICE,
        nextAction: { type: "go_confirmed", bookingId: id, pendingNotice: true },
      };

    case "pending":
      if (!id) return fail("Your payment is pending, but we could not match it to your order. Please contact support.");
      return {
        kind: "under_review",
        message: UNDER_REVIEW,
        nextAction: { type: "poll", target: isBooking ? "booking" : "credit_purchase", id },
      };

    case "declined":
      return {
        kind: "retry",
        message: "PayPal could not take this payment. Please choose another card or funding source and try again. Nothing was charged.",
        nextAction: { type: "restart" },
      };

    case "failed":
      return fail(serverMessage ? `The payment could not be completed. ${serverMessage}` : "The payment could not be completed. Nothing was charged.");

    default:
      // Unknown outcome from a newer or broken backend: never treat as paid.
      return fail("We could not tell whether this payment went through. Please check your bookings before paying again.");
  }
}

export function interpretCaptureError(err: unknown): OutcomeView {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 400:
        return fail("We could not process this payment request. Please start the payment again.");
      case 404:
        return fail("We could not find this PayPal order. Please start the payment again.");
      case 409:
        return {
          kind: "unavailable_slot",
          message: "This time slot is no longer available (the reservation expired or the slot was taken). Please pick a new time.",
          nextAction: { type: "back_to_tutor" },
        };
      case 0:
      case 502:
      case 503:
      case 504:
        return {
          kind: "retryable",
          message:
            "We could not reach PayPal to finish this payment. Do not assume it failed: we are checking your booking now. If it is not confirmed you can safely try again.",
          nextAction: { type: "check_then_retry" },
        };
      default:
        return fail("Something went wrong while finishing your payment. Please check your bookings before trying again.");
    }
  }
  return fail("Something went wrong while finishing your payment. Please check your bookings before trying again.");
}
