import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { viewerPeriodBounds } from "./dashboardTime";

describe("viewerPeriodBounds", () => {
  it("uses the viewer timezone when UTC is still in the previous month", () => {
    const bounds = viewerPeriodBounds("Indian/Mauritius", new Date("2026-10-31T22:30:00Z"));
    assert.deepEqual(bounds, {
      dayStart: "2026-10-31T20:00:00.000Z",
      dayEnd: "2026-11-01T19:59:59.999Z",
      monthStart: "2026-10-31T20:00:00.000Z",
    });
  });

  it("uses UTC boundaries for a UTC viewer", () => {
    const bounds = viewerPeriodBounds("UTC", new Date("2026-10-03T12:00:00Z"));
    assert.equal(bounds.dayStart, "2026-10-03T00:00:00.000Z");
    assert.equal(bounds.dayEnd, "2026-10-03T23:59:59.999Z");
    assert.equal(bounds.monthStart, "2026-10-01T00:00:00.000Z");
  });
});
