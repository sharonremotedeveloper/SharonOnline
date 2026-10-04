# ADR-0001: Refund claim / call / apply protocol

**Date**: 2026-10-04
**Status**: accepted (Architect-approved with changes; provisional values flagged for Anesu)
**Deciders**: Architect review of `TASK_10_7_REFUND_GATEWAYS_PLAN.md`, Claude (implementation), Anesu MUPESA (open: first-attempt delay)

## Context

Refunds must go back through PayPal (decision D-6). The sweeper (`process_pending_refunds`, every 15 minutes) has to send each refund
**at most once** even though: several Celery workers may run the sweep (the Redis beat lock is best-effort); a worker can crash after
PayPal accepted a refund but before we recorded it; PayPal can be down for days; the PayPal webhook and the student's
"convert to wallet" button can race the sweeper; and the code runs on SQLite in CI and Postgres in production. Paying a student twice,
or telling them "paid" when nothing moved, are the two failures that cost real money and trust.

## Decision

A refund is processed in three steps, none of which holds a database lock across the network call:

1. **Claim** - one compare-and-swap `UPDATE` on the `RefundRequest` row (`WHERE id=? AND status=... AND due AND lease expired`)
   stamps a random `claim_token`, a lease (`REFUND_ATTEMPT_LEASE_MINUTES`), counts the attempt and stores the idempotency key
   `gateway_request_id` (`refund-<id>`, `-r<epoch>` after a human retry) on first use. `rowcount == 1` means we own the row. The
   claim is taken just before each call, not in a batch, so a slow call never lets another row's lease lapse.
2. **Call** - the gateway adapter is called with no lock held, passing the stored request id as PayPal's `PayPal-Request-Id`, so a
   replay after a crash returns the original refund instead of creating a second one. Adapters never raise; anything unexpected is
   `transient`.
3. **Apply** - `apply_result(refund_id, token, result, kind)` re-locks (PaymentTransaction then RefundRequest - the webhook handler's
   order, so they cannot deadlock), checks the token still matches (a worker whose lease expired and whose row was claimed again is
   ignored), writes the outcome, the ledger entry and exactly one immutable `RefundAttempt` row in one transaction.

Supporting rules: guards (payment `SUCCESS`, real capture id, single currency, whole minor units, no unresolved external refund,
cumulative cap under the payment's row lock) run before any call and fail the row as `guard`; transient failures never fail a row
until `REFUND_MAX_ATTEMPTS` AND `REFUND_TRANSIENT_WINDOW_HOURS`; a per-gateway breaker stops sending after three consecutive
transient/provider-level answers in one sweep and raises one alert; the student may convert to wallet credit only before the first
attempt (`attempts == 0`, no live claim), which is why the first attempt is delayed by `REFUND_FIRST_ATTEMPT_DELAY_MINUTES`
(60, provisional); an ambiguous failure (`exhausted`, `replay_window`, `already_refunded`) can be retried by an admin only after
confirming in the gateway that nothing was refunded.

## Alternatives Considered

### Alternative 1: `SELECT ... FOR UPDATE SKIP LOCKED` as the claim
- **Pros**: the textbook Postgres job-queue pattern, no token column.
- **Cons**: SQLite (our CI database) ignores it, so the concurrency behaviour would be untestable where the suite runs; the lock only
  lives as long as the transaction, so it either does not cover the network call or must be held across it (below); no fencing for a
  stale worker. It is kept only as a candidate-selection optimisation on Postgres; the CAS is the real guard.

### Alternative 2: hold the row (or payment) lock across the HTTP call
- **Pros**: trivially exclusive.
- **Cons**: a slow PayPal call pins a database connection and a row lock for up to the HTTP timeout; the webhook handler, the student's
  convert button and other refunds on the same payment block behind it; a PayPal outage would stall the whole sweep and risk
  deadlocks with the webhook path. A crash still leaves the outcome unknown, so idempotent replay is needed anyway.

### Alternative 3: a status flag (`sending`) without a token or lease
- **Pros**: simple.
- **Cons**: a crashed worker leaves the row `sending` forever; a late result from a slow worker can overwrite a newer attempt.

### Alternative 4: fail a refund after N attempts regardless of age
- **Pros**: simple, bounded.
- **Cons**: a three-day PayPal outage would fail every queued refund at once and flood the admins; rejected in favour of the dual
  attempts-and-age rule plus the circuit breaker.

## Consequences

### Positive
- Money moves at most once: the CAS makes ownership exclusive, the stored request id makes replay safe, the token fences stale workers.
- Works identically on SQLite (CI) and Postgres; the concurrency tests run in the normal suite.
- Short lock holds; an outage degrades to delayed refunds with one alert, not failed rows.
- Every attempt and admin action is auditable (`RefundAttempt`).

### Negative
- More state on `RefundRequest` (token, lease, request id, epoch, counters) and more states for operators to understand
  (`submitted`, `failure_kind`); documented in `RUNBOOK_REFUNDS.md`.
- A refund is delayed by up to `REFUND_FIRST_ATTEMPT_DELAY_MINUTES` plus the sweep interval before PayPal is asked.

### Risks
- A call that succeeds at PayPal but whose lease expires before we apply it is replayed with the same request id; this relies on
  PayPal honouring `PayPal-Request-Id` for the replay window (30 days, enforced by `REFUND_REPLAY_WINDOW_DAYS`). **Unverified until the
  sandbox run** (mocked HTTP only so far).
- Open follow-ups: the ledger capture side still keys cash accounts 1010/1020 on currency (ERR-092); a single PayPal 404
  `RESOURCE_NOT_FOUND` is treated as provider-level and could trip the per-gateway breaker for one bad row.
