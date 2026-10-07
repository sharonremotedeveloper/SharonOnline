/**
 * Pure date helpers for the lesson scheduler.
 *
 * The API gives every slot a `local_date` ("2026-10-07") and `local_start_time` ("15:00") already converted to the
 * viewer's IANA time zone. These helpers never re-convert a slot: they only group what the server sent and build the
 * strip of calendar days in that same zone, so a day shown in the picker always matches the `local_date` of its slots.
 */

export interface DayPart {
  id: "night" | "morning" | "afternoon" | "evening";
  label: string;
  hint: string;
}

export const DAY_PARTS: DayPart[] = [
  { id: "morning", label: "Morning", hint: "6:00 to 11:59" },
  { id: "afternoon", label: "Afternoon", hint: "12:00 to 16:59" },
  { id: "evening", label: "Evening", hint: "17:00 to 23:59" },
  { id: "night", label: "Night", hint: "0:00 to 5:59" },
];

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Today's calendar date ("YYYY-MM-DD") in the given IANA zone. Falls back to the device zone for an unknown zone. */
export function todayInZone(timeZone: string, now: Date = new Date()): string {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(now);
    const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
    return `${get("year")}-${get("month")}-${get("day")}`;
  } catch {
    return todayInZone(Intl.DateTimeFormat().resolvedOptions().timeZone, now);
  }
}

/** Add whole days to an ISO calendar date. Uses UTC arithmetic so daylight-saving changes cannot skip or repeat a day. */
export function addDays(isoDate: string, days: number): string {
  const m = ISO_DATE.exec(isoDate);
  if (!m) throw new RangeError(`Not an ISO date: ${isoDate}`);
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + days));
  return d.toISOString().slice(0, 10);
}

/** `count` consecutive calendar dates starting at `start`. */
export function dateRange(start: string, count: number): string[] {
  return Array.from({ length: count }, (_, i) => addDays(start, i));
}

/** Slots grouped by their `local_date`, keeping each day's slots in time order. */
export function groupByLocalDate<T extends { local_date: string; local_start_time: string }>(slots: T[]): Map<string, T[]> {
  const byDay = new Map<string, T[]>();
  for (const slot of slots) {
    const day = byDay.get(slot.local_date);
    if (day) day.push(slot);
    else byDay.set(slot.local_date, [slot]);
  }
  for (const day of byDay.values()) day.sort((a, b) => a.local_start_time.localeCompare(b.local_start_time));
  return byDay;
}

/** Which part of the day a "HH:MM" start time falls in. */
export function dayPartOf(localTime: string): DayPart["id"] {
  const hour = Number.parseInt(localTime.split(":")[0] ?? "", 10);
  if (!Number.isFinite(hour)) return "night";
  if (hour >= 6 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  if (hour >= 17) return "evening";
  return "night";
}

/** Short label parts for a calendar date, e.g. { weekday: "Wed", day: "7", month: "Oct" }. Locale-stable (English). */
export function dayLabel(isoDate: string): { weekday: string; day: string; month: string; long: string } {
  const m = ISO_DATE.exec(isoDate);
  if (!m) return { weekday: "", day: "", month: "", long: isoDate };
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12));
  const fmt = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", ...opts }).format(d);
  return {
    weekday: fmt({ weekday: "short" }),
    day: fmt({ day: "numeric" }),
    month: fmt({ month: "short" }),
    long: fmt({ weekday: "long", day: "numeric", month: "long" }),
  };
}

/** "October 2026" for a calendar date. */
export function monthYearLabel(isoDate: string): string {
  const m = ISO_DATE.exec(isoDate);
  if (!m) return "";
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12));
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", month: "long", year: "numeric" }).format(d);
}

/** "GMT+9" style offset for a zone right now, or "" when the zone is unknown. */
export function zoneOffsetLabel(timeZone: string, now: Date = new Date()): string {
  try {
    const parts = new Intl.DateTimeFormat("en-GB", { timeZone, timeZoneName: "shortOffset" }).formatToParts(now);
    return parts.find((p) => p.type === "timeZoneName")?.value ?? "";
  } catch {
    return "";
  }
}

/** Human name for a zone: "Tokyo" from "Asia/Tokyo". */
export function zoneCityName(timeZone: string): string {
  const city = timeZone.split("/").pop() ?? timeZone;
  return city.replace(/_/g, " ");
}
