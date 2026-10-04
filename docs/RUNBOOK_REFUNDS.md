# Refund operations runbook (Task 10.7)

Audience: whoever is on call for payments. Design: `TASK_10_7_REFUND_GATEWAYS_PLAN.md` 2b; protocol: `adr/ADR-0001-refund-claim-protocol.md`;
state table: `SETTLEMENT_PATHS.md`. Alerts arrive as admin e-mails and as open `GatewayAnomaly` rows (Django admin) with the code below
as `reason`. Provisional/unverified: all of this has run only against mocked HTTP; verify in the PayPal sandbox before trusting it.

## Where to look
- Queue: `GET /api/v1/admin/refunds/?status=failed` (an admin page is deferred; use the API or Django admin **Refund requests**).
  `buckets` gives counts per status / failure kind, `in_flight` (a worker holds a live lease) and `waiting_manual`.
- Each row shows the last 5 `RefundAttempt` entries (kind, result, HTTP status, error code, who). Provider response bodies are never stored.
- Never edit refund rows or ledger entries by hand. Use retry or mark-paid below; ledger rows are immutable.

## Actions
- **Retry**: `POST /api/v1/admin/refunds/<id>/retry/` `{}` for `rejected`, `provider_failed`, `guard`. For `exhausted`, `replay_window`,
  `already_refunded` first check PayPal (below), then send `{"confirm_not_refunded_in_gateway": true}`. 409 `not_failed` = it is not failed
  (a second click is harmless); 409 `confirmation_required` = you must check and confirm; 409 `guard_failed` = a safety check still
  refuses (the message says which) - fix the cause first. A retry after `rejected` / `provider_failed` uses a NEW request id; after an
  ambiguous failure it keeps the old id so a replay cannot double-refund.
- **Mark paid manually**: Django admin -> Refund requests -> select -> **Mark as paid in the gateway**, giving the PayPal refund id. Use only
  after you have seen the money leave in the gateway console. It posts `DR 2050 / CR gateway cash`, sets the payment to `REFUNDED`,
  e-mails the student and writes an audit row with your name. Not allowed for `submitted` refunds (wait for the poll or webhook).
- **Verify in the PayPal dashboard**: Activity -> find the payment by the capture id (the booking's payment `gateway_reference`) -> look for a
  refund of the full amount. If present: copy its refund id and mark paid manually. If absent: retry. If PayPal shows `Pending`: leave it.

## Alert codes
| Code (key) | Meaning | What to do |
| :--- | :--- | :--- |
| `refund_failed_rejected` (refund id) | PayPal refused it (declined instrument, time limit, amount over the remaining, capture not completed) | Read `last_error_code`. If the time limit passed or the instrument is closed, pay the student another way, then mark paid manually with your reference, or convert the amount to a goodwill credit via finance. If the cause is fixed, retry |
| `refund_failed_already_refunded` | PayPal says the capture is already fully refunded | Look in PayPal: if the refund went to this student, mark paid manually with its id (do NOT retry). If it was a different refund, find out why (dashboard refund?) |
| `refund_failed_guard` | A pre-flight safety check refused it (payment not `SUCCESS`, no real capture id, currency mismatch, non-whole JPY amount, unresolved external refund anomaly, cumulative cap) | The alert text names the check. Resolve the anomaly or data problem, then retry |
| `refund_failed_exhausted` | Transient errors continued for `REFUND_MAX_ATTEMPTS` attempts over `REFUND_TRANSIENT_WINDOW_HOURS` (default 8 attempts, 7 days) | Check PayPal for a refund that may have gone through; if none, retry with confirmation |
| `refund_failed_replay_window` | First attempt more than 30 days ago and no provider id was recorded: we cannot tell whether PayPal refunded | Check PayPal as above; mark paid or retry with confirmation |
| `refund_failed_provider_failed` | PayPal accepted it, then failed it later | Retry (new request id); check the capture is still refundable |
| `refund_manual_waiting` | A refund sat `pending_gateway` for 72 h because the backend answers `manual` (credentials missing, PayFast, or Manual backend in production) | Fix the configuration (PayPal credentials, `REFUND_GATEWAY_BACKEND`) - the next sweep sends it - or pay it in the console and mark paid manually |
| `refund_submitted_stale` | A `submitted` refund is still unfinished 14 days after PayPal accepted it | Open it in PayPal; if completed, the webhook was missed: mark paid is blocked for `submitted`, so ask engineering to run the poll / replay the webhook; if failed, the poll will move it to `failed(provider_failed)` |
| `refund_provider_outage` (key = gateway) | Three refund calls in a row to that gateway failed transiently or with a config error (401/403/sandbox-live mismatch) in one sweep | Check the provider status page and credentials. Nothing is lost: affected rows stay `pending_gateway` with backoff and burn no attempts. The alert resolves itself on the next successful call |
| `refund_after_convert` (refund id, **critical**) | PayPal paid a refund that was already converted to wallet credit (or voided): the student may have been paid twice | Finance: reverse the wallet credit (reversing ledger entry) or recover the money. Nothing is posted automatically |

## What a three-day PayPal outage looks like
Day 1: the first sweep trips the breaker after three failures, raises ONE `refund_provider_outage`, and skips the rest of PayPal's rows for that
run (`skipped_breaker` in the sweep counters). Each later sweep tries one row at a time until three more fail. Rows back off 15 min, 1 h,
4 h, 12 h, then daily; provider-level answers (outage, 401/403) never count towards `exhausted`. Days 2-3: refunds keep their
`pending_gateway` status, students still see "Waiting to be sent" (they can no longer convert once a first attempt was made). When PayPal
returns, the next successful call resolves the alert and rows drain at `REFUND_SWEEP_LIMIT` per 15 minutes (25 rows -> 100 per hour). No
admin action is needed unless a row ends up `failed`. If the outage lasts past 7 days, rows individually fail as `exhausted`: check each in
PayPal and retry with confirmation.

## Quick triage order
1. `refund_after_convert` (money moved twice) - immediately.
2. `refund_provider_outage` - check credentials and status page.
3. `failed` rows by oldest first; `waiting_manual`; `submitted` older than a week.
