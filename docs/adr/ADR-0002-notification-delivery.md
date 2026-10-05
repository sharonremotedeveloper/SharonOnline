# ADR-0002: Notification delivery - claim / idempotency protocol

**Date**: 2026-10-05
**Status**: accepted (slice N1a; plan `PHASE_11_12_EXECUTION_PLAN.md` §3.2 approved by Anesu 2026-10-04)
**Deciders**: Claude (lead architect, implementation), plan reviewers (integrations stream)

## Context

Every user-facing message (booking events, reminders, strikes, refunds) and every staff alert becomes a `Notification` row
with an optional e-mail. The e-mail is sent through Resend by Celery workers that can crash at any point, run several at a
time, and lose messages when the broker is down. Resend deduplicates by `Idempotency-Key` for **24 hours**, and answers
**409** when the same key arrives with a different payload or while the first request is still in flight. We need: no
duplicate e-mails, no lost e-mails, no endless retries, and no event silently suppressed after a reschedule.

## Decision

1. **Durable row first.** `notify()` inserts the row (UNIQUE `idempotency_key`, own savepoint) and renders subject, HTML and
   text **once**, persisting them. Delivery is enqueued on commit. The row is the outbox.
2. **Generation-token keys.** Booking-bound keys include `{booking_id}:{reschedule_count}`; other keys use the id of the
   record that caused the event (strike, change record), never a timestamp. One event = one key = at most one e-mail.
3. **CAS claim with a lease.** One conditional `UPDATE ... WHERE state IN (pending, due retryable) OR (sending AND
   claimed_at <= now - 15 min)` sets `sending`, `claimed_at = now` (the token), counts the attempt and records the first
   attempt time. No row lock is held across the HTTP call. Result writes are conditional on `(sending, claimed_at = mine)`.
4. **Byte-identical resend under the same key.** Every attempt sends the persisted bytes with `Idempotency-Key =
   idempotency_key`. A crash after Resend accepted the mail is therefore harmless: the retry returns the first result.
5. **409 = in flight.** Treated like a transient failure (retry with backoff), never as permanent.
6. **20 h cutoff.** If the first attempt was 20 h or more ago, the row becomes `failed` (`stale_needs_review`) instead of
   being sent: Resend may have forgotten the key, so a resend could duplicate an e-mail that actually went out. A person
   checks (provider id / Resend dashboard) and re-queues it, which resets the window (`requeue_failed`).
7. **Bounded retries.** Backoff 60 s doubling, +-20 % jitter, cap 1 h, provider `Retry-After` as a floor; 8 attempts, then
   `failed`. Every `failed` raises a staff alert, except a failed staff alert (recursion guard).
8. **Sweep instead of countdowns.** A 2-minute beat task re-enqueues due retries, `pending` rows older than 2 minutes
   (lost messages) and expired leases. Countdown messages are not used (they are lost with the broker and interact badly
   with visibility timeouts).

## Consequences

- At-most-once per key inside Resend's window and at-least-once delivery overall; the gap (a mail sent but not recorded,
  then refused after 20 h) ends in a human-visible `failed` row instead of a guess.
- A changed user address between attempts changes the payload: Resend answers 409 until the key expires, then the 20 h rule
  stops it for review. Accepted: rare, and visible.
- Retries can be up to ~2 minutes later than their backoff (sweep granularity). Accepted for notification mail.
- Tested on SQLite; the CAS claim and the concurrent unique insert have Postgres-marked tests
  (`tests/test_notifications_delivery.py`) run in the Postgres CI job.

- **Clock assumption (QA minor 1):** claim times, lease comparisons and due times come from the application clock
  (`apps.common.clock.now()`) on whichever worker runs, not from the database clock. Chosen over `Now()` expressions
  because it is the simpler option and keeps the clock seam testable. It assumes workers are NTP-synchronised: skew of a
  few seconds against a 15-minute lease, a 2-minute sweep and a 20 h cutoff is harmless; skew of minutes is an ops fault.
- **Producer isolation (QA majors):** `notify()` and `alert_staff()` run their risky parts (renderer, recipient lookup, each
  insert) in savepoints and never raise into a producer's transaction (PostgreSQL aborts a transaction on any DB error,
  even a swallowed one, unless it was rolled back to a savepoint).
- **Expiry:** a kind can register `not_after`; past it the row is `skipped` / `expired` (reminders must not be sent or
  retried after the lesson started).

## Alternatives considered

- `select_for_update` around the send: holds a row lock across HTTP; rejected (same reasoning as ADR-0001).
- Re-rendering on each attempt: a template or data change would produce a different payload under the same key (409 loop)
  or a different e-mail; rejected.
- Tombstone rows kept 25 h after retention deletion: every purged row is >= 90 days old, so it protects nothing; replaced by
  plain deletion (`NOTIFICATIONS.md` §2.5).
