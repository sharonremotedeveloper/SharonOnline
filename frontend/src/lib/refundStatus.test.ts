import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { adminRefundQuery } from "./adminRefunds";
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
