# Slice N1c - unified `send_email` (PRP 12.2 / 12.3 partial)

Branch `feature/n1c-unified-send-email` (Claude). Plan: `docs/PHASE_11_12_EXECUTION_PLAN.md` §3.2, §4 (N1c row), §5.
Contract: `docs/NOTIFICATIONS.md` §1. Mutation table: `docs/mutation/N1c.md` (29/29 + QA round 23/23 killed).

## Status
- Done: red tests; `apps/integrations/services/email.py` (`send_email`, `EmailResult`, `Attachment`, `render_html`);
  settings + production guard + `scripts/check_deploy.py`; booking confirmation (.ics) on `send_email`; the older raising
  `apps/integrations/email.py::send_email` delegates to the service; docs; mutation run; full gate.
- Remaining: none in scope. Hand-off follow-ups below.
- Next command (from `backend/`): `venv python -m pytest tests/test_send_email.py tests/test_account_recovery.py tests/test_settings_guard.py -q`

## Red run (first commit `44804d3`, tests only)
```
tests/test_send_email.py
E   ImportError: cannot import name 'email' from 'apps.integrations.services' (unknown location)
ERROR tests/test_send_email.py
1 error in 1.09s

tests/test_account_recovery.py -k TestMailPlumbing
FAILED tests/test_account_recovery.py::TestMailPlumbing::test_console_mode_never_logs_links_or_addresses
FAILED tests/test_account_recovery.py::TestMailPlumbing::test_provider_failure_raises_instead_of_being_swallowed
FAILED tests/test_account_recovery.py::TestMailPlumbing::test_success_sends_to_the_given_address_only
3 failed, 1 passed, 41 deselected in 8.61s
```

## QA round 1 (APPROVE WITH CONDITIONS) - red run, tests only
```
tests/test_send_email_qa.py
E   ImportError: cannot import name 'EmailPermanentError' from 'apps.integrations.email'
ERROR tests/test_send_email_qa.py
```
Fixed (commit `5604623`): 1 permanent vs transient (`EmailPermanentError`, `.result`, `dont_autoretry_for`, no
`self.retry` on permanent in manual-retry tasks; ERR-182), 2 `retry_after_seconds`, 3 printable-ASCII keys + console-mode
exceptions documented, 4 console `EMAIL_BACKEND` in `local.py` only (docker compose sets
`DJANGO_SETTINGS_MODULE=config.settings.local` for backend, worker and beat, so it still prints there; ERR-184),
5 warning on a 2xx without id + `,`/`;` rejected inside one address, 6 cancellation mail escaped (ERR-183). The edit in
`integrations/tasks.py` is confined to `send_eskom_notification_task` and `send_cancellation_emails` (fulfilment untouched).
SupportInquiry / EskomNotificationAttempt have no `failed` state (adding one is a migration): a permanent failure leaves
the row `retryable` with `last_error` starting `permanent:`; nothing sweeps those rows, so nothing re-sends them.

## Decisions
- Confirmation key `booking-confirmed:{booking_id}:{reschedule_count}:student`: `Booking.reschedule_count` exists and is the
  generation; the `:student` role suffix follows the plan's §6 key so N2b can add the tutor copy without a collision.
- The confirmation now **raises** on anything but `sent`: `EmailPermanentError` for `failed`, `EmailDeliveryError` for
  `in_flight` / `retryable` (before: a non-200 returned `False`, and `dispatch_booking_fulfillment` marked
  `email_completed` anyway). The fulfilment task is untouched (F0 owns it); until F0 consumes `EmailPermanentError`, a
  permanent `failed` is retried by the task's existing 3 retries.
- Console mode uses Django's mail backend (`EMAIL_BACKEND` = console backend in `settings/local.py` only), not a log line: dev
  mail is visible, tests assert on `mail.outbox`, nothing personal reaches the log. The old dev mock logged the address.
- Settings live in `settings/base.py` (a short block after `SUPPORT_TO_EMAIL`), because the code needs them; integrator
  note: that block, the console `EMAIL_BACKEND` + logger entry in `settings/local.py`, and `EMAIL_BACKEND_MODE='console'`
  in the `tests/conftest.py` autouse fixture are the shared-file edits.

## Send-path inventory (for N4)
All of these now reach Resend only through `services/email.py::send_email`, via the raising wrapper
`apps/integrations/email.py::send_email` (raise on anything but `sent`; transient errors retried as before, permanent
`EmailPermanentError` not retried since the QA round). None passes an idempotency key yet. Line numbers as of `5604623`.

| # | Sender (file:line) | Trigger (file:line) | Recipient | Dedup today | N4 / owner |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | `apps/integrations/email.py:77` `send_booking_confirmation_email` (+ `.ics`) **on `send_email` with key** | `apps/integrations/tasks.py:95` in `dispatch_booking_fulfillment` (enqueued by `payments/services/webhook_handler.py:68`, `bookings/services/rescheduling.py:109`) | student | `FulfillmentDispatch.email_completed` + Resend key | N2b (`notify()`, tutor copy) |
| 2 | `apps/users/tasks.py:64` `send_account_email_task` (password reset, verify e-mail) | `apps/users/services.py:10` | user | none (Celery retry) | stays direct (security mail, never stored in-app, plan §3.2); add key |
| 3 | `apps/users/tasks.py:89` `send_support_inquiry_notification` | `apps/users/services.py:23`, `payments/services/grace.py:372` | `SUPPORT_TO_EMAIL` | none | stays as is (plan §3.2) |
| 4 | `apps/payments/tasks.py:35` `send_admin_alert_email_task` | `apps/payments/services/alerts.py:32` (`alert_admin`) | `SUPPORT_TO_EMAIL` | `GatewayAnomaly (code, key)` row | unchanged (plan §6, money alerts) |
| 5 | `apps/payments/tasks.py:54` `send_payment_failure_email_task` | `apps/payments/services/grace.py:373` | student | none | N4 -> `notify()` |
| 6 | `apps/payments/tasks.py:271` `send_refund_processed_email_task` | `apps/payments/services/refunds.py:376` | student | `cache.add` claim at `payments/tasks.py:261` | N4 -> `notify()`, **remove the `cache.add`** |
| 7 | `apps/integrations/tasks.py:223` `send_eskom_notification_task` | `apps/integrations/tasks.py:198` (Eskom sync) | tutor + student | `EskomNotificationAttempt.idempotency_key` | N4 -> `notify()` with the key verbatim |
| 8 | `apps/integrations/tasks.py:301` `send_cancellation_emails` | `apps/bookings/services/cancellation.py:197`, `apps/payments/services/grace.py:308` | other party | none | N2b -> `notify()` (refund-state-aware) |

No other sender exists in `backend/apps` (`send_mail`, `EmailMessage`, `mail_admins`: none). #8 used to put the student's
first name unescaped into the tutor's HTML; fixed in the QA round with `render_html` (ERR-183).

## Follow-ups (not in N1c)
- **N1a:** persist rendered subject/html/text at creation and resend byte-identical under the same key; treat `in_flight`
  as retry-later with an age cap (no resend after ~20 h without review); honour `retry_after_seconds`.
- **F0:** `dispatch_booking_fulfillment` should stop on `EmailPermanentError` (terminal FAILED + alert) instead of retrying.
- **N2b / ICS:** `generate_ics_content` lacks `UID` and `DTSTAMP` (RFC 5545 requires both; a stable `UID` per booking is
  also what lets a rescheduled invite replace the old one); check the `zoom_join_url` scheme (`https://`) before it goes
  into `href` / the invite.
- **N4:** account mails get idempotency keys; support inquiry / Eskom rows get a real `failed` state (migration).
- Sandbox: verify 409 behaviour, 24 h key retention and `attachments[].content_type` against real Resend.

## Final gate (2026-10-04, after QA round 1)
- `pytest -q`: **1953 passed, 6 skipped** (baseline 1840 + 6; +67 in `test_send_email.py`, +46 in `test_send_email_qa.py`).
- `manage.py check`: no issues. `makemigrations --check --dry-run`: No changes detected. `scripts/check_deploy.py`: no issues.
- Mutation: 29/29 + 23/23 killed.
- No real Resend call was made (tool gate).
