# Notifications

Owner: Claude (lead architect). Design: `PHASE_11_12_EXECUTION_PLAN.md` §3.2 and §6. This file grows slice by slice:
N1c (sending e-mail, below), then N1a (the `notifications` app: `notify()`, delivery state machine, sweep, templates),
N1b (API + preferences), N2/N3/N4 (events, Resend webhook, wrapped senders).

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
