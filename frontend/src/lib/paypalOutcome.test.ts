import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { ApiError } from "./http";
import { interpretCaptureError, interpretCaptureResponse, type CaptureResponse } from "./paypalOutcome";

const resp = (over: Partial<CaptureResponse>): CaptureResponse => ({
  outcome: "confirmed",
  booking_id: "b-1",
  credit_purchase_id: null,
  message: "",
  retryable: false,
  ...over,
});

describe("interpretCaptureResponse - lessons", () => {
  it("confirmed -> go to the confirmation page", () => {
    const r = interpretCaptureResponse(resp({ outcome: "confirmed" }), "booking");
    assert.equal(r.kind, "success");
    assert.deepEqual(r.nextAction, { type: "go_confirmed", bookingId: "b-1", pendingNotice: false });
  });

  it("pending_confirmed -> confirmation page with the pending notice and the exact wording", () => {
    const r = interpretCaptureResponse(resp({ outcome: "pending_confirmed" }), "booking");
    assert.equal(r.kind, "success_pending");
    assert.deepEqual(r.nextAction, { type: "go_confirmed", bookingId: "b-1", pendingNotice: true });
    assert.equal(
      r.message,
      "PayPal is still verifying this payment. Your lesson is booked. If it cannot be completed we will contact you by e-mail."
    );
  });

  it("pending -> under review, keep polling the booking, tell the student we will e-mail", () => {
    const r = interpretCaptureResponse(resp({ outcome: "pending" }), "booking");
    assert.equal(r.kind, "under_review");
    assert.deepEqual(r.nextAction, { type: "poll", target: "booking", id: "b-1" });
    assert.match(r.message, /under review/i);
    assert.match(r.message, /e-mail/i);
  });

  it("declined -> restart the PayPal flow, slot still held", () => {
    const r = interpretCaptureResponse(resp({ outcome: "declined" }), "booking");
    assert.equal(r.kind, "retry");
    assert.deepEqual(r.nextAction, { type: "restart" });
    assert.match(r.message, /another/i);
  });

  it("failed -> unrecoverable error, no next action; includes the server message when present", () => {
    const r = interpretCaptureResponse(resp({ outcome: "failed", message: "Capture failed." }), "booking");
    assert.equal(r.kind, "error");
    assert.deepEqual(r.nextAction, { type: "none" });
    assert.match(r.message, /Capture failed\./);
  });

  it("confirmed without a booking id never claims success", () => {
    const r = interpretCaptureResponse(resp({ outcome: "confirmed", booking_id: null }), "booking");
    assert.equal(r.kind, "error");
    assert.deepEqual(r.nextAction, { type: "none" });
  });

  it("an unknown outcome is never treated as paid", () => {
    const r = interpretCaptureResponse(resp({ outcome: "paid-ish" as never }), "booking");
    assert.equal(r.kind, "error");
  });
});

describe("interpretCaptureResponse - credit packs", () => {
  const pack = (over: Partial<CaptureResponse>) => resp({ booking_id: null, credit_purchase_id: "cp-1", ...over });

  it("confirmed -> credited, refresh wallet", () => {
    const r = interpretCaptureResponse(pack({ outcome: "confirmed" }), "credit_pack");
    assert.equal(r.kind, "success");
    assert.deepEqual(r.nextAction, { type: "pack_credited", purchaseId: "cp-1" });
  });

  it("pending -> poll the purchase", () => {
    const r = interpretCaptureResponse(pack({ outcome: "pending" }), "credit_pack");
    assert.equal(r.kind, "under_review");
    assert.deepEqual(r.nextAction, { type: "poll", target: "credit_purchase", id: "cp-1" });
  });

  it("pending_confirmed is never granted to packs: treated as under review, not credited", () => {
    const r = interpretCaptureResponse(pack({ outcome: "pending_confirmed" }), "credit_pack");
    assert.equal(r.kind, "under_review");
    assert.deepEqual(r.nextAction, { type: "poll", target: "credit_purchase", id: "cp-1" });
  });

  it("confirmed without a purchase id is an error", () => {
    const r = interpretCaptureResponse(pack({ outcome: "confirmed", credit_purchase_id: null }), "credit_pack");
    assert.equal(r.kind, "error");
  });

  it("declined -> restart", () => {
    assert.deepEqual(interpretCaptureResponse(pack({ outcome: "declined" }), "credit_pack").nextAction, { type: "restart" });
  });
});

describe("interpretCaptureError", () => {
  const e = (status: number, msg = "x") => new ApiError(status, msg);

  it("400 -> invalid request, no retry", () => {
    const r = interpretCaptureError(e(400));
    assert.equal(r.kind, "error");
    assert.deepEqual(r.nextAction, { type: "none" });
  });

  it("404 -> unknown order, no retry", () => {
    const r = interpretCaptureError(e(404));
    assert.equal(r.kind, "error");
    assert.deepEqual(r.nextAction, { type: "none" });
  });

  it("409 -> booking no longer payable, link back to the tutor", () => {
    const r = interpretCaptureError(e(409));
    assert.equal(r.kind, "unavailable_slot");
    assert.deepEqual(r.nextAction, { type: "back_to_tutor" });
    assert.match(r.message, /no longer available/i);
  });

  it("502, 503, 504 and network errors -> retryable, check the booking first, never assume failure", () => {
    for (const status of [502, 503, 504, 0]) {
      const r = interpretCaptureError(e(status));
      assert.equal(r.kind, "retryable", String(status));
      assert.deepEqual(r.nextAction, { type: "check_then_retry" });
      assert.match(r.message, /Do not assume it failed/);
    }
  });

  it("any other status or a non-ApiError is a generic error", () => {
    assert.equal(interpretCaptureError(e(500)).kind, "error");
    assert.equal(interpretCaptureError(new Error("boom")).kind, "error");
    assert.equal(interpretCaptureError("weird").kind, "error");
  });
});
