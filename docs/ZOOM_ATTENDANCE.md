# Zoom attendance mapping (Task 9.8)

> [!IMPORTANT]
> **ARCHITECTURAL UPDATE (2026-10-05): ZOOM VIDEO SDK ADOPTED — ZOOM MEETINGS S2S LABELED STALE / DEPRECATED**
> On 2026-10-05, the project officially resolved Decision **D-9** by approving the transition to **Zoom Video SDK** for embedded, in-browser classrooms.
> The legacy Zoom Meetings Server-to-Server (S2S) architecture described below (including `HostPicker`, single/pooled host license juggling, desktop Zoom app launching, and `zoommtg://` URLs) is **STALE / DEPRECATED** and will be superseded by the in-browser Video SDK architecture.
> See full roadmap and implementation design in [`ZOOM_VIDEO_SDK_MIGRATION_PLAN.md`](./ZOOM_VIDEO_SDK_MIGRATION_PLAN.md).

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
* **C3 - Z1: DONE** (token cache, see "Client contract" below).
* **C4 - sandbox check (Z1):** `GET /users/{host}/meetings?type=scheduled` returns `agenda` in its list items (the create
  search matches the marker line in it; the client falls back to exact topic + start time if it does not); the host `start_url`
  ZAK lifetime (about 2 h?); the `Retry-After` format on 429.
* **Done in N1a:** every `[ADMIN ALERT]` log line from F0 (fulfilment needs attention / failed, orphaned meeting or
  calendar event, lesson disputed without a verdict) also raises `alert_staff(...)` (`NOTIFICATIONS.md` §2.7); the log line
  stays. Go-live still needs `ADMIN_ALERT_RECIPIENTS` set (or an active admin) and a worker on the `notifications` queue.
  The staff-host-link warning (Z1) is not routed yet: N2/P1.

## Video SDK lessons (D-9, slices V1-V4; contract `tests/test_v4_attendance_contract.py`)

A lesson with **no `zoom_meeting_id`** while the Video SDK is configured is an SDK lesson (`bookings/services/video_provider.py`):
the room is the in-browser classroom `lesson-<booking id>`, fulfilment **skips** the Meetings step (`zoom_state = skipped`), and
lessons that already have a meeting id stay on the Meetings rules above until V5. The verdict rules keep the F0 semantics:

| Situation at T+10 (tutor not in the attendance records) | Result |
| :--- | :--- |
| the student has a recorded join AND `probe_video_session` answers `not_started` (Zoom positively says no tutor session started) | `teacher_no_show` (strike, refund, bonus credit) |
| probe `started` (the tutor is in the live session) | `in_progress` (+ probe attendance row), no no-show |
| probe `unknown`, an exception, the student also absent, or no evidence at all | deferred; still unresolved at the lesson end -> `disputed` + open `DisputeCase`; **never a no-show** |
| tutor present in the records, student absent | `student_no_show` (as before) |

Evidence is `AttendanceAudit` rows (classification teacher/student, join/leave, `identity='video_sdk'`, one `zoom_session_id` per
join) written by V4 from Video SDK webhooks / client heartbeats; V4 never decides a verdict. Completion is unchanged: >= 20
credited tutor minutes -> `completed_pending_memo`, otherwise `disputed`. Both absent is deliberately **not** a tutor no-show
here (the Meetings path scores it; the SDK path needs the student's join as proof the room was open).

## Client contract (Slice Z1, `integrations/zoom.py`, `zoom_auth.py`, `zoom_hosts.py`)

* **Credentials** are Django settings `ZOOM_ACCOUNT_ID` / `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET` (no environment reads in app
  code). Production refuses to boot without them (`config/settings/guard.py::ZOOM_CREDENTIAL_SETTINGS`), and
  `scripts/check_deploy.py` reports the same three names. Tests blank them in the autouse fixture; `fake_zoom` sets fake ones.
* **Token cache (closes F0 condition C3).** One S2S token per account id in the Django cache (Redis in production), kept for
  `expires_in - 60 s`; a token living 60 s or less is used once and not cached. Single-flight: the worker that wins
  `cache.add(<key>:lock)` (15 s, owner-checked release) fetches; others poll every 0.25 s for up to `ZOOM_TOKEN_WAIT_SECONDS`
  (5) and then fetch themselves. Failures are never cached. A **401** invalidates the cached token (only if it is still the
  refused one) and the request is sent **once** more with a fresh token (a token Zoom refused is never handed out again); a
  second 401 is final. The token lives only in the cache and memory, never in a log.
* **Retries.** Only **429** and **5xx**, at most `ZOOM_HTTP_MAX_ATTEMPTS` (3) tries per call. 429 honours `Retry-After`
  (seconds or HTTP date) up to `ZOOM_RETRY_AFTER_CAP_SECONDS` (10); a longer one is not slept: the call raises `ZoomError`
  with `retry_after_seconds`, which fulfilment uses as its minimum retry delay. Without Retry-After, and for 5xx: full-jitter
  exponential back-off (0.5 s doubling, capped at 10 s). Other 4xx are final at once. Timeouts / connection errors raise
  `ZoomAmbiguous` and are **not** retried by reads (the T+10 probe reads that as `unknown` and probes again next minute).
  Every request has `timeout=ZOOM_HTTP_TIMEOUT_SECONDS` (10). The token request follows the same policy.
* **Errors** carry the HTTP status (`ZoomError.status`) and never Zoom's body; `ZoomNotFound` for 404.
* **create_meeting is never retried blind.** Every lesson meeting's agenda carries a marker line
  `sharon-booking:<booking id>`. After an ambiguous outcome (timeout, connection error or 5xx: Zoom may have built the room
  and lost the response) the client lists the host's scheduled meetings (`type=scheduled`, `from`/`to` = the lesson's UTC
  date +- 1 day, paged, at most 10 pages; Zoom caps one listing at about 3000 meetings, see the D-9 checklist) and reuses the one whose
  agenda has that exact marker line **and** the same start time (a rescheduled lesson's old room carries the same marker
  until the cleanup task deletes it); only if none is found does it POST again (with back-off, bounded by
  `ZOOM_HTTP_MAX_ATTEMPTS`). A failed search raises: no second POST. 429 on create is retried without a search (Zoom did not
  process it). Fulfilment passes `search_first=True` after ANY earlier attempt (`attempts > 1`, which also covers a worker that
  died after Zoom built the room and whose claim was reclaimed, or a previously FAILED zoom step), so a lost response from
  an earlier *attempt* is found before a new room is built. Host and meeting ids are validated before they enter a URL
  (`.`/`..`, slashes, queries rejected); a 201 without an id raises. Without a booking id an ambiguous create is never retried.
  *Why a marker in Zoom, not a stored request marker:* it needs no database write before the HTTP call, survives a worker
  crash between the call and our save, and a stored marker would still need the same search to learn whether Zoom created
  the meeting.
* **`auto_recording: "none"`** is set explicitly on create (D-8: no recording in the MVP, whatever the account default).
* **No silent `return ""`**: without credentials `get_access_token` raises (guard allowlist for `zoom.py` is now 0).

## Host link (Slice Z1)

The host `start_url` embeds a ZAK that expires (about 2 h for a regular user; verify in the sandbox, C4). Since Z1 it is
**never stored, e-mailed or copied into a calendar event**: fulfilment no longer writes `Booking.zoom_start_url`, migration
`bookings/0015` blanked existing values (reverse is a no-op), and the tutor's Google Calendar event carries only the join
URL. `BookingDetailSerializer.zoom_start_url` stays in the contract for one release but is always `""` (deprecated) and
`zoom_url` is the join URL for everyone. The column is dropped in a later release.

`GET /api/v1/bookings/{id}/host-link/` (`bookings/host_link_views.py`, service `bookings/services/host_link.py`) fetches a
fresh link from Zoom (`GET /meetings/{id}`) when the classroom opens:

| Caller / state | Answer |
| :--- | :--- |
| the booking's tutor, or staff (role admin / is_staff / superuser), lesson `confirmed` or `in_progress`, meeting id set, from `ZOOM_HOST_LINK_OPEN_MINUTES_BEFORE` (15) minutes before the start until `end_time_utc` | 200 `{meeting_id, start_url}`, `Cache-Control: no-store` |
| the booking's student | 403 `host_only` |
| anyone else, or unknown booking | 404 `not_found` |
| not live / no meeting id / ended / before the window | 409 `not_live` / `no_meeting` / `lesson_ended` / `too_early` |
| Zoom 404 for the meeting | 409 `meeting_missing` + `[ADMIN ALERT]` log |
| any other Zoom failure, or any unexpected error while fetching | 502 `zoom_unavailable` (no provider detail; error type logged) |

Throttle scope `zoom_host_link` (30/hour per user). Logs carry booking / user / meeting ids only.

**Staff hosting (QA #3).** Whoever opens the host link IS the host, and the attendance rule credits the host (`host_id`) as the
tutor. A link issued to staff who are not the tutor therefore writes a `bookings.HostLinkIssue` row (staff user id, time;
migration `bookings/0016`) and **holds the lesson's escrow release**: `settlement.attendance_verified_for_release` returns
False while an unreviewed row exists (also for a student no-show or a late-cancel, whose attendance would otherwise be
taken on trust). An admin clears the hold in Django admin ("Host link issues" -> action "Mark reviewed", which records the
reviewer) after checking who really attended. Use the staff path only to rescue a lesson. **Who may review** (re-review): the
action needs `is_active`, `is_staff` and (superuser or role admin), like the fulfilment re-queue and notification re-send
admins; a reviewer cannot clear a link issued to themselves unless superuser. The same predicate (`host_link.can_review`)
decides who may obtain a staff host link at all, so no hold can be created that nobody is able to clear. Open question for
N2/P1: alert the admin when a row is created (today only a `[WARNING]` log line with ids). The money effect is described in
`SETTLEMENT_PATHS.md` (staff-hosted lesson row). **This hold is part of the legacy Meetings path and will retire with the
Zoom Video SDK migration (V5).**

**Frontend (done in Z1, not F1).** `lib/hostLink.ts` (`api.getHostLink`) fetches the link when the tutor presses "Start Lesson
as Host"; `ZoomLauncherButton` (host mode) opens it in a new tab with `noopener,noreferrer`, shows what to do on 409
(not open yet / ended / no room) and 502 (try again), keeps the link only in memory so the tutor can click again if the
browser blocked the tab, and only opens an `https` zoom.us address. The tutor page no longer falls back to the guest join
link, and the host mode hides the web-join toggle and the direct join link (a tutor joining as a guest is not the host: with
`join_before_host` off the room never opens and the lesson would end as a teacher no-show). F1 keeps the join gating helper.

**Cache outage (QA #4).** Every cache call in `zoom_auth.py` is guarded: a failing read/lock degrades to a direct token fetch
(no caching, no lock), a failing write/delete is skipped; one warning with the error type only. The lock TTL
(`ZOOM_HTTP_MAX_ATTEMPTS * (timeout + Retry-After cap) + 5` = 65 s by default) outlives the worst-case fetch.

## Host allocation (Slice Z1, `integrations/zoom_hosts.py`): LAUNCH BLOCKER pending D-9

`HostPicker.pick_host(booking)` returns `settings.ZOOM_HOST_USER_ID` (default `'me'`, the account owning the S2S app);
fulfilment creates the meeting under that user and stores it in `Booking.zoom_host_user_id` (nullable, migration
`bookings/0014`; cleared on reschedule; null = no meeting or created before Z1, i.e. `'me'`). The host id is validated
(`[A-Za-z0-9_.@+-]{1,64}`) before it goes into a URL path. **One host account can run one meeting at a time: two concurrent
lessons collide on the single licence.** This is a launch blocker until D-9 (host pool) replaces `pick_host` with an
allocation; probe, delete and host-link paths already work by meeting id and need no change.

**D-9 launch checklist (Zoom side):** licences / alternative hosts for the expected concurrency; the marker search lists a
host's scheduled meetings (Zoom returns at most about 3000 per listing, and the search is bounded to the lesson's day +- 1
by `from`/`to`), so a pool host with a very large backlog needs the pool split or the search narrowed further; confirm
`from`/`to` are honoured for `type=scheduled` and that the list payload carries `agenda` (C4).

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

* Meetings are created under the host chosen by `HostPicker` (today the platform's one Zoom account: single host = launch blocker pending D-9), so the tutor's host link joins as that account (`host_id`). If tutors ever get their own Zoom hosts, `classify` still works (the host is still the tutor).
* `participant.user_id` is per join session; `participant_uuid` is the fallback key.
* The student join link is not personal, so the student is identified by the e-mail they joined with, which is self-asserted for guests. **Registrant links** (Zoom registration, one personal join URL per student) would make this verified; it needs a Zoom plan that supports registration and a `registrants` call at fulfillment time. Not built.

## Known limits

* Two overlapping sessions by the same person (two devices) are summed, not merged.
* A tutor who joins as a plain guest (join link, not signed in) is not recognised and gets a teacher no-show at T+10; the invariant is that only the host link proves the tutor.
