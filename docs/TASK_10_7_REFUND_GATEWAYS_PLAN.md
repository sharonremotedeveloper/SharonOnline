# Task 10.7 - Real refund gateways (PayPal capture refunds, PayFast refunds)

**Created:** 2026-10-04 · **Branch:** `feature/10-7-refund-gateways` · **Parent:** `PHASE_10_EXECUTION_PLAN.md` Sprint 10-C · **Status:** plan, awaiting Architect review

Goal: when the platform decides a student is owed money back (cancel, tutor no-show, outage, arbitration), the money actually returns to the
original payment method through the gateway, exactly once, with a ledger that matches the gateway, and a human only has to step in for the
cases a machine must not decide. Built and tested on **mocked HTTP**; the live sandbox pass needs the PayPal credentials.

## 1. What exists (do not rebuild)

`RefundRequest` (unique per booking+reason), the decision journal (DR 2010 / CR 2050), `refunds.mark_processed` (DR 2050 / CR 1010|1020,
`PaymentTransaction -> REFUNDED`, idempotent), `convert_to_wallet`, deferred refunds for grace bookings (`awaiting_clearance` / `void`),
`process_pending_refunds` + beat task every 15 minutes, the `REFUND_GATEWAY_BACKEND` setting (default `ManualSandboxRefundGateway`), the
Django-admin "mark as paid" action, PayPal `get_refund` (slice 10.2F), webhook `PAYMENT.CAPTURE.REFUNDED` handling that completes a refund we
started exactly once (10.2F), `alerts.alert_admin`, `send_email`.

What is wrong today: the backend is a stub; `process_pending_refunds` treats **any** exception as a permanent failure (a PayPal timeout would
dead-end a refund); a `failed` refund is never retried; there is no idempotency key, no cap on the cumulative amount refunded per payment, no
polling of a refund PayPal says is pending, no admin queue, and the HTTP call would be made while holding row locks.

## 2. Design

**Contract** (`services/refund_gateways.py`, already stubbed): `RefundGateway.refund(request) -> RefundResult` and `.lookup(request)`;
`RefundResult.state` in `completed | submitted | rejected | transient | manual`. Adapters never touch the ledger or the database.

**Adapters**
- `PayPalRefundGateway`: `POST /v2/payments/captures/{capture_id}/refund` with header `PayPal-Request-Id: refund-{request.id}` (stable, so a retry
  returns the same refund instead of a second one), body `{amount: {value, currency_code}, invoice_id: <request.id>, note_to_payer}`; the value is
  formatted with `quantize_money` (JPY whole yen). Response `COMPLETED -> completed`, `PENDING -> submitted` (keep the refund id), `FAILED/CANCELLED
  -> rejected`. 4xx business errors (`CAPTURE_FULLY_REFUNDED`, `REFUND_AMOUNT_EXCEEDED`, `REFUND_TIME_LIMIT_EXCEEDED` (180 days),
  `INSTRUMENT_DECLINED`, ...) -> `rejected` with PayPal's name/issue in `detail`; 408/429/5xx/transport errors -> `transient`. `lookup` uses
  `get_refund(reference)`.
- `PayFastRefundGateway`: PayFast's refund API (signed request headers, `pf_payment_id` = the transaction's `gateway_reference`), behind
  `PAYFAST_REFUNDS_ENABLED` (default **false**). Disabled -> `manual` (the request waits in the admin queue). The agent must verify the exact
  API against PayFast's published docs; anything it cannot verify stays disabled and is listed as UNVERIFIED.
- `RoutingRefundGateway` (the new default `REFUND_GATEWAY_BACKEND`): picks the adapter from `payment_transaction.gateway`; `ManualSandboxRefundGateway`
  remains for tests and as the fallback.

**Service** (`services/refunds.py`, `process_pending_refunds` rewritten):
1. *Claim then call outside the lock.* In a short transaction select due rows `FOR UPDATE SKIP LOCKED` (Postgres; plain select on SQLite), stamp
   `attempts += 1`, `last_attempt_at`, `next_attempt_at = now + lease`, commit. Call the gateway with **no DB lock held**. Apply the result in a second
   short transaction that re-reads the row under lock and only acts if it is still in the state it was claimed in.
2. *Results.* `completed -> mark_processed` (existing, posts DR 2050 / CR cash once). `submitted -> mark_submitted` (new status `submitted`, stores
   the provider id, polled by `lookup` on later runs; never re-submitted; not convertible to wallet credit because the money is already on its way).
   `transient -> ` backoff (15 min, 1 h, 4 h, 12 h, 24 h, then 24 h), attempt counted, **never** marks failed; after `REFUND_MAX_ATTEMPTS` (8) it
   becomes `failed` + admin alert. `rejected -> mark_failed` + admin alert + student e-mail only when a person decides. `manual -> ` no attempt used,
   admin alert once after `REFUND_MANUAL_ALERT_AFTER` (3 days).
3. *Guards before any gateway call* (each failing guard marks the refund `failed` with a precise `failure_detail` and alerts, it never calls out):
   a refund may only be sent for a payment transaction in `SUCCESS` (or `PENDING_CAPTURE` is never refunded: that path is deferred already) whose
   `gateway_reference` is a real capture id (not `INIT-`); `refund.currency == tx.currency`; **cumulative cap**: processed + submitted + in-flight
   refund amounts for the transaction plus this one never exceed `tx.amount`; amount > 0; a `REFUNDED` transaction is never refunded again.
4. *Crash safety.* The request id is stable per refund, so "gateway call succeeded, our update did not" is recovered by the next run replaying
   the same id (PayPal keeps request ids ~45 days; a claimed refund older than 30 days with attempts > 0 and no provider id is sent to `failed` for a
   person instead of being replayed blind).
5. *Webhook race.* The existing `PAYMENT.CAPTURE.REFUNDED` handler and the poll both end in `mark_processed`, which is already idempotent; it must
   accept `submitted` as a source state.
6. *Notifications.* On `processed` e-mail the student ("your refund has been sent, it can take 3-5 business days to show"); `failed`/manual-timeout
   alert the admin through `alert_admin` (de-duplicated).

**Operations/admin**: `GET /admin/refunds/?status=` (queue incl. `failed`, `manual`-waiting, `submitted`), `POST /admin/refunds/<id>/retry/`
(failed -> pending_gateway, resets backoff, audited, re-checks the guards), existing Django-admin "mark as paid" kept for manual PayFast. Student
`GET /refunds/` gains the `submitted` status (label "On its way").

**Settings (all env-driven):** `REFUND_GATEWAY_BACKEND`, `REFUND_MAX_ATTEMPTS=8`, `REFUND_ATTEMPT_LEASE_MINUTES=10`, `REFUND_MANUAL_ALERT_AFTER_HOURS=72`,
`PAYFAST_REFUNDS_ENABLED=False`, `PAYPAL_REFUND_NOTE` (text shown to the payer).

**Accounting note:** PayPal keeps its fee on a refund, so 1020 ends lower by the fee: the platform bears it (already expensed to 5030 at capture).
No new account. The refund pays out the exact captured amount from `BookingFunding`; EUR/JPY refunds are returned in the captured currency (the
ledger ZAR value stays at the rate stamped at checkout).

## 3. Slices and ownership

| Slice | Work | Files (owner) |
| :--- | :--- | :--- |
| R-A | PayPal `create_refund` + refund classification in `gateways/paypal.py`; PayFast refund client in `gateways/payfast.py`; the three adapters + router in `services/refund_gateways.py`; adapter tests on mocked HTTP | gateways/*, services/refund_gateways.py, tests/test_refund_gateways.py |
| R-B | `RefundRequest` fields + `submitted` status + migration; `process_pending_refunds` rewrite (claim/backoff/guards/poll/alerts/e-mail); `mark_submitted`; settings; beat task wiring; tests incl. crash-recovery, concurrency, cap, race with webhook | models.py, migrations, services/refunds.py, tasks.py, settings, tests/test_refund_processing.py |
| R-C | admin API (list/retry) + OpenAPI/TS types + admin page + student status label; docs (CANCELLATION_AND_REFUNDS, SETTLEMENT_PATHS, ADR) | admin_api/*, frontend/*, docs/* |
| QA | independent quality review (ECC `django-reviewer`, `python-reviewer`, `security-reviewer`, `code-reviewer` criteria) + mutation checks | read-only |
| ARCH | design review of this plan before code; final review of the integrated diff | read-only |

## 4. Acceptance

A refund decided for a PayPal-funded booking reaches `processed` through one mocked PayPal call; the same refund replayed (job re-run, worker crash,
webhook first, webhook second) posts exactly one 2050 -> cash journal and calls PayPal at most once per request id; a timeout never produces
`failed`; a rejected refund alerts the admin and shows in the queue; the cumulative cap and currency guards refuse an over-refund before any call;
`PAYFAST_REFUNDS_ENABLED=false` leaves PayFast refunds visibly waiting; full backend + frontend gates, the Postgres ledger job and the no-float
guard stay green; docs, ERR log and roadmap updated. The live PayPal sandbox pass is a separate, credential-gated step.
