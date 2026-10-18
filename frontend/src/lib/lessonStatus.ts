/**
 * How a lesson's status reads in lists, and what a tutor can do next with it (TEA-06 lessons list). Pure, so tested.
 * Statuses: docs/BOOKING_STATE_MACHINE.md.
 */
export type StatusTone = "info" | "success" | "warning" | "error" | "neutral";

const STATUS: Record<string, { label: string; tone: StatusTone }> = {
  pending_payment: { label: "Awaiting payment", tone: "neutral" },
  confirmed: { label: "Confirmed", tone: "info" },
  in_progress: { label: "In progress", tone: "info" },
  completed_pending_memo: { label: "Memo due", tone: "warning" },
  completed: { label: "Completed", tone: "success" },
  completed_memo_forfeited: { label: "Completed (memo missed)", tone: "warning" },
  disputed: { label: "Disputed", tone: "warning" },
  interrupted_power: { label: "Interrupted (power cut)", tone: "warning" },
  student_no_show: { label: "Student no-show", tone: "error" },
  teacher_no_show: { label: "Tutor no-show", tone: "error" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  cancelled_by_student: { label: "Cancelled by student", tone: "neutral" },
  student_late_cancelled: { label: "Late cancellation", tone: "neutral" },
  cancelled_by_teacher: { label: "Cancelled by you", tone: "neutral" },
};

export function lessonStatus(status: string): { label: string; tone: StatusTone } {
  return STATUS[status] ?? { label: status.replace(/_/g, " "), tone: "neutral" };
}

export interface TutorLessonAction {
  kind: "classroom" | "memo";
  href: string;
  label: string;
}

/** The one next step for a tutor: write the memo when it is due, open the classroom for a lesson that has not ended. */
export function tutorLessonAction(
  lesson: { id: string; status: string; end_time_utc: string },
  now: number
): TutorLessonAction | null {
  if (lesson.status === "completed_pending_memo") {
    return { kind: "memo", href: `/teacher/bookings/${lesson.id}/memo`, label: "Write memo" };
  }
  if ((lesson.status === "confirmed" || lesson.status === "in_progress") && Date.parse(lesson.end_time_utc) >= now) {
    return { kind: "classroom", href: `/teacher/classroom/${lesson.id}`, label: "Open classroom" };
  }
  return null;
}

/** The tabs of the tutor lessons list and the server query each one makes (docs/BOOKING_LIST.md). */
export const TUTOR_LESSON_VIEWS = [
  { key: "upcoming", label: "Upcoming", query: { when: "upcoming", status: ["confirmed", "in_progress"] } },
  { key: "memo", label: "Memo due", query: { status: ["completed_pending_memo"], ordering: "start_time_utc" } },
  { key: "past", label: "Past", query: { when: "past" } },
] as const;

export function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .map((w) => w[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?"
  );
}

/**
 * "Sat, 17 Oct 2026" from the server's `local_date` (YYYY-MM-DD, already in the viewer's time zone). Formatted as a plain
 * calendar date (UTC) so the browser's own zone can never shift it to another day. Unparseable input is returned as is.
 */
export function formatLessonDate(localDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(localDate);
  if (!m) return localDate;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
