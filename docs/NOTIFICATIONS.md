# Notifications

Owner: Claude (lead architect). Design: `PHASE_11_12_EXECUTION_PLAN.md` §3.2 and §6. This file grows slice by slice:
N1c (sending e-mail, §1), N1a (the `notifications` app: `notify()`, delivery state machine, sweep, templates, staff
alerts, retention, §2), then N1b (API + preferences), N2/N3/N4 (events, Resend webhook, wrapped senders).

## 1. Sending e-mail: `send_email` (slice N1c)

`apps/integrations/services/email.py` is the **only** code that talks to Resend (a test fails if `api.resend.com` appears
in any other module under `backend/apps`).

```python
send_email(to, subject, html, text='', *, idempotency_key=None, attachments=(), tags=None, reply_to=None) -> EmailResult
EmailResult(status, provider_message_id='', error_code='', http_status=None, retry_after_seconds=None)  # .ok == (status == 'sent')
Attachment(filename, content: bytes, content_type='application/octet-stream')
render_html(template, **values) -> SafeString                                   # every value HTML-escaped
```

- `to` is one address or a list; several recipients go in a list, never one `,`/`;`-separated string (rejected, which
  also rejects a display name containing a comma). The sender is `DEFAULT_FROM_EMAIL`.
- Provider problems never raise: read `result.status`. The function raises only for programming errors:
  `InvalidEmailError` (CR or LF in `to` / `subject` / `reply_to` / `idempotency_key`, `,`/`;` inside one address, empty
  recipient, key longer than 256 characters or not printable ASCII) and `ImproperlyConfigured` (unknown
  `EMAIL_BACKEND_MODE`). In console mode the Django mail backend's own exceptions propagate unchanged.
- Attachments go to Resend base64-encoded with `filename` and `content_type` (the booking `.ics` uses `text/calendar`).
- `tags` (a dict) becomes Resend's `[{name, value}]` list; keep names and values to ASCII letters, digits, `_` and `-`.

### Error mapping

| Provider outcome | `status` | `error_code` | What the caller does |
| :-- | :-- | :-- | :-- |
| 2xx | `sent` | `''` (`provider_message_id` = Resend id) | store the id |
| 409 | `in_flight` | `http_409[:name]` | same key still being processed, or same key with a different payload: retry later with the **same** payload |
| 429, 5xx | `retryable` | `http_429[:name]`, `http_503[:name]` ... | retry with backoff + jitter; on 429/503 an integer `Retry-After` is in `retry_after_seconds` (capped at 3600; an HTTP-date or junk gives `None`) |
| timeout / connection error / other `requests` error | `retryable` | `timeout`, `connection_error`, `request_error` | retry |
| other 4xx (400, 401, 403, 422 ...) | `failed` | `http_422:validation_error` ... | permanent: do not retry, alert a human |
| `EMAIL_BACKEND_MODE=resend` without `RESEND_API_KEY` | `failed` | `not_configured` | configuration bug |

`[:name]` is Resend's error `name` (e.g. `validation_error`) and is kept only when it is a plain lower-case identifier.
Logs carry the provider id, the status, the HTTP code and the exception **type**; never addresses, subjects, bodies,
provider messages or exception text. A provider id that is not a plain token is dropped; a 2xx without an id is logged as
a warning (still `sent`).

### Idempotency

Pass `idempotency_key` for anything that may be retried; it is sent as Resend's `Idempotency-Key` header. Per Resend's
documentation (not yet verified live): keys are kept **24 hours**; a repeat with the same key and payload returns the
first result; the same key with a **different** payload, or a concurrent request, returns **409**, which we map to
`in_flight`. Consequences for callers (N1a builds this in): render subject/html/text **once**, persist them, and resend
them byte-identical; never resend under a key older than about 20 hours without a human look.

Keys in use: booking confirmation `booking-confirmed:{booking_id}:{reschedule_count}:student`
(`apps/integrations/email.py::booking_confirmation_key`; `reschedule_count` is the generation, so a reschedule gets a new
confirmation). Event keys for later slices are listed in the plan, §6.

### Console mode

`EMAIL_BACKEND_MODE` = `resend` | `console` (settings module; blank = `resend` when `RESEND_API_KEY` is a real key, else
`console`; resolved by `config/settings/guard.py::resolve_email_backend_mode`).

- `console`: the message (with attachments) goes to Django's mail backend. `EMAIL_BACKEND` is the console backend **only
  in `settings/local.py`** (printed by `runserver` / the worker; docker compose uses local settings too); under pytest the
  test backend collects it in `django.core.mail.outbox`. Any other settings module keeps Django's SMTP default, so console
  mode there fails loudly instead of printing reset / verify links. The result is `sent` with a `console:<uuid>` id.
  Idempotency keys are ignored in this mode.
- Tests: the autouse fixture in `tests/conftest.py` pins `console`, so a developer `.env` with a real key never sends
  real mail from a test. Tests that exercise the Resend path set `EMAIL_BACKEND_MODE='resend'` and a fake key, and replace
  `requests.post` in the service module.
- **Production refuses to boot** unless the mode resolves to `resend` (and `RESEND_API_KEY` is real):
  `config/settings/guard.py`, and `scripts/check_deploy.py::email_mode_problems`.

Settings (all in `.env.example`): `RESEND_API_KEY`, `DEFAULT_FROM_EMAIL`, `RESEND_TIMEOUT_SECONDS` (default 10),
`EMAIL_BACKEND_MODE`.

### Building bodies safely

Build HTML with `render_html('<p>Hi {name}</p>', name=user.first_name)`: every value is escaped (`format_html`), the
template itself must be a trusted literal. Plain-text bodies need no escaping, but nothing user-controlled may go into a
subject without passing the CR/LF check (`send_email` enforces it).

### Older raising interface

`apps/integrations/email.py::send_email(to, subject, html, text='') -> None` is a thin wrapper that calls the service and
raises for anything but `sent` (so does `send_booking_confirmation_email`):

| `status` | raises | Celery callers |
| :-- | :-- | :-- |
| `in_flight`, `retryable` | `EmailDeliveryError` (`.result` = the `EmailResult`) | retried as before |
| `failed` | `EmailPermanentError(EmailDeliveryError)` | **not retried**: `autoretry_for` tasks declare `dont_autoretry_for=(EmailPermanentError,)`; manual-retry tasks re-raise without `self.retry`, writing `permanent: ...` into their row's last error where they have one; `log_permanent_failure()` logs task, record id and `error_code` |

The fulfilment task (`dispatch_booking_fulfillment`) does not distinguish them yet (F0 owns it). The existing Celery tasks
(account mails, support inquiry, admin alerts, payment failure, refund processed, Eskom, cancellations) still use the
wrapper; N4 moves them to `notify()`. Inventory with file:line: `docs/slices/N1c.md`.

## 2. The notifications app (slice N1a)

`backend/apps/notifications/`. Protocol and its reasons: `docs/adr/ADR-0002-notification-delivery.md`. Operations:
`docs/RUNBOOK_NOTIFICATIONS.md`. No API yet (N1b); no real events yet (N2a-c, N4).

### 2.1 Model
`Notification` (UUID id): `user`, `kind`, `title` / `body` (in-app text), `payload` (JSON, **ids and short codes only**),
`booking` (nullable), `idempotency_key` (UNIQUE), `in_app` (False = e-mail-only row, hidden from the in-app list),
`created_at` (clock seam), `read_at`; e-mail delivery: `email_state` (`pending | sending | sent | retryable | failed |
skipped | bounced`), `email_attempts`, `email_claimed_at` (claim token), `email_first_attempt_at` (20 h rule),
`email_next_attempt_at` (backoff), `email_sent_at`, `provider_message_id`, `rendered_subject / rendered_html /
rendered_text` (frozen at creation), `email_last_error` (short code only, never a provider body). Indexes:
`(user, read_at, -created_at)` (in-app list) and `(email_state, email_next_attempt_at)` (sweep).
`NotificationPreference(user, email_by_kind, in_app_by_kind)`: `{kind: false}` opts out; a missing kind is on.

### 2.2 `notify()`
```python
from apps.notifications.service import notify, booking_key
notify(user, kind, *, key, payload, booking=None) -> Notification | None
```
- Unknown kind -> `registry.UnknownKind`; a bad key or a payload that is not ids-only -> `InvalidNotification` (programming
  errors). Payload: flat dict, snake_case keys, values `str` (<= 128 chars) / `int` / `bool` / `None` / UUID (stored as
  str), no float, nothing nested; key names containing `review`, `note`, `dossier`, `token`, `password`, `secret`,
  `email`, `text`, `body`, `message`, `comment`, `statement` are refused. Renderers fetch what they need from ids.
- Idempotent on `key`: an existing row is returned and nothing is enqueued, **even if the new payload differs** (the first
  event wins; the persisted e-mail never changes). The insert runs in its own savepoint, so a lost race returns the
  winner's row and never breaks the caller's transaction.
- **Producer contract.** `notify()` is safe to call inside a producer's transaction (a booking, settlement, cancellation):
  it raises only for programming errors (`UnknownKind`, `InvalidNotification`). A renderer exception (the renderer runs in
  its own savepoint) is caught: log `notification.render_failed kind= key= error=<type>` (no message text), a minimal row is
  created (`title` = the kind name, empty body, `in_app` as the preferences say, `email_state=failed`,
  `email_last_error=render_error`) and staff get a `notification_failed` alert (not for `admin_alert` itself). A user with
  no e-mail address gets `email_state=skipped`, `email_last_error=no_address` at creation (the in-app item still shows; no
  alert). `alert_staff` likewise never raises and rolls back to its own savepoint, so a swallowed database error cannot
  leave the producer's PostgreSQL transaction aborted.
- Preferences: a **mandatory** kind (category in `registry.MANDATORY_CATEGORIES`: security, payment, cancellation, refund,
  bank_change, strike, suspension, vetting_outcome, staff_alert) always e-mails and always shows in-app; an optional
  kind follows the user's opt-outs. Both channels off -> no row, returns `None`. E-mail off -> `email_state=skipped`,
  nothing rendered for e-mail. In-app off (optional kinds only) -> the row exists with `in_app=False`.
- The e-mail is rendered once and persisted; delivery is enqueued with `transaction.on_commit` (a rolled-back caller
  leaves nothing; a broker failure is logged with the id and left to the sweep).
- **Never through notify():** password-reset / e-mail-verification mails (their bodies carry live tokens and must not be
  persisted); they stay on `users/tasks.py::send_account_email_task`.

### 2.3 Keys
Plan §6 lists every event key. Booking-bound keys carry the generation token `{booking_id}:{reschedule_count}`
(`booking_generation(booking)`; `booking_key('reminder:24h', booking, 'student')` ->
`reminder:24h:{bid}:{g}:student`), so a reschedule re-arms confirmations and reminders. Strike keys use the strike id,
bank / calendar keys the change-record id, never a timestamp. Keys are 1-200 characters of `A-Z a-z 0-9 : _ . -`
(they are also Resend's `Idempotency-Key`). Staff alerts append `:{recipient_user_id}`.

**Producer rules for keys (N2a-c, N4).** A key must be built from an event id (booking id + generation, strike id, change
record id, lot id); never a timestamp or a random value. A key must **never be re-emitted after retention has deleted its
row** (read in-app items after 180 days, finished e-mail-only rows after 90 days; there are no tombstones, plan note in
§2.5), or the user would get the message again. Recurring events (credit expiring, Eskom shield) need a window token in the
key (`credit-expiring:{lot}:{window}`, the existing Eskom key already has its window).

### 2.4 Delivery state machine
```
pending | retryable(due) --claim (CAS)--> sending --sent--> sent (+ provider id)
                                            |--retryable / in_flight--> retryable (backoff)
                                            |--failed / cap / no or invalid address--> failed (+ staff alert)
                                            |--first attempt >= 20 h ago--> failed 'stale_needs_review' (+ staff alert)
                                            '--lease 15 min expired--> claimable again
```
- Claim = one conditional UPDATE; it counts the attempt and stamps `email_claimed_at` (the token) and, once,
  `email_first_attempt_at`. Every result write is conditional on `(sending, my claimed_at)`; a worker whose lease was
  taken over gets `revoked` and writes nothing.
- The persisted subject/html/text go to `send_email(user.email, ..., idempotency_key=notification.idempotency_key)`; a
  retry is byte-identical, so Resend answers a duplicate with the first result. The address is read at send time.
- Backoff: `NOTIFICATION_RETRY_SECONDS` (60) doubling, +-20 % jitter, capped at `NOTIFICATION_RETRY_MAX_SECONDS` (3600),
  never earlier than the provider's `retry_after_seconds`. `NOTIFICATION_MAX_ATTEMPTS` (8): the 8th transient failure is
  `failed` with `attempts_exhausted:<code>`.
- Staff alert on every `failed` (`alert_staff('notification_failed', ...)`), except for `admin_alert` rows themselves
  (recursion guard: log only, the in-app item still shows).
- No countdown messages: the **sweep** (`sweep_notifications_task`, every 2 min, `notifications` queue, beat lock) enqueues
  `pending` rows older than 2 min (lost message / broker outage), `retryable` rows whose time has come and `sending` rows
  past the lease; at most `NOTIFICATION_SWEEP_LIMIT` (200) per run.
- **Latency:** a delivery message normally goes out at commit. When it is lost, a `pending` row is swept once it is older
  than 2 minutes, at the next 2-minute sweep tick, so a lost message costs about 2 to 4 minutes; retries are picked up at
  the sweep tick after their backoff time (up to 2 more minutes).
- **Expiry (`Kind.not_after`)**: a kind may register `not_after(payload, booking) -> datetime | None`; from that instant
  (`now >= not_after`) delivery marks the row `skipped` with `email_last_error=expired` instead of sending or retrying. N2a's
  reminders use the lesson start. A hook that raises is logged (type only) and the mail is sent normally.
- **Clock:** claim times and lease comparisons use the application clock (`clock.now()`), not the database clock; workers are
  assumed NTP-synchronised (ADR-0002).
- `bounced` is reserved for N3 (Resend webhook + suppression).

### 2.5 Retention (`purge_notifications_task`, daily 03:20 UTC, beat lock, batches of 1000)
Read in-app items 180 days after `read_at`; e-mail-only rows (`in_app=False`) 90 days after creation once finished
(`sent / failed / skipped / bounced`). Unread items stay (erasure / DSR rules are PRP 14.3). The plan's "anonymised key row
for 25 h" is replaced by an equivalent: every deleted row is at least 90 days old, far outside Resend's 24 h key window, so
a tombstone would protect nothing.

**Admin and personal data.** `rendered_text` and `rendered_subject` contain the recipient's personal text and `rendered_html`
the same markup. In Django admin nobody sees `rendered_html`; staff with the admin role do not see subject or text either;
only superusers do. `Notification` (and its payload / rendered fields) must be registered in the Phase 14 data-subject
register (PRP 14.3 export + erasure; see `PRODUCTION_READINESS_PLAN.md` task 14.3).

### 2.6 Kinds and how to add one
`apps/notifications/registry.py`: `Kind(name, category, channels, render, example, not_after=None)`. `render(user, payload, booking)`
returns `Rendered(subject, html, text, title, body)`. Rules:
1. Build HTML with `rendering.render_html` (every value escaped); subjects and titles through `rendering.one_line` (no CR/LF,
   <= 200 characters); times through `rendering.local_time(dt, user)` (recipient's zone; blank/invalid -> UTC with a
   visible "time zone not set" label); names through `rendering.first_name`.
2. Fetch data from the ids in the payload; never read `Booking.student_review`, CRM dossiers or credentials.
3. Register it in a module imported from `NotificationsConfig.ready()` and give it an `example(booking)` payload builder.
4. Add `tests/golden/notifications/<kind>.txt` (guard `tests/guards/test_guard_notification_kinds.py`; render
   `golden_text(kind)` and commit it after reviewing). `tests/test_notifications_templates.py` renders every kind with hostile
   names and private text present in the database and asserts escaping and no leak.

Kinds today: `admin_alert` (category `staff_alert`, mandatory; codes in `builtin_kinds.ALERT_TITLES`) and
`sample_lesson_notice` (category `booking`; exercises the machinery, wired to no event; N2 may delete it).

### 2.7 Staff alerts
`apps.notifications.alerts.alert_staff(alert, *, key, payload)`: `alert` must be a code in `ALERT_TITLES`; one
`admin_alert` per recipient, key `{key}:{user_id}`; never raises into the caller (errors logged by type). Recipients:
`ADMIN_ALERT_RECIPIENTS` = comma-separated e-mail addresses of **active staff accounts** (`is_staff` or role admin, matched
case-insensitively; other addresses ignored with a count-only warning); empty = every active admin-role user. No recipient
-> an `[ADMIN ALERT] ... no recipient` error log. Routed today (the `[ADMIN ALERT]` log lines stay, ids only):

| Site | Alert code | Key |
| :-- | :-- | :-- |
| `bookings/services/fulfillment.py::_fail` terminal | `fulfilment_failed` | `admin:fulfilment-failed:{bid}:{claim_token}` |
| same, cap reached before the lesson | `fulfilment_needs_attention` | `admin:fulfilment-attention:{bid}:{claim_token}` |
| `_delete_orphan` (broker down) | `orphaned_zoom_meeting` | `admin:orphaned-zoom-meeting:{meeting_id}` |
| `_store_event` cleanup (broker down) | `orphaned_calendar_event` | `admin:orphaned-calendar-event:{bid}:{claim_token}` |
| `attendance_probe.py::dispute_without_verdict` | `lesson_disputed_without_verdict` | `admin:disputed-no-verdict:{bid}:{g}` |
| `notifications/delivery.py` failed row | `notification_failed` | `admin:notification-failed:{notification_id}` |

Money alerts stay in `payments/services/alerts.py::alert_admin` (GatewayAnomaly, `SUPPORT_TO_EMAIL`).

### 2.8 Settings (`settings/base.py`, all in `.env.example`)
`ADMIN_ALERT_RECIPIENTS`, `NOTIFICATION_MAX_ATTEMPTS` (8), `NOTIFICATION_LEASE_SECONDS` (900),
`NOTIFICATION_RETRY_SECONDS` (60), `NOTIFICATION_RETRY_MAX_SECONDS` (3600). A blank `ADMIN_ALERT_RECIPIENTS` is a production
boot **warning** (`settings/guard.py`) and a `WARNING` line of `scripts/check_deploy.py` (not a failure: the fallback is every
active admin). Constants `NOTIFICATION_SWEEP_AGE_SECONDS`
(120), `NOTIFICATION_SWEEP_LIMIT` (200). Tasks route to the `notifications` queue (`config/celery_schedule.py`).
