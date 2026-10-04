# Zoom attendance mapping (Task 9.8)

Attendance decides no-show verdicts (T+10), the 20-minute completion rule, escrow release and disputes, and all of it
reads `AttendanceAudit.classification`. So the rule is: **only an explicit `teacher` or `student` classification counts;
`unknown` evidence never changes state or money.** The decision lives in one place, `integrations/services/attendance.py::classify()`; the
webhook view only parses, locks the booking and dispatches.

## Who is who

| Participant | `classification` | `identity` | Stored `participant_email` |
| :--- | :--- | :--- | :--- |
| Zoom account id equals the payload `host_id` (whoever opened the host/start link) | tutor | `host` | tutor's account e-mail |
| Signed-in Zoom account (non-empty `participant.id`) whose e-mail is the tutor's | tutor | `account_email` | tutor's account e-mail |
| Joined with the student's e-mail (case-insensitive) | student | `email` | student's account e-mail |
| `meeting.started` (the host opened the room) | tutor present | `meeting_started` | tutor's account e-mail, **0 minutes** |
| Anyone else | `unknown` | `unmatched` | empty (raw payload kept as evidence) |

Each attendance row also retains Zoom participant ID, registrant ID, host ID, event IDs, session ID, and raw payload. Unknown
rows are read-only in Django administration for investigation, but every no-show, completion, and settlement query filters by
classification.

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
* **Five-minute disconnect grace** treats a participant as present for five minutes after a leave event and merges reconnect gaps of at most five minutes when calculating credited lesson attendance.
* **Active probing** accepts only Zoom's authoritative `started` meeting status as host evidence. A non-zero participant count alone proves no identity and cannot prevent a no-show.
* The T+10 job now also looks at `in_progress` bookings: tutor present + student absent -> `student_no_show` (previously unreachable once the tutor's join had moved the booking out of `confirmed`, so a student no-show ended as a normal completion).
* Malformed payloads (non-object `payload`/`object`/`participant`) are acknowledged and ignored, not 500s.
* `ZoomClient.create_meeting` raises `ZoomError` carrying Zoom's reason when Zoom rejects the request (it used to return `None`, which surfaced as an opaque `TypeError` in the fulfillment task).

## T+10 probe and verdict (Slice F0, `bookings/services/attendance_probe.py`)

A teacher no-show refunds the student, grants a bonus credit and strikes the tutor, so it needs positive evidence.

| Situation at T+10 (tutor not seen in attendance) | Probe answer | Result |
| :--- | :--- | :--- |
| meeting id present, Zoom says `waiting` | `not_started` | `teacher_no_show` (strike, refund, bonus credit) |
| meeting id present, Zoom says `started` | `started` | `in_progress` (+ `active_zoom_probe` attendance row); student absent -> `student_no_show` |
| non-200 / `error` / timeout / auth failure / any exception / unexpected payload | `unknown` | **nothing changes**; the next beat run (every 60 s) probes again |
| still `unknown` (or never adjudicated) when the lesson window ends | - | `disputed` + an open `DisputeCase` (reason "no attendance verdict before the lesson ended ..."); no refund, strike or credit |
| **no meeting id** (fulfilment never built a room) | not probed | `disputed` + open `DisputeCase` at T+10 ("no Zoom meeting provisioned"); never a no-show |

* The HTTP probes run **first**, holding no database row lock and no task lock (`probe_t10_candidates`), bounded by
  `ATTENDANCE_PROBE_BUDGET_SECONDS` (default 25 s, under the 50 s beat lock); a lesson not probed inside the budget counts as
  `unknown` (deferred). Then, under the task lock, each booking is row-locked (`select_for_update(of=('self',))`), its status
  and meeting id are re-checked, and the verdict applied. A probe of a meeting id that changed meanwhile is ignored (deferred).
* Admin alert today: the open `DisputeCase` (admin disputes screen) plus a `[ADMIN ALERT]` log line with the booking id.
  `notify()` to `ADMIN_ALERT_RECIPIENTS` arrives with N1a.
* Without Zoom credentials `ZoomClient.get_meeting_status` still returns a simulated `waiting`; removing that mock in
  production is Z1's job (plan section 3.3).

## Fulfilment (Slice F0, `bookings/services/fulfillment.py`)

The Zoom room, tutor calendar event and confirmation e-mail are provisioned by one `FulfillmentDispatch` per booking:
compare-and-swap claim (`QUEUED|RETRYABLE|PENDING -> RUNNING` with a token, one conditional UPDATE; a RUNNING claim older than
`FULFILLMENT_LEASE_SECONDS` is reclaimable), the booking re-checked `confirmed` under its row lock, `update_fields` writes only,
per-step `done | skipped | failed` (no Google token = `skipped`), `FULFILLMENT_MAX_ATTEMPTS` then terminal `failed` + admin
alert, a permanent e-mail failure terminal at once, and a meeting that could not be kept (lesson cancelled or moved meanwhile,
save failed) deleted again. A **reschedule resets the dispatch inside its transaction**, so the moved lesson gets a new room
(the old one is deleted) and a run still working on the old time loses its claim.

## Assumptions to confirm against real Zoom (Phase 11 / sandbox)

* `GET /meetings/{id}` returns `status: waiting` for a scheduled meeting nobody has started and `started` while it runs;
  anything else (including `finished`, if Zoom ever reports it) is treated as `unknown`. Verify in the sandbox.

* Meetings are created under the platform's one Zoom account, so the tutor's host link joins as that account (`host_id`). If tutors ever get their own Zoom hosts, `classify` still works (the host is still the tutor).
* `participant.user_id` is per join session; `participant_uuid` is the fallback key.
* The student join link is not personal, so the student is identified by the e-mail they joined with, which is self-asserted for guests. **Registrant links** (Zoom registration, one personal join URL per student) would make this verified; it needs a Zoom plan that supports registration and a `registrants` call at fulfillment time. Not built.

## Known limits

* Two overlapping sessions by the same person (two devices) are summed, not merged.
* A tutor who joins as a plain guest (join link, not signed in) is not recognised and gets a teacher no-show at T+10; the invariant is that only the host link proves the tutor.
