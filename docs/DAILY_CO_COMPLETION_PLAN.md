# Daily.co Completion Plan

**Branch:** `feature/antigravity-repair`
**Scope:** development implementation and provider wiring only; production credentials and services remain untouched.

## Current position

Daily.co is the approved primary video provider (Decision D-14). The current `develop` migration has been integrated into this Antigravity branch while preserving its existing UI repair changes. The migration supplies token generation, a Daily classroom component, and webhook handling; this work adds room lifecycle integration, Daily-first attendance probing, cleanup on cancellation/rescheduling, and a focused room lifecycle test suite. Railway development credentials and the development webhook are now configured; real provider events and two-browser joining remain outstanding.

Existing uncommitted Antigravity UI repairs must be preserved.

## Implementation sequence

1. Integrate the current `develop` history into this branch without losing the existing Antigravity work.
2. Audit the integrated Daily implementation and keep Zoom support only as an explicit legacy path for existing Zoom bookings.
3. Implement idempotent Daily room provisioning:
   - deterministic room name per booking;
   - private room configuration;
   - bounded expiration around the lesson window;
   - safe reuse on retries;
   - typed handling for duplicate, auth, timeout, rate-limit, and provider failures.
4. Connect provisioning to the confirmed-booking fulfillment path without weakening payment, escrow, calendar, notification, or state-machine boundaries.
5. Make token issuance provider-aware and require successful room readiness before issuing a Daily token.
6. Replace the Zoom-only presence probe with Daily presence semantics while preserving `UNKNOWN` on provider failure and never converting uncertainty into a no-show.
7. Harden Daily webhooks for signature/timestamp validation, URL validation, malformed/out-of-order events, booking-room ownership, idempotency, and unknown participants.
8. Preserve historical Zoom attendance while introducing provider-neutral attendance identifiers where needed; do not remove legacy columns in this migration.
9. Verify the student and tutor frontend classroom paths and remove accidental Zoom links from new Daily bookings while retaining an intentional legacy fallback if required.
10. Add strict unit, integration, and frontend tests for room lifecycle, token roles/window, presence, webhook replay/idempotency, and failure recovery. Credential-dependent tests must be explicit live-smoke tests, not silently skipped acceptance tests.
11. Update environment examples, deployment guard documentation, migration/readiness docs, rollback instructions, and progress tracking. Credentials remain owner-supplied later.
12. Run focused backend/frontend gates, then the full available gates. Report provider/browser verification separately from automated evidence.

## Implementation progress

- [x] Integrated current `develop` Daily migration into `feature/antigravity-repair` without dropping Antigravity changes.
- [x] Added idempotent private Daily room creation with lesson-window `nbf`/`exp` bounds.
- [x] Added Daily room deletion and wired cancellation/rescheduling cleanup.
- [x] Connected Daily room readiness to confirmed-booking fulfillment before token issuance.
- [x] Made the attendance probe prefer Daily presence when Daily is configured; Zoom remains a legacy fallback.
- [x] Prevented the Daily frontend `left-meeting` event from calling `leave()` recursively during SDK teardown.
- [x] Added focused room reuse, creation, expiry, and deletion tests.
- [x] Configure `DAILY_API_KEY`, `DAILY_DOMAIN`, and `DAILY_WEBHOOK_SECRET` in Railway development without recording secret values in source control.
- [x] Register and read back the active Daily development webhook for `participant.joined` and `participant.left`.
- [x] Verify a signed development delivery reaches the receiver and returns HTTP 200.
- [ ] Run a real two-browser student/tutor classroom test and verify real join/leave webhooks.
- [ ] Run the full backend and frontend gates after the focused implementation tests pass.

The implementation uses the official Daily REST contract: `POST /v1/rooms` for room creation and `DELETE /v1/rooms/{room_name}` for cleanup. Development credentials are stored only in Railway. The active development webhook URL is the Railway backend URL with `/api/v1/integrations/daily/webhooks/`; its provider identifier is `a91b9bba-def4-40ae-b764-f8b373c94f3d`.

## Safety rules

- Development branch/worktree only; do not change Railway production or production credentials.
- Do not log or commit Daily secrets.
- Use existing booking state transitions and fulfillment boundaries; do not create a hidden direct-status shortcut.
- Room creation must be idempotent and recoverable.
- Provider failure is not evidence of a tutor no-show.
- Keep Zoom compatibility for historical bookings until an explicit removal decision is made.
- Do not claim full classroom E2E verification until a real Daily room, two authenticated browser clients, and real `participant.joined`/`participant.left` deliveries have been observed.

## Definition of done

- A confirmed development booking provisions exactly one Daily room.
- Student and tutor receive scoped tokens for the same room.
- Cancellation/rescheduling does not leave an active orphan room.
- Daily presence and webhook evidence drive attendance safely and idempotently.
- Automated tests and quality gates pass without hiding Daily-critical failures behind skips.
- Documentation accurately states what is implemented, what is credential-blocked, and how to finish live verification.
