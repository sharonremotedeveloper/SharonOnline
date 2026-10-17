import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { formatRand } from "./currency";

describe("formatRand", () => {
  it("uses one format for every Rand amount on tutor screens", () => {
    assert.equal(formatRand(0), "R0.00");
    assert.equal(formatRand(1234.5), "R1,234.50");
    assert.equal(formatRand(Number.NaN), "R0.00");
  });
});
