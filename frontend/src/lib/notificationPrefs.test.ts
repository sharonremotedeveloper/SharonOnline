import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { groupsFor, isGroupOn, PREF_GROUPS, setGroup } from "./notificationPrefs";

// Kind names the server registers (backend/apps/notifications/domain_kinds.py). Anything else is a 400.
const SERVER_OPTIONAL_KINDS = new Set([
  "reminder_24h", "reminder_1h", "reminder_10m", "memo_reminder_12h", "tutor_late_warning",
  "booking_confirmed", "booking_rescheduled", "credit_granted", "credit_expiring",
]);

describe("notification preference groups", () => {
  it("only ever sends kind names the server knows and allows switching off", () => {
    for (const g of PREF_GROUPS) for (const k of g.kinds) assert.ok(SERVER_OPTIONAL_KINDS.has(k), k);
    // The bug this replaces: invented category keys.
    const sent = setGroup({}, PREF_GROUPS[0], false);
    assert.ok(!("lesson_reminders" in sent));
  });

  it("treats a missing key as on and one switched-off kind as the group off", () => {
    const reminders = PREF_GROUPS.find((g) => g.key === "reminders")!;
    assert.equal(isGroupOn({}, reminders), true);
    assert.equal(isGroupOn(undefined, reminders), true);
    assert.equal(isGroupOn({ reminder_1h: false }, reminders), false);
  });

  it("switches the whole group and keeps unrelated keys", () => {
    const booking = PREF_GROUPS.find((g) => g.key === "booking")!;
    assert.deepEqual(setGroup({ reminder_24h: false }, booking, false),
      { reminder_24h: false, booking_confirmed: false, booking_rescheduled: false });
  });

  it("never changes the mandatory group", () => {
    const essential = PREF_GROUPS.find((g) => g.mandatory)!;
    assert.equal(isGroupOn({}, essential), true);
    assert.deepEqual(setGroup({ a: true }, essential, false), { a: true });
  });

  it("shows each role only its own groups", () => {
    assert.ok(groupsFor("student").some((g) => g.key === "credits"));
    assert.ok(!groupsFor("student").some((g) => g.key === "memo"));
    assert.ok(groupsFor("teacher").some((g) => g.key === "memo"));
    assert.ok(!groupsFor("teacher").some((g) => g.key === "tutor_delay"));
  });
});
