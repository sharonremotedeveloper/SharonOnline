/**
 * Notification settings as people think of them (groups), stored the way the server wants them (per kind).
 *
 * The server keys preferences by notification KIND (`reminder_24h`, `booking_confirmed`, ...; backend
 * apps/notifications/domain_kinds.py) and answers 400 "Unknown notification kind" to anything else. A missing key means
 * "on". Mandatory categories (cancellations, refunds, payments, security, strikes...) cannot be switched off at all.
 * The old preferences dialog sent invented group names, so no preference could ever be saved (fixed 2026-10-18).
 */
export type PrefChannel = "email" | "in_app";
export type PrefRole = "student" | "teacher";

export interface PrefGroup {
  key: string;
  title: string;
  description: string;
  /** Real kind names. Empty for the always-on group. */
  kinds: string[];
  mandatory: boolean;
  roles: PrefRole[];
}

export const PREF_GROUPS: PrefGroup[] = [
  {
    key: "reminders",
    title: "Lesson reminders",
    description: "A day, an hour and 10 minutes before each lesson.",
    kinds: ["reminder_24h", "reminder_1h", "reminder_10m"],
    mandatory: false,
    roles: ["student", "teacher"],
  },
  {
    key: "tutor_delay",
    title: "Tutor running late",
    description: "If your tutor has not joined a few minutes after the start.",
    kinds: ["tutor_late_warning"],
    mandatory: false,
    roles: ["student"],
  },
  {
    key: "memo",
    title: "Memo reminders",
    description: "A nudge when a lesson memo is due soon.",
    kinds: ["memo_reminder_12h"],
    mandatory: false,
    roles: ["teacher"],
  },
  {
    key: "booking",
    title: "Booking confirmations and changes",
    description: "New bookings and reschedules, with a calendar file.",
    kinds: ["booking_confirmed", "booking_rescheduled"],
    mandatory: false,
    roles: ["student", "teacher"],
  },
  {
    key: "credits",
    title: "Lesson credits",
    description: "Credits added to your wallet and credits about to expire.",
    kinds: ["credit_granted", "credit_expiring"],
    mandatory: false,
    roles: ["student"],
  },
  {
    key: "essential",
    title: "Cancellations, payments and security",
    description: "Always sent: cancellations, refunds, payment problems and account security.",
    kinds: [],
    mandatory: true,
    roles: ["student", "teacher"],
  },
];

export type KindMap = Record<string, boolean>;

export function groupsFor(role: PrefRole): PrefGroup[] {
  return PREF_GROUPS.filter((g) => g.roles.includes(role));
}

/** A group is on unless one of its kinds is explicitly switched off (a missing key means on). */
export function isGroupOn(map: KindMap | undefined, group: PrefGroup): boolean {
  if (group.mandatory) return true;
  return group.kinds.every((k) => map?.[k] !== false);
}

/** The map with every kind of the group set; other keys are kept as they were. */
export function setGroup(map: KindMap | undefined, group: PrefGroup, on: boolean): KindMap {
  if (group.mandatory) return { ...(map ?? {}) };
  const next = { ...(map ?? {}) };
  for (const k of group.kinds) next[k] = on;
  return next;
}
