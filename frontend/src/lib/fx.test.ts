import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { ApiError } from "./http";
import {
  blockedCurrencies,
  checkoutFailureMessage,
  fxStatus,
  isConfirmationRequired,
  paypalCheckoutCurrency,
  validateRateInput,
  type FxRateRow,
} from "./fx";

const row = (over: Partial<FxRateRow>): FxRateRow => ({
  id: 1, currency: "EUR", rate_to_zar: "19.850000", source: "manual", valid_from: "2026-10-03T08:00:00Z",
  set_by: "admin", age_hours: 1, stale: false, ...over,
});

describe("validateRateInput", () => {
  it("accepts positive decimal strings unchanged", () => {
    for (const v of ["19.85", "0.1", "1", "19.850000", "0.000001", "123456.5"]) {
      assert.deepEqual(validateRateInput(v), { ok: true, rate: v });
    }
    assert.deepEqual(validateRateInput("  19.85 "), { ok: true, rate: "19.85" });
  });
  it("rejects empty, zero, negative, non-numeric and exponent input", () => {
    for (const v of ["", "  ", "0", "0.000", "-1", "abc", "1e3", "1,5", "1.", ".5", "NaN", "Infinity", "1 2"]) {
      assert.equal(validateRateInput(v).ok, false, v);
    }
  });
  it("rejects more than 6 decimals and more than 6 integer digits", () => {
    assert.equal(validateRateInput("1.1234567").ok, false);
    assert.equal(validateRateInput("1234567").ok, false);
    assert.equal(validateRateInput("0001.5").ok, true);
  });
});

describe("fx status", () => {
  it("classifies ok, stale and missing", () => {
    assert.equal(fxStatus(row({})), "ok");
    assert.equal(fxStatus(row({ stale: true })), "stale");
    assert.equal(fxStatus(row({ rate_to_zar: null, stale: true })), "missing");
  });
  it("lists blocked currencies", () => {
    assert.deepEqual(blockedCurrencies([row({}), row({ currency: "JPY", stale: true })]), ["JPY"]);
    assert.deepEqual(blockedCurrencies(null), []);
  });
});

describe("isConfirmationRequired", () => {
  it("is true only for a 409 with code confirmation_required", () => {
    assert.equal(isConfirmationRequired(new ApiError(409, "x", { error: "x", code: "confirmation_required" })), true);
    assert.equal(isConfirmationRequired(new ApiError(409, "x", { error: "x" })), false);
    assert.equal(isConfirmationRequired(new ApiError(400, "x", { code: "confirmation_required" })), false);
    assert.equal(isConfirmationRequired(new Error("x")), false);
  });
});

describe("checkout helpers", () => {
  it("sends a currency only for EUR and JPY", () => {
    assert.equal(paypalCheckoutCurrency("EUR"), "EUR");
    assert.equal(paypalCheckoutCurrency("JPY"), "JPY");
    assert.equal(paypalCheckoutCurrency("USD"), undefined);
    assert.equal(paypalCheckoutCurrency("ZAR"), undefined);
  });
  it("surfaces the 503 message with a USD suggestion", () => {
    const msg = checkoutFailureMessage(new ApiError(503, "EUR payments are temporarily unavailable: rate stale."), "generic");
    assert.match(msg, /EUR payments are temporarily unavailable/);
    assert.match(msg, /USD/);
  });
  it("falls back for other errors", () => {
    assert.equal(checkoutFailureMessage(new ApiError(500, "boom"), "generic"), "generic");
  });
});
