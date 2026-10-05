# Slice N1a - notifications app core (PRP 12.2 partial)

Branch `feature/n1a-notifications-core` (Claude), based on develop `db0a997`. Plan: `docs/PHASE_11_12_EXECUTION_PLAN.md`
§3.2, §4 (N1a row), §5-§7. ERR block ERR-200..ERR-209 (used: ERR-200). Migration `notifications/0001_initial`.
Contract: `docs/NOTIFICATIONS.md` §2, `docs/adr/ADR-0002-notification-delivery.md`, `docs/RUNBOOK_NOTIFICATIONS.md`.
Mutation table: `docs/mutation/N1a.md` (37/37 killed).

## Status
- Done: red tests (`115c043`), implementation (`5079895`), docs, mutation run, full gate.
- Remaining: none in scope. Follow-ups below.
- Next command (from `backend/`): `venv python -m pytest tests/test_notifications_core.py tests/test_notifications_delivery.py tests/test_notifications_alerts.py tests/test_notifications_retention.py tests/test_notifications_templates.py tests/guards/test_guard_notification_kinds.py -q`

## QA round 1 (APPROVE WITH CONDITIONS) - fixed
Red tests first (`efeda5f`: 16 failed, 6 passed, 1 skipped), fixes (`5ff73ba`), survivor-pinning tests (`bda40e8`).
- MAJOR-1: `alert_staff` runs the recipient query and each recipient in its own `transaction.atomic()` savepoint (tests incl.
  Postgres-marked).
- MAJOR-2: `notify()` renders in a savepoint; a renderer error -> minimal in-app row, `failed` / `render_error`, staff alert
  (not for `admin_alert`), log of type + kind + key only. Producer contract documented (NOTIFICATIONS.md §2.2).
- MINOR-1: documented the NTP assumption (ADR-0002), simpler than `Now()` expressions. MINOR-3: `Kind.not_after` hook ->
  `skipped` / `expired`; sweep latency documented (2-4 minutes). MINOR-4: no address -> `skipped` / `no_address` at creation;
  "existing key returns the existing row even if the payload differs" documented. MINOR-5: key producer rules documented.
  MINOR-6: boot warning (`guard.py`) + `check_deploy.py` WARNING line. MINOR-7: admin hides `rendered_html` for everyone and
  subject/text from non-superusers; DSR register note in PRP 14.3.
- Nits: SENDING label no longer hard-codes "15-minute"; migration 0001 regenerated (unmerged, still the single 0001); mutants
  added (table 38-53). No new ERR id was needed (ERR-201..209 unused).
- Gate after QA round: see "Final gate (QA round)" below.

## Red run (first commit, tests only)
```
E   ModuleNotFoundError: No module named 'apps.notifications'
ERROR tests/test_notifications_core.py
ERROR tests/test_notifications_delivery.py
ERROR tests/test_notifications_alerts.py
ERROR tests/test_notifications_retention.py
ERROR tests/test_notifications_templates.py
ERROR tests/guards/test_guard_notification_kinds.py
6 errors in 0.73s
```

## Decisions (deviations from the plan text, and why)
- **Extra columns** `in_app`, `email_first_attempt_at`, `email_next_attempt_at` (additive, defaulted): `in_app=False` marks
  an e-mail-only row (retention 90 days, hidden from the list); the 20 h rule counts from the first attempt; backoff needs a
  due time. UUID primary key (N1b exposes ids; no enumeration).
- **Claim token = `email_claimed_at`** (no separate token column); result writes match `(sending, claimed_at)`.
- **No countdown retries**: the 2-minute sweep is the only retry path (ADR-0002 §8).
- **Preferences**: in-app opt-out is honoured for optional kinds only (row kept with `in_app=False`), mandatory kinds ignore
  both opt-outs; both channels off -> no row. `staff_alert` added to the mandatory set.
- **Password reset / verify mails never go through notify()** (bodies with live tokens must not be persisted); they stay on
  `send_account_email_task`. No e-mail-only kind is registered yet; the machinery is tested with ad-hoc kinds.
- **`ADMIN_ALERT_RECIPIENTS`** = e-mail addresses of active staff accounts (a Notification needs a user FK for the in-app
  item; an address that is not staff is ignored, so a typo cannot leak operational detail); empty = every active admin.
- **Retention**: no 25 h tombstone; every purged row is >= 90 days old, outside Resend's 24 h window (NOTIFICATIONS.md §2.5).
- `alert_staff` never raises into its caller (alerting must not break fulfilment/adjudication); errors logged by type.
- The F0 orphaned Zoom meeting / calendar event log lines are also routed (ZOOM_ATTENDANCE.md listed them for N1a).

## Integrator notes (shared files, all in commented blocks)
- New app `apps.notifications` in `INSTALLED_APPS` (one line, `settings/base.py`) + a settings block after the N1c e-mail
  block (`ADMIN_ALERT_RECIPIENTS`, `NOTIFICATION_*`).
- `config/celery_schedule.py`: 2 beat entries (`sweep-notifications-2min`, `purge-notifications-daily` 03:20 UTC) and 3 routes
  to the `notifications` queue. Beat schedule count on develop goes **11 -> 13** (CLAUDE.md still says 8).
- `.env.example`: `ADMIN_ALERT_RECIPIENTS=` + commented `NOTIFICATION_*` tuning keys.
- No API change: OpenAPI / TS untouched. No frontend change.
- **T1b seam:** T1b's "suspended tutors with future lessons" alert (plan §3.1) should call
  `alert_staff('<code>', key='admin:suspended-with-lessons:{change_id}', payload={...ids})` after adding the code to
  `builtin_kinds.ALERT_TITLES` (and refreshing the `admin_alert` golden only if the example changes; it does not).
- `teachers/vetting.py::notify_status_change` is NOT wired (N2c, after T1b removes the verify shim).

## Follow-ups (not in N1a)
- N1b: API + PATCH preferences (enforce the mandatory set there too); strip `email_last_error` for non-staff.
- N2a-c / N4: real kinds (each with example + golden); migrate the refund / payment-failure / Eskom senders.
- N3: `bounced` state + suppression; decide whether `notify()` skips e-mail for a suppressed address.
- `scripts/check_deploy.py`: warn in production when `ADMIN_ALERT_RECIPIENTS` resolves to nobody.
- Sandbox: verify Resend 409 / 24 h key retention (N1c follow-up) before relying on the 20 h cutoff margin.

## Final gate (QA round, 2026-10-05)
`pytest -q`: **2489 passed, 16 skipped** (N1a files: 138 passed, 4 skipped, all Postgres-marked); `manage.py check` clean;
`makemigrations --check --dry-run`: No changes detected; `ruff check .`: All checks passed. Mutation: 53 mutants, 52 killed,
1 PostgreSQL-only (A:44).

## Final gate (first pass, 2026-10-05)
- `pytest -q`: **2465 passed, 14 skipped** (N1a files: 119 passed, 2 Postgres skips).
- `manage.py check`: no issues. `makemigrations --check --dry-run`: No changes detected. `ruff check .`: All checks passed.
- No real Resend / Zoom / Google call was made (tool gate; Resend path tested with the `resend` fixture and console mode).
