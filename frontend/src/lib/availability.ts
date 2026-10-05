// Weekly availability matrix <-> API rows (Slice T2, docs/UI_VERTICAL_SLICE_MIGRATION_PLAN.md Slice 7).
// The grid is hourly blocks in the tutor's local clock; the API takes windows (`PUT /teachers/availability/replace/`).
import { ApiError } from "./http";

export interface AvailabilityRow {
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
}

export interface LessonConflict {
  booking_id: string;
  start_time_utc: string;
  end_time_utc: string;
}

export type WeeklyMatrix = { [day: number]: boolean[] };

export const DAYS = [
  { id: 0, label: "Mon", full: "Monday" },
  { id: 1, label: "Tue", full: "Tuesday" },
  { id: 2, label: "Wed", full: "Wednesday" },
  { id: 3, label: "Thu", full: "Thursday" },
  { id: 4, label: "Fri", full: "Friday" },
  { id: 5, label: "Sat", full: "Saturday" },
  { id: 6, label: "Sun", full: "Sunday" },
];

export const TIME_BLOCKS = [
  "08:00 - 09:00",
  "09:00 - 10:00",
  "10:00 - 11:00",
  "11:00 - 12:00",
  "13:00 - 14:00",
  "14:00 - 15:00",
  "15:00 - 16:00",
  "16:00 - 17:00",
  "17:00 - 18:00",
  "18:00 - 19:00",
  "19:00 - 20:00",
  "20:00 - 21:00",
];

const hhmm = (value: string) => value.slice(0, 5);

/** Open blocks -> API windows. Consecutive blocks merge into one window; the lunch gap (12:00-13:00) stays a gap. */
export function matrixToRows(schedule: WeeklyMatrix): Pick<AvailabilityRow, "day_of_week" | "start_time" | "end_time">[] {
  const rows: Pick<AvailabilityRow, "day_of_week" | "start_time" | "end_time">[] = [];
  for (const day of DAYS) {
    const blocks = schedule[day.id] ?? [];
    let start: string | null = null;
    let end: string | null = null;
    const flush = () => {
      if (start !== null && end !== null) rows.push({ day_of_week: day.id, start_time: start, end_time: end });
      start = end = null;
    };
    TIME_BLOCKS.forEach((range, index) => {
      const [from, to] = range.split(" - ");
      if (!blocks[index]) return flush();
      if (start !== null && end === from) {
        end = to;
      } else {
        flush();
        start = from;
        end = to;
      }
    });
    flush();
  }
  return rows;
}

/** Saved windows -> the grid: a block is open when one active window covers it completely. */
export function rowsToMatrix(rows: AvailabilityRow[]): WeeklyMatrix {
  const matrix: WeeklyMatrix = {};
  for (const day of DAYS) {
    matrix[day.id] = TIME_BLOCKS.map((range) => {
      const [from, to] = range.split(" - ");
      return rows.some(
        (r) => r.is_active && r.day_of_week === day.id && hhmm(r.start_time) <= from && hhmm(r.end_time) >= to
      );
    });
  }
  return matrix;
}

/** True when saving from the grid would change a saved window (off-grid hours, overlapping rows, inactive rows). */
export function wouldChangeSavedWindows(rows: AvailabilityRow[]): boolean {
  const key = (r: { day_of_week: number; start_time: string; end_time: string }) =>
    `${r.day_of_week}|${hhmm(r.start_time)}|${hhmm(r.end_time)}`;
  const saved = rows.filter((r) => r.is_active).map(key).sort();
  const regenerated = matrixToRows(rowsToMatrix(rows)).map(key).sort();
  return saved.length !== regenerated.length || saved.some((value, index) => value !== regenerated[index]);
}

/** The confirmed lessons a rejected save would strand, or null when the error is something else. */
export function conflictsFromError(err: unknown): LessonConflict[] | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const body = err.body as { code?: string; conflicts?: LessonConflict[] } | null;
  return body && body.code === "availability_conflicts" && Array.isArray(body.conflicts) ? body.conflicts : null;
}
