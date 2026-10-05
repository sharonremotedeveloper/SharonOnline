# V4 contract (written by Claude, integrator) - what Antigravity builds against

**Acceptance test:** `backend/tests/test_v4_attendance_contract.py` (14 tests). It must pass **unchanged** when V4 is done. If a test seems wrong, ask Claude; do not edit it to go green.

## What already exists on `develop` (the seam, do not redesign)
- `bookings/services/video_provider.py::uses_video_sdk(booking)`: SDK lesson = SDK configured AND no `zoom_meeting_id`. Lessons with a meeting id stay on the legacy Meetings path until V5.
- `bookings/services/fulfillment.py`: the zoom step is `SKIPPED` for SDK lessons (no Meetings room is created).
- `bookings/services/attendance_probe.py`: T+10 verdict for SDK lessons. Tutor absent: a tutor no-show only if the **student has a recorded join AND `probe_video_session` says `not_started`**; `started` marks the tutor present (in_progress); anything else defers and the lesson-end check disputes it. Both absent is never a tutor no-show. Exceptions from the probe are treated as `unknown`.
- Completion rule unchanged: `credited_attendance_minutes(booking, TEACHER) >= LESSON_DELIVERED_MIN_TEACHER_MINUTES` -> `completed_pending_memo`, otherwise DISPUTED.
- `tests/conftest.py`: SDK credentials are blanked for every test (a real key in `.env` must not change test behaviour); opt in with the `video_sdk_on` fixture.

## What V4 must implement
1. **`bookings/services/video_session_probe.py::probe_session(booking)`** (currently returns `unknown`): ask Zoom's Video SDK REST API (sessions for topic `lesson-<booking id>`, with participants) and return `started` only if the session is live and the tutor's `user_identity` is in it, `not_started` only if Zoom positively reports no tutor ever joined a session for this topic, otherwise `unknown`. S2S/OAuth token handling follows Z1's `zoom_auth` pattern (cache, timeout, backoff, never cache failures). Verify the account with `TOOL_ACCESS_AND_ACCOUNTS.md` before any live call; the SDK key/secret are only in `.env`.
2. **Evidence writer** (webhook receiver `POST /api/v1/integrations/video-sdk/webhooks/`, timing-safe HMAC, URL-validation challenge, idempotent on the event id; optional client heartbeat as a second source). Events `session.user_joined` / `session.user_left` (and `session.started/ended`) become `AttendanceAudit` rows: `classification` teacher or student by matching `user_identity` (our user UUID) to the booking's tutor/student, `identity='video_sdk'`, `join_time_utc`/`leave_time_utc`, `zoom_session_id` unique per join (webhook retries must not double count), `raw_payload` kept (R1 purges it at 90 days). An unmatched identity is kept as `unknown` with an empty e-mail and never counts.
3. A rejoin within the 5 minute grace counts as continuous presence (already handled by `present_with_disconnect_grace`; do not duplicate).

## Safety rules (F0, non-negotiable)
Silence, a lost webhook, a Zoom error or an unmatched participant is never evidence of absence. No code path in V4 may transition a booking to TEACHER_NO_SHOW/STUDENT_NO_SHOW directly; V4 only writes evidence and answers the probe. Every state change goes through `transition_booking()`.

## Tests V4 adds (in addition to the contract)
HMAC (valid/invalid/replay/timestamp), challenge response, idempotent retries, identity matching (tutor, student, stranger), leave without join, probe `started/not_started/unknown/exception/timeout` with mocked HTTP only, no secret in logs.
