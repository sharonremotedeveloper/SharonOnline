import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { adminRefundQuery, adminRefundStatusLabel, failureHelp, gatewayName, REFUND_VIEWS, refundReasonLabel, retryErrorText, retryNeedsConfirmation } from "./adminRefunds";
import { ApiError } from "./http";
import { canConvertRefund, convertRefundErrorMessage, refundStatusLabel } from "./refunds";

describe("student refund status labels", () => {
  it("labels every known status, 'submitted' as On its way", () => {
    assert.equal(refundStatusLabel("submitted"), "On its way");
    assert.equal(refundStatusLabel("pending_gateway"), "Waiting to be sent");
    assert.equal(refundStatusLabel("converted"), "Converted to lesson credit");
    assert.match(refundStatusLabel("processed"), /^Paid/);
    assert.equal(refundStatusLabel("failed"), "Being looked at by our team");
  });

  it("never renders an unknown status as paid", () => {
    for (const unknown of ["", "refunded", "settled", "constructor", "__proto__", "toString", "PROCESSED"]) {
      const label = refundStatusLabel(unknown);
      assert.equal(label, "Status being updated", unknown);
      assert.doesNotMatch(label, /paid/i);
    }
  });

  it("offers 'convert to wallet' only while the refund has not been handed to the gateway", () => {
    assert.equal(canConvertRefund({ status: "pending_gateway" }), true);
    for (const status of ["submitted", "processed", "converted", "failed"] as const) {
      assert.equal(canConvertRefund({ status }), false, status);
    }
  });
});

describe("convert-to-wallet failure message", () => {
  const conflict = (code: string) => new ApiError(409, "raw server text", { error: "raw server text", code });

  it("explains refund_in_progress in plain words", () => {
    const msg = convertRefundErrorMessage(conflict("refund_in_progress"));
    assert.match(msg, /already been sent/);
    assert.doesNotMatch(msg, /raw server text/);
  });

  it("explains already_processed and falls back for anything else", () => {
    assert.match(convertRefundErrorMessage(conflict("already_processed")), /already been completed/);
    assert.equal(convertRefundErrorMessage(new ApiError(403, "no")), "You don't have permission to do that.");
    assert.ok(convertRefundErrorMessage(new Error("boom")).length > 0);
  });
});

describe("admin refund query", () => {
  it("builds only the filters that are set, keeping explicit false", () => {
    assert.equal(adminRefundQuery({}), "");
    assert.equal(adminRefundQuery({ status: "failed", gateway: "", in_flight: false }), "?status=failed&in_flight=false");
    assert.equal(adminRefundQuery({ waiting_manual: true, page: 2 }), "?waiting_manual=true&page=2");
  });
});

describe("admin refund helpers", () => {
  it("asks for gateway confirmation only for ambiguous failures", () => {
    assert.equal(retryNeedsConfirmation("exhausted"), true);
    assert.equal(retryNeedsConfirmation("replay_window"), true);
    assert.equal(retryNeedsConfirmation("already_refunded"), true);
    assert.equal(retryNeedsConfirmation("rejected"), false);
    assert.equal(retryNeedsConfirmation(""), false);
    assert.equal(retryNeedsConfirmation(null), false);
  });

  it("labels statuses for staff and explains every failure kind", () => {
    assert.equal(adminRefundStatusLabel("failed"), "Failed - needs a person");
    assert.equal(adminRefundStatusLabel("something_new"), "something new");
    for (const kind of ["rejected", "already_refunded", "guard", "exhausted", "replay_window", "provider_failed"]) {
      assert.ok(failureHelp(kind), kind);
    }
    assert.equal(failureHelp("unknown_kind"), null);
    assert.equal(refundReasonLabel("teacher_no_show"), "Tutor did not attend");
    assert.equal(refundReasonLabel("new_reason"), "new reason");
  });

  it("starts the queue on the rows that need a person", () => {
    assert.deepEqual(REFUND_VIEWS[0].params, { status: "failed" });
    assert.equal(adminRefundQuery(REFUND_VIEWS[1].params), "?waiting_manual=true");
  });
});

describe("admin refund display", () => {
  it("names gateways properly", () => {
    assert.equal(gatewayName("paypal"), "PayPal");
    assert.equal(gatewayName("payfast"), "PayFast");
    assert.equal(gatewayName(""), "the gateway");
  });

  it("shows the server's sentence for a refused retry, without the code", () => {
    const err = new ApiError(409, "Check the gateway first. confirmation_required", { error: "Check the gateway first.", code: "confirmation_required" });
    assert.equal(retryErrorText(err), "Check the gateway first.");
    const other = new ApiError(500, "Server error", "<html>");
    assert.equal(retryErrorText(other), other);
  });
});
