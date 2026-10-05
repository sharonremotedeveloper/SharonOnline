# Runbook - notifications (slice N1a)

Design: `NOTIFICATIONS.md` §2, `adr/ADR-0002-notification-delivery.md`. Django admin: **Notifications -> Notifications**
(read-only; filter by `email_state` and `kind`; search by id, key or provider id). Logs carry ids, codes and attempt
numbers only (`notification.sent / retryable / failed / claim_lost / requeued / enqueue_failed / sweep_enqueue_failed`).

## Before go-live
- Set `ADMIN_ALERT_RECIPIENTS` to the e-mail addresses of active staff accounts (or make sure at least one active admin-role
  user exists). An `[ADMIN ALERT] ... no recipient` log line means nobody received an alert.
- Run a Celery worker that consumes the `notifications` queue and beat (`sweep-notifications-2min`,
  `purge-notifications-daily`).

## Rows stuck in `sending`
A worker died mid-send. Nothing to do: after the 15-minute lease the sweep re-enqueues the row and the retry goes out under
the same idempotency key (Resend returns the first result if the mail had already gone). If many rows stay `sending` for
longer than 20 minutes, the sweep is not running: check beat, the `notifications` worker and the broker.

## Rows stuck in `pending` / `retryable`
- `pending` older than a few minutes: the delivery message was lost (look for `notification.enqueue_failed`); the sweep picks
  it up every 2 minutes once beat and the broker work.
- `retryable` with `email_last_error` `http_429` / `http_5xx` / `timeout`: Resend trouble; the backoff continues up to 8
  attempts (about 2 hours). `http_409`: Resend is still holding the key (in flight or a payload mismatch).

## `failed` rows (a staff alert `notification_failed` was raised)
| `email_last_error` | Meaning | Action |
| :-- | :-- | :-- |
| `http_4xx:...` (e.g. `http_422:validation_error`) | Resend refused the message permanently | fix the cause (address, sender domain, template), then re-send |
| `not_configured` | `RESEND_API_KEY` missing in resend mode | fix configuration, then re-send |
| `no_address` / `invalid_address` | the user has no usable e-mail | correct the user's address, then re-send |
| `attempts_exhausted:<code>` | 8 transient failures | check Resend status; re-send when healthy |
| `render_error` | the kind's template raised at creation; the row has only a title and no e-mail | fix the template (code change), then create a new notification if the message still matters (re-sending cannot help: no body was stored) |
| `stale_needs_review` | the first attempt is 20 h old; Resend may no longer know the key | **check first** (below) |

**Check before re-sending** (`stale_needs_review`, `attempts_exhausted`): if `provider_message_id` is set, or the Resend
dashboard shows a mail with this notification's key/subject to this user, it WAS delivered: leave the row (or mark it
handled in your notes) and do not re-send. Otherwise re-send.

## `skipped` rows (no alert; informational)
`email_last_error` `no_address`: the user had no e-mail address when the notification was created (the in-app item exists);
`expired`: the kind's `not_after` passed before delivery (a reminder after the lesson started); empty: the user's
preference or the kind has no e-mail. Nothing to do.

## How to re-send
Django admin -> Notifications -> select the `failed` rows -> action **"Re-send FAILED e-mails"** (staff with the admin role
or superusers). The rows go back to `pending` with fresh attempts and a fresh 20 h window and are enqueued at once; each
re-queue is logged with the row id and the actor id. Rows in any other state are left unchanged. The e-mail is the bytes
rendered at creation (a template fix does not change an existing row; create a new notification with a new key if the
content itself was wrong).

## Staff alerts
`admin_alert` rows are in-app items for each recipient plus an e-mail. A failed alert e-mail does not raise another alert
(log `[ADMIN ALERT] staff alert e-mail failed`); the in-app item still shows. Alert codes and their sources: `NOTIFICATIONS.md`
§2.7. Money alerts are separate (`GatewayAnomaly`, `SUPPORT_TO_EMAIL`).

## Retention
`purge-notifications-daily` (03:20 UTC) deletes read in-app items after 180 days and finished e-mail-only rows after 90
days, in batches of 1000. Unread items and unfinished rows are never deleted.
