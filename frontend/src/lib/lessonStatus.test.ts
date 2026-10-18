import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { formatLessonDate, initials, lessonStatus, TUTOR_LESSON_VIEWS, tutorLessonAction } from "./lessonStatus";

const NOW = Date.parse("2026-10-18T10:00:00Z");

describe("tutor lessons list", () => {
  it("offers the memo when it is due, the classroom only before the lesson ends", () => {
    assert.equal(tutorLessonAction({ id: "b1", status: "completed_pending_memo", end_time_utc: "2026-10-17T10:00:00Z" }, NOW)?.href,
      "/teacher/bookings/b1/memo");
    assert.equal(tutorLessonAction({ id: "b2", status: "confirmed", end_time_utc: "2026-10-18T10:25:00Z" }, NOW)?.kind, "classroom");
    assert.equal(tutorLessonAction({ id: "b3", status: "confirmed", end_time_utc: "2026-10-18T09:59:00Z" }, NOW), null);
    assert.equal(tutorLessonAction({ id: "b4", status: "cancelled_by_student", end_time_utc: "2026-10-19T10:00:00Z" }, NOW), null);
    assert.equal(tutorLessonAction({ id: "b5", status: "completed", end_time_utc: "2026-10-17T10:00:00Z" }, NOW), null);
  });

  it("labels every booking status and never shows a raw code", () => {
    for (const s of ["pending_payment", "confirmed", "in_progress", "completed", "cancelled", "disputed", "interrupted_power",
      "student_no_show", "teacher_no_show", "completed_pending_memo", "completed_memo_forfeited", "cancelled_by_student",
      "student_late_cancelled", "cancelled_by_teacher"]) {
      assert.doesNotMatch(lessonStatus(s).label, /_/, s);
    }
    assert.equal(lessonStatus("completed_pending_memo").tone, "warning");
    assert.equal(lessonStatus("brand_new").label, "brand new");
  });

  it("asks the server for upcoming confirmed lessons and due memos oldest first", () => {
    assert.deepEqual(TUTOR_LESSON_VIEWS.map((v) => v.key), ["upcoming", "memo", "past"]);
    assert.equal(TUTOR_LESSON_VIEWS[1].query.ordering, "start_time_utc");
  });

  it("makes initials from names", () => {
    assert.equal(initials("Aiko  Tanaka"), "AT");
    assert.equal(initials("Sharon Ncube Moyo"), "SN");
    assert.equal(initials(""), "?");
  });

  it("formats the lesson day without shifting it to another day", () => {
    assert.equal(formatLessonDate("2026-10-17"), "Sat, 17 Oct 2026");
    assert.equal(formatLessonDate("2026-01-01"), "Thu, 1 Jan 2026");
    assert.equal(formatLessonDate("Oct 17, 2026"), "Oct 17, 2026");
  });
});
