/**
 * Tests for the scheduler's date helpers. The calendar strip must line up with the server's `local_date` values.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  addDays,
  dateRange,
  dayLabel,
  dayPartOf,
  groupByLocalDate,
  monthYearLabel,
  todayInZone,
  zoneCityName,
  zoneOffsetLabel,
} from "./scheduling";

describe("todayInZone", () => {
  it("returns the calendar date in the requested zone, not in UTC", () => {
    // 20:30 UTC on 6 Oct is already 7 Oct in Tokyo and still 6 Oct in New York.
    const now = new Date("2026-10-06T20:30:00Z");
    assert.equal(todayInZone("Asia/Tokyo", now), "2026-10-07");
    assert.equal(todayInZone("America/New_York", now), "2026-10-06");
    assert.equal(todayInZone("UTC", now), "2026-10-06");
  });

  it("does not throw for an unknown zone", () => {
    assert.match(todayInZone("Not/AZone", new Date("2026-10-06T12:00:00Z")), /^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("addDays and dateRange", () => {
  it("rolls over month and year ends", () => {
    assert.equal(addDays("2026-10-31", 1), "2026-11-01");
    assert.equal(addDays("2026-12-31", 1), "2027-01-01");
    assert.equal(addDays("2026-03-01", -1), "2026-02-28");
  });

  it("does not skip or repeat a day across a daylight-saving change", () => {
    assert.deepEqual(dateRange("2026-10-24", 3), ["2026-10-24", "2026-10-25", "2026-10-26"]);
  });

  it("builds the requested number of consecutive days", () => {
    const range = dateRange("2026-10-07", 14);
    assert.equal(range.length, 14);
    assert.equal(range[13], "2026-10-20");
  });

  it("rejects a value that is not an ISO date", () => {
    assert.throws(() => addDays("07/10/2026", 1), RangeError);
  });
});

describe("groupByLocalDate", () => {
  it("groups by date and sorts each day by time", () => {
    const slots = [
      { local_date: "2026-10-07", local_start_time: "16:30" },
      { local_date: "2026-10-08", local_start_time: "09:00" },
      { local_date: "2026-10-07", local_start_time: "15:00" },
    ];
    const grouped = groupByLocalDate(slots);
    assert.deepEqual(
      grouped.get("2026-10-07")?.map((s) => s.local_start_time),
      ["15:00", "16:30"],
    );
    assert.equal(grouped.get("2026-10-08")?.length, 1);
    assert.equal(grouped.get("2026-10-09"), undefined);
  });
});

describe("dayPartOf", () => {
  it("places times in the right part of the day", () => {
    assert.equal(dayPartOf("05:30"), "night");
    assert.equal(dayPartOf("06:00"), "morning");
    assert.equal(dayPartOf("11:30"), "morning");
    assert.equal(dayPartOf("12:00"), "afternoon");
    assert.equal(dayPartOf("16:30"), "afternoon");
    assert.equal(dayPartOf("17:00"), "evening");
    assert.equal(dayPartOf("23:30"), "evening");
    assert.equal(dayPartOf("00:00"), "night");
  });

  it("treats an unreadable time as night rather than throwing", () => {
    assert.equal(dayPartOf(""), "night");
  });
});

describe("labels", () => {
  it("formats a day without shifting it by the device time zone", () => {
    const l = dayLabel("2026-10-07");
    assert.equal(l.weekday, "Wed");
    assert.equal(l.day, "7");
    assert.equal(l.month, "Oct");
    assert.match(l.long, /Wednesday/);
  });

  it("formats month and year", () => {
    assert.equal(monthYearLabel("2026-10-07"), "October 2026");
  });

  it("names a zone and its offset", () => {
    assert.equal(zoneCityName("America/New_York"), "New York");
    assert.equal(zoneOffsetLabel("Asia/Tokyo", new Date("2026-10-06T00:00:00Z")), "GMT+9");
    assert.equal(zoneOffsetLabel("Not/AZone"), "");
  });
});
