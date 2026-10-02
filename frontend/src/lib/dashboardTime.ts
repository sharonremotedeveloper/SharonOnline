import { formatInTimeZone, fromZonedTime } from "date-fns-tz";

/** UTC query bounds for the viewer's local calendar day and month. */
export function viewerPeriodBounds(timezone: string, now = new Date()) {
  const localDate = formatInTimeZone(now, timezone, "yyyy-MM-dd");
  const localMonth = formatInTimeZone(now, timezone, "yyyy-MM");
  return {
    dayStart: fromZonedTime(`${localDate}T00:00:00`, timezone).toISOString(),
    dayEnd: fromZonedTime(`${localDate}T23:59:59.999`, timezone).toISOString(),
    monthStart: fromZonedTime(`${localMonth}-01T00:00:00`, timezone).toISOString(),
  };
}
