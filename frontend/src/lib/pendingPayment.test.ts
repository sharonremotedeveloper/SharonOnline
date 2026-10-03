import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { parsePendingPayFast } from "./pendingPayment";

describe("parsePendingPayFast", () => {
  it("accepts a booking or credit purchase hint", () => {
    assert.deepEqual(parsePendingPayFast('{"kind":"booking","id":"b-1"}'), { kind: "booking", id: "b-1" });
    assert.deepEqual(parsePendingPayFast('{"kind":"credit_purchase","id":"c-1"}'), { kind: "credit_purchase", id: "c-1" });
  });

  it("rejects anything malformed", () => {
    for (const raw of [null, "", "not json", "{}", '{"kind":"booking"}', '{"kind":"other","id":"x"}', '{"kind":"booking","id":""}', "null", "5"]) {
      assert.equal(parsePendingPayFast(raw), null, String(raw));
    }
  });
});
