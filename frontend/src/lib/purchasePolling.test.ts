import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  PURCHASE_POLL_MAX_ATTEMPTS,
  PURCHASE_POLL_MAX_DURATION_MS,
  PURCHASE_POLL_FETCH_TIMEOUT_MS,
  purchasePollDelayMs,
  purchasePollRemainingMs,
  retryAfterMs,
} from "./purchasePolling";

describe("purchase status polling", () => {
  it("backs off and caps the delay", () => {
    assert.deepEqual([0, 1, 2, 3, 4, 8].map((attempt) => purchasePollDelayMs(attempt)), [2_000, 4_000, 8_000, 15_000, 30_000, 30_000]);
    assert.equal(purchasePollDelayMs(1, 12_500), 12_500);
    assert.equal(purchasePollDelayMs(1, 120_000), 60_000);
    assert.equal(purchasePollDelayMs(4, 30_000, 7_000), 7_000);
    assert.equal(purchasePollDelayMs(4, 30_000, 0), 0);
  });

  it("parses seconds and HTTP dates, rejecting malformed values", () => {
    assert.equal(retryAfterMs("5"), 5_000);
    assert.equal(retryAfterMs(" 0 "), 0);
    assert.equal(retryAfterMs("not-a-date"), undefined);
    assert.equal(retryAfterMs("Wed, 21 Oct 2015 07:28:00 GMT", Date.parse("Wed, 21 Oct 2015 07:27:55 GMT")), 5_000);
  });

  it("keeps the browser poll bounded", () => {
    assert.equal(PURCHASE_POLL_MAX_ATTEMPTS, 8);
    assert.equal(PURCHASE_POLL_MAX_DURATION_MS, 120_000);
    assert.equal(PURCHASE_POLL_FETCH_TIMEOUT_MS, 10_000);
    assert.equal(purchasePollRemainingMs(1_000, 91_000), 30_000);
    assert.equal(purchasePollRemainingMs(1_000, 121_000), 0);
  });
});
