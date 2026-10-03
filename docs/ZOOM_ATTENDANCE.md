# Zoom attendance mapping (Task 9.8)

Attendance decides no-show verdicts (T+10), the 20-minute completion rule, escrow release and disputes, and all of it
reads `AttendanceAudit.participant_email`. So the rule is: **a row only carries an account e-mail when the participant
was positively identified.** The decision lives in one place, `integrations/services/attendance.py::classify()`; the
webhook view only parses, locks the booking and dispatches.

## Who is who

| Participant | Identified as | `identity` | Stored `participant_email` |
| :--- | :--- | :--- | :--- |
| Zoom account id equals the payload `host_id` (whoever opened the host/start link) | tutor | `host` | tutor's account e-mail |
| Signed-in Zoom account (non-empty `participant.id`) whose e-mail is the tutor's | tutor | `account_email` | tutor's account e-mail |
| Joined with the student's e-mail (case-insensitive) | student | `email` | student's account e-mail |
| `meeting.started` (the host opened the room) | tutor present | `meeting_started` | tutor's account e-mail, **0 minutes** |
| Anyone else | nobody | `unmatched` | empty (raw payload kept as evidence) |

What changed: a guest used to be recorded as the student by default, the tutor was matched on a self-typed e-mail, and the
host check compared the host id with the per-session `user_id` (the wrong field). A guest typing the tutor's e-mail can no
longer stop a teacher no-show verdict, and a stranger can no longer stand in for an absent student.

## Events

* **Idempotent**: rows are keyed by the Zoom join session (`zoom_session_id`, unique per booking). A retried join/leave
  fills in only what is missing; it never resets a recorded leave or double-transitions the booking. If Zoom reuses an id
  when someone rejoins, a join after that session's leave starts a new row (`<id>@<join ts>`) and later leaves close the open one.
* **Out of order** delivery (leave before join) converges on the same row and minutes. A leave earlier than its join gives 0 minutes, never negative.
* **Zoom's clock**: `meeting.ended` closes open sessions at the payload `end_time` (our clock is only the fallback). Unparseable times fall back to now (logged) instead of failing the webhook.
* **`meeting.started`** records the tutor as present (no minutes) and moves the booking to `in_progress`, so a lost `participant_joined` no longer produces a false teacher no-show.
* **In progress** now means *the tutor is in the room*; a student alone leaves the booking `confirmed`.
* **Late telemetry after a verdict** opens a dispute only from the party the verdict blamed: tutor activity after `teacher_no_show`, student activity after `student_no_show`. Strangers and the other party are recorded but change nothing.
* The T+10 job now also looks at `in_progress` bookings: tutor present + student absent -> `student_no_show` (previously unreachable once the tutor's join had moved the booking out of `confirmed`, so a student no-show ended as a normal completion).
* Malformed payloads (non-object `payload`/`object`/`participant`) are acknowledged and ignored, not 500s.
* `ZoomClient.create_meeting` raises `ZoomError` carrying Zoom's reason when Zoom rejects the request (it used to return `None`, which surfaced as an opaque `TypeError` in the fulfillment task).

## Assumptions to confirm against real Zoom (Phase 11 / sandbox)

* Meetings are created under the platform's one Zoom account, so the tutor's host link joins as that account (`host_id`). If tutors ever get their own Zoom hosts, `classify` still works (the host is still the tutor).
* `participant.user_id` is per join session; `participant_uuid` is the fallback key.
* The student join link is not personal, so the student is identified by the e-mail they joined with, which is self-asserted for guests. **Registrant links** (Zoom registration, one personal join URL per student) would make this verified; it needs a Zoom plan that supports registration and a `registrants` call at fulfillment time. Not built.

## Known limits

* Two overlapping sessions by the same person (two devices) are summed, not merged.
* A tutor who joins as a plain guest (join link, not signed in) is not recognised and gets a teacher no-show at T+10; the invariant is that only the host link proves the tutor.
