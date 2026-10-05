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
| meeting id present, Zoom says `waiting` **and** `GET /past_meetings/{id}/instances` returns an empty list | `not_started` | `teacher_no_show` (strike, refund, bonus credit) |
| Zoom says `waiting` but a past instance exists (a scheduled meeting reverts to `waiting` after it ends), or the past-instance call is not a clear 200 + list | `unknown` | deferred, as below |
| meeting id present, Zoom says `started` | `started` | `in_progress` (+ `active_zoom_probe` attendance row). **No student no-show** from probe-only presence: the webhooks may have been lost, so missing student rows prove nothing; the lesson-end check decides |
| non-200 / timeout / **OAuth token failure (401/429/5xx, or a 200 without a token)** / any exception / a 200 **without** `status` / any other status | `unknown` | **nothing changes**; the next beat run (every 60 s) probes again |
| still `unknown` (or never adjudicated) when the lesson window ends | - | `disputed` + an open `DisputeCase` (reason "no attendance verdict before the lesson ended ..."); no refund, strike or credit |
| **no meeting id** (fulfilment never built a room) | not probed | `disputed` + open `DisputeCase` at T+10 ("no Zoom meeting provisioned"); never a no-show |

* The HTTP probes run **first**, holding no database row lock and no task lock (`probe_t10_candidates`), bounded by
  `ATTENDANCE_PROBE_BUDGET_SECONDS` (default 25 s, under the 50 s beat lock); a lesson not probed inside the budget counts as
  `unknown` (deferred). Then, under the task lock, each booking is row-locked (`select_for_update(of=('self',))`), its status
  and meeting id are re-checked, and the verdict applied. A probe of a meeting id that changed meanwhile is ignored (deferred).
* Admin alert: the open `DisputeCase` (admin disputes screen), a `[ADMIN ALERT]` log line with the booking id, and (since
  N1a) `alert_staff('lesson_disputed_without_verdict')`: an in-app item + e-mail to `ADMIN_ALERT_RECIPIENTS`.
* **Credentials and simulation (review B1).** With Zoom credentials configured, a failed OAuth token request **raises
  `ZoomError`** from create / status / past-instances / delete (logged with the HTTP status only, never the provider body): no
  fabricated room, no simulated `waiting`, no silent "deleted". Simulated rooms and a simulated `waiting` status exist only when
  credentials are absent **and** `ZOOM_SIMULATE_WITHOUT_CREDENTIALS` is on (only `config/settings/local.py` sets it;
  production inherits `False` from `base.py`) **and** `DEBUG` is on (re-review C1). Tests opt in explicitly with the
  `simulated_zoom` fixture; tests that mean "Zoom says waiting and the meeting was never held" use `zoom_never_held`.
  `scripts/check_deploy.py` fails when `ZOOM_ACCOUNT_ID` / `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET` is missing.
* **Docker compose is dev-only for attendance.** It runs `config.settings.local`; without Zoom credentials it either simulates
  (DEBUG on: every simulated room reads `waiting` with no past instance, so a lesson nobody joins becomes a teacher no-show)
  or raises (DEBUG off: lessons get no room and end DISPUTED). Never run real lessons, a shared demo or staging attendance on
  a compose stack without real Zoom credentials.

### Open conditions handed on
* **C2 - sandbox check (before launch):** call `GET /past_meetings/{id}/instances` for a meeting that was never held (200 with
  `meetings: []`, or 404?) and measure how soon an instance appears after a meeting ends. A 404 would turn every real
  no-show into DISPUTED (safe but manual); a slow instance would let a just-ended lesson read `waiting` + no instance.
* **C3 - Z1:** cache the Server-to-Server OAuth token (about 55 min TTL, keyed by account, single-flight, invalidated on 401).
  Today every probe/create/delete requests a new token.
* **Done in N1a:** every `[ADMIN ALERT]` log line from F0 (fulfilment needs attention / failed, orphaned meeting or
  calendar event, lesson disputed without a verdict) also raises `alert_staff(...)` (`NOTIFICATIONS.md` §2.7); the log line
  stays. Go-live still needs `ADMIN_ALERT_RECIPIENTS` set (or an active admin) and a worker on the `notifications` queue.

## Fulfilment (Slice F0, `bookings/services/fulfillment.py`)

The Zoom room, tutor calendar event and confirmation e-mail are provisioned by one `FulfillmentDispatch` per booking:
compare-and-swap claim (`QUEUED|PENDING -> RUNNING`, and `RETRYABLE` only once `next_retry_at` has passed, with a token, one
conditional UPDATE; a RUNNING claim older than `FULFILLMENT_LEASE_SECONDS` is reclaimable), the booking re-checked `confirmed`
under its row lock, `update_fields` writes only, per-step `done | skipped | failed` (no Google token = `skipped`), and a Zoom
meeting **or calendar event** that could not be kept (lesson cancelled or moved meanwhile, claim lost, one already stored, save
failed) deleted again. The calendar sync only returns the event id; fulfilment stores it under the row lock. E-mail success is
explicit (`True`, or a result with status `sent`). A **reschedule resets the dispatch inside its transaction**, so the moved
lesson gets a new room (the old one is deleted) and a run still working on the old time loses its claim.

**Retries (review M4).** A failed step makes the row RETRYABLE with jittered exponential backoff (`FULFILLMENT_RETRY_SECONDS`
= 30 s doubling, +-20 %, capped at `FULFILLMENT_RETRY_MAX_SECONDS` = 30 min, never earlier than a provider's
`retry_after_seconds`) and schedules the next attempt with `apply_async(countdown=...)`. A replayed webhook cannot jump the
queue: `requeue` leaves a not-yet-due RETRYABLE row untouched. Terminal `failed` comes at once for a permanent e-mail failure,
and otherwise only after `FULFILLMENT_MAX_ATTEMPTS` **once the lesson has started** (before that every retry may still save the
lesson; after it, a room no longer helps and the T+10 guard disputes a lesson without one). Staff get an `[ADMIN ALERT]` log
line (booking id only) when the cap is reached and again when it becomes terminal. The 5-minute sweep
(`retry_fulfillment_dispatches_task`) is the safety net: due RETRYABLE rows, RUNNING rows past the lease, and PENDING/QUEUED
rows untouched for `FULFILLMENT_QUEUED_STALE_SECONDS` (= 120 s; a lost or early-acked message). Django admin
**Fulfillment dispatches -> "Re-queue FAILED fulfilment"** (staff with the admin role or superusers) gives a FAILED row a fresh
set of attempts; each re-queue is logged with the booking id and the actor id.

**Deploying migration `payments/0022` (runbook):** drain the Celery workers (stop consuming the `critical_io` queue and wait
for running fulfilment tasks to finish) **before** migrating. Workers still running the old code set `RUNNING` without
`claimed_at`; such rows count as stale (the lease treats `claimed_at IS NULL` as expired) and are re-run by the sweep, but
draining avoids a second room being created by an old worker and a new one at the same time.

## Assumptions to confirm against real Zoom (Phase 11 / sandbox)

* `GET /meetings/{id}` returns `status: waiting` for a scheduled meeting nobody has started and `started` while it runs;
  anything else (including `finished`, if Zoom ever reports it) is treated as `unknown`. Verify in the sandbox.
* `GET /past_meetings/{id}/instances` returns **200 with `meetings: []`** for a meeting that never ran. If the sandbox shows a
  404 instead, every real tutor no-show becomes `unknown` and ends as DISPUTED (safe: nobody is wrongly penalised, but no
  automatic no-show); then map that specific 404 to "no instances" after confirming it.

* Meetings are created under the platform's one Zoom account, so the tutor's host link joins as that account (`host_id`). If tutors ever get their own Zoom hosts, `classify` still works (the host is still the tutor).
* `participant.user_id` is per join session; `participant_uuid` is the fallback key.
* The student join link is not personal, so the student is identified by the e-mail they joined with, which is self-asserted for guests. **Registrant links** (Zoom registration, one personal join URL per student) would make this verified; it needs a Zoom plan that supports registration and a `registrants` call at fulfillment time. Not built.

## Known limits

* Two overlapping sessions by the same person (two devices) are summed, not merged.
* A tutor who joins as a plain guest (join link, not signed in) is not recognised and gets a teacher no-show at T+10; the invariant is that only the host link proves the tutor.
