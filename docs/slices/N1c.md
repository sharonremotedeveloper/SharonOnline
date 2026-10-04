# Slice N1c - unified `send_email` (PRP 12.2 / 12.3 partial)

Branch `feature/n1c-unified-send-email` (Claude). Plan: `docs/PHASE_11_12_EXECUTION_PLAN.md` §3.2, §4 (N1c row), §5.
Contract: `docs/NOTIFICATIONS.md` §1. Mutation table: `docs/mutation/N1c.md` (29/29 killed).

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

## Decisions
- Confirmation key `booking-confirmed:{booking_id}:{reschedule_count}:student`: `Booking.reschedule_count` exists and is the
  generation; the `:student` role suffix follows the plan's §6 key so N2b can add the tutor copy without a collision.
- The confirmation now **raises** `EmailDeliveryError` on anything but `sent` (before: a non-200 returned `False`, and
  `dispatch_booking_fulfillment` marked `email_completed` anyway). `integrations/tasks.py` is untouched (F0 owns it); a
  permanent `failed` is retried by the task's existing 3 retries, then F0's terminal-FAILED handling applies.
- Console mode uses Django's mail backend (`EMAIL_BACKEND` = console backend in `settings/base.py`), not a log line: dev
  mail is visible, tests assert on `mail.outbox`, nothing personal reaches the log. The old dev mock logged the address.
- Settings live in `settings/base.py` (a 9-line block after `SUPPORT_TO_EMAIL`), because the code needs them; integrator
  note: that block plus `EMAIL_BACKEND_MODE='console'` in the `tests/conftest.py` autouse fixture are the shared-file edits.

## Send-path inventory (for N4)
All of these now reach Resend only through `services/email.py::send_email`, via the raising wrapper
`apps/integrations/email.py::send_email` (behaviour unchanged: raise on anything but `sent`, the task retries). None
passes an idempotency key yet.

| # | Sender (file:line) | Trigger (file:line) | Recipient | Dedup today | N4 / owner |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | `apps/integrations/email.py:77` `send_booking_confirmation_email` (+ `.ics`) **on `send_email` with key** | `apps/integrations/tasks.py:95` in `dispatch_booking_fulfillment` (enqueued by `payments/services/webhook_handler.py:68`, `bookings/services/rescheduling.py:109`) | student | `FulfillmentDispatch.email_completed` + Resend key | N2b (`notify()`, tutor copy) |
| 2 | `apps/users/tasks.py:62` `send_account_email_task` (password reset, verify e-mail) | `apps/users/services.py:10` | user | none (Celery retry) | stays direct (security mail, never stored in-app, plan §3.2); add key |
| 3 | `apps/users/tasks.py:84` `send_support_inquiry_notification` | `apps/users/services.py:23`, `payments/services/grace.py:372` | `SUPPORT_TO_EMAIL` | none | stays as is (plan §3.2) |
| 4 | `apps/payments/tasks.py:33` `send_admin_alert_email_task` | `apps/payments/services/alerts.py:32` (`alert_admin`) | `SUPPORT_TO_EMAIL` | `GatewayAnomaly (code, key)` row | unchanged (plan §6, money alerts) |
| 5 | `apps/payments/tasks.py:47` `send_payment_failure_email_task` | `apps/payments/services/grace.py:373` | student | none | N4 -> `notify()` |
| 6 | `apps/payments/tasks.py:260` `send_refund_processed_email_task` | `apps/payments/services/refunds.py:376` | student | `cache.add` claim at `payments/tasks.py:250` | N4 -> `notify()`, **remove the `cache.add`** |
| 7 | `apps/integrations/tasks.py:223` `send_eskom_notification_task` | `apps/integrations/tasks.py:198` (Eskom sync) | tutor + student | `EskomNotificationAttempt.idempotency_key` | N4 -> `notify()` with the key verbatim |
| 8 | `apps/integrations/tasks.py:296` `send_cancellation_emails` | `apps/bookings/services/cancellation.py:197`, `apps/payments/services/grace.py:308` | other party | none | N2b -> `notify()` (refund-state-aware) |

No other sender exists in `backend/apps` (`send_mail`, `EmailMessage`, `mail_admins`: none). Note on #8: the body is
`f"<p>{line}</p>"` with an unescaped student first name (`integrations/tasks.py:289-290`), an HTML-injection gap in the
tutor's mail; fixed when N2b moves it to escaped templates (or earlier, see follow-ups).

## Final gate (2026-10-04)
- `pytest -q`: **1907 passed, 6 skipped** (was 1840 + 6 skipped; +67 tests in `test_send_email.py`).
- `manage.py check`: no issues. `makemigrations --check --dry-run`: No changes detected. `scripts/check_deploy.py`: no issues.
- No real Resend call was made (tool gate).
