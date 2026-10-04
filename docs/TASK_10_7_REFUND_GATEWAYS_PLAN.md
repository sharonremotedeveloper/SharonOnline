# Task 10.7 - Real refund gateways (PayPal capture refunds, PayFast refunds)

**Created:** 2026-10-04 · **Branch:** `feature/10-7-refund-gateways` · **Parent:** `PHASE_10_EXECUTION_PLAN.md` Sprint 10-C · **Status:** Architect-approved with changes (section 2b); implementation in progress

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


---

## 2b. Architect-approved design (2026-10-04) - SUPERSEDES section 2 wherever they differ

The Architect review (approve with changes) found: a wallet-conversion race that could pay twice, a webhook that could not finish a `submitted`
refund, a stale-worker overwrite, per-row attempt exhaustion that would mass-fail refunds during a PayPal outage, an untestable SKIP LOCKED claim on
SQLite, and several guard/audit gaps. The design below resolves all 12 required changes. Engineers build exactly these names.

### Decisions recorded for Anesu (provisional, ADR in docs)
- **Wallet conversion window.** A student may convert a pending gateway refund to wallet credit only **before the first gateway call or live claim**
  (`attempts == 0`, no live claim). To keep a usable window, the first gateway attempt is delayed by `REFUND_FIRST_ATTEMPT_DELAY_MINUTES` (default **60**,
  provisional). Anesu to confirm 60 minutes or another value. PayFast-disabled / manual rows stay convertible (they are never attempted).
- **PayFast** ships as a stub that returns `manual` plus a doc listing what is UNVERIFIED; `PAYFAST_REFUNDS_ENABLED` defaults False. Live PayFast refunds are deferred.
- **Admin UI page deferred**: ship the admin API + Django admin only. The student "On its way" label rides with the API change.

### New fields on `RefundRequest` (exact names)
`submitted_at` (DateTime null), `attempts` (PositiveSmallInt default 0), `next_attempt_at` (DateTime null), `last_attempt_at` (DateTime null),
`first_attempt_at` (DateTime null), `claim_token` (Char 32, '' when free), `claimed_until` (DateTime null), `gateway_request_id` (Char 80, '' until the first claim; then
stored, never re-derived), `request_epoch` (PositiveSmallInt default 0), `failure_kind` (Char 24 blank), `last_http_status` (PositiveSmallInt null), `last_error_code`
(Char 64 blank). Index `(status, next_attempt_at)`. `gateway_reference` stays = the provider refund id. New status `SUBMITTED = 'submitted'`.
`failure_kind` values: `rejected | already_refunded | guard | exhausted | replay_window | provider_failed`.

New immutable model `RefundAttempt` (`ImmutableFinancialQuerySet`): refund FK, `seq`, `kind` (`send|poll|admin_retry|admin_mark_paid`), `actor` (FK user, null = system),
`request_id`, `result_state`, `http_status`, `error_code`, `created_at`. One row per claim result and per admin action, written inside the apply transaction.

### State machine (status x event -> next; "token" = the claim token must match)
| From | Event (actor) | To |
| :--- | :--- | :--- |
| awaiting_clearance | activate_deferred (system) | pending_gateway |
| awaiting_clearance | void_deferred (system) | void |
| pending_gateway | claim (sweeper) | pending_gateway (claim_token + claimed_until set, attempts+1) |
| pending_gateway | completed (sweeper w/ token, webhook, admin mark-paid) | processed |
| pending_gateway | submitted (token) | submitted |
| pending_gateway | transient (token) | pending_gateway, `next_attempt_at` = backoff; **never failed** unless attempts >= `REFUND_MAX_ATTEMPTS` AND age since `first_attempt_at` >= `REFUND_TRANSIENT_WINDOW_HOURS` (168) |
| pending_gateway | rejected (token) | failed (`rejected`, or `already_refunded` for CAPTURE_FULLY_REFUNDED) |
| pending_gateway | guard fails (sweeper, before claim) | failed (`guard`) |
| pending_gateway | manual (token) | pending_gateway, `next_attempt_at` +6 h, attempts restored (does not count) |
| pending_gateway | convert (student) | converted - **only if attempts == 0 and no live claim and last_attempt_at is null**, else 409 `refund_in_progress` |
| submitted | poll (sweeper, token) | processed / submitted (next poll) / failed (`provider_failed`) |
| submitted | webhook completed | processed |
| submitted | convert / mark-paid | **not allowed** (poll or webhook finishes it) |
| failed | admin retry (IsPlatformAdmin, audited) | pending_gateway for `guard`, `rejected`, `provider_failed`; for `exhausted`, `replay_window`, `already_refunded` requires `{"confirm_not_refunded_in_gateway": true}` and re-runs the guards; a retry from `rejected` bumps `request_epoch` (new request id `refund-<id>-r<n>`), from an ambiguous failure keeps the id |
| failed | webhook completed with matching ids / admin mark-paid | processed |
| processed, converted, void | any apply/poll | no-op (`'noop'`) |

Replay window: measured from `first_attempt_at`, `REFUND_REPLAY_WINDOW_DAYS=30`; beyond it a claimed refund with no provider id goes to `failed(replay_window)` for a human to verify in PayPal (it is an "unknown who refunded" guard, not a double-pay guard: every refund is the full captured amount, so a blind replay yields CAPTURE_FULLY_REFUNDED).

### Claim / call / apply protocol (portable, race-safe on SQLite and Postgres)
- **Claim = compare-and-swap UPDATE**, one row per loop iteration just before its call: `UPDATE ... SET claim_token=:t, claimed_until=:now+lease, last_attempt_at=:now, first_attempt_at=COALESCE(first_attempt_at,:now), attempts=attempts+1, gateway_request_id=COALESCE(NULLIF(gateway_request_id,''),:rid) WHERE id=:id AND status='pending_gateway' AND (next_attempt_at IS NULL OR next_attempt_at<=:now) AND (claimed_until IS NULL OR claimed_until<=:now)`; `rowcount == 1` wins. SKIP LOCKED is only a candidate-selection optimisation on Postgres. The first attempt for a new refund is not due before `created_at + REFUND_FIRST_ATTEMPT_DELAY_MINUTES`.
- Sweep budget: at most `REFUND_SWEEP_LIMIT` (25) rows and `REFUND_SWEEP_BUDGET_SECONDS` (600) wall-clock per run (beat lock TTL is 800 s); `distributed_task_lock` is best-effort, the CAS is the real guard.
- **Call with no DB lock.** Build a `RefundOrder` DTO from the claimed row.
- **Apply = `apply_result(refund_id, token, result, *, kind)`**, the single entry point; lock order is always PaymentTransaction then RefundRequest (same as `paypal_events.apply_refund`); the token must still match (fencing against a stale worker) else `'noop'`. Writes one `RefundAttempt`. Returns `'processed'|'submitted'|'retry'|'failed'|'manual'|'noop'`.
- **Per-gateway circuit breaker per sweep:** 3 consecutive `transient`/`provider_level` results from one gateway stop sending to it for the rest of the sweep; rows not attempted are untouched and burn no attempt; one provider-level alert `refund_provider_outage` (key = gateway) once per trip, `resolve_alert` on the next success. Config errors (401 after the single token refresh, 403, sandbox/live 404 mismatch) are provider-level, never per-row failure.
- Backoff: 15 min, 1 h, 4 h, 12 h, then 24 h. `lookup` polls of `submitted` refunds every `REFUND_POLL_INTERVAL_MINUTES` (60); alert `refund_submitted_stale` after 14 days.

### Guards (before any gateway call; a failing guard -> `failed(guard)` + alert, never a call)
Payment transaction status must be `SUCCESS` (REFUNDED/FAILED/INITIALIZED/UNALLOCATED/PENDING_CAPTURE all fail); `capture_ref` real (not `INIT-`, matches `^[A-Za-z0-9_-]{5,64}$`); `refund.currency == tx.currency == funding.currency`; `quantize_money(amount, currency) == amount` (JPY must be whole yen: fail, never round); amount > 0; **no unresolved `GatewayAnomaly(reason='external_refund')` on the transaction**; **cumulative cap** computed under a `select_for_update` on the PaymentTransaction: sibling refunds that are `processed`, `submitted`, or `pending_gateway|failed` with `attempts > 0` (money may have moved) plus this one never exceed `tx.amount`. `awaiting_clearance` rows are never claimed (explicit test). `_gateway_cash_account` must key on `tx.gateway` only (currently ZAR currency always picks 1010).

### Contract (see `services/refund_gateways.py`, committed)
`RefundOrder` frozen DTO, `RefundResult(state, reference, detail, code, http_status, retry_after_s, provider_level)`, adapters MUST NOT raise (the router wraps both calls: unexpected exception -> `transient`, logged as `type(exc).__name__` only). `RoutingRefundGateway` (in `refund_gateways.py`, loaded lazily by `import_string`, no import cycle) picks by `order.gateway` and returns `manual` when PayPal credentials are empty or `PAYFAST_REFUNDS_ENABLED` is false, so a dev/CI process never reaches the network by default. `settings/base.py` default stays `ManualSandboxRefundGateway` (tests need it); production selects Routing via env, and `scripts/check_deploy.py` must fail a production check while the backend is Manual. The duplicate `ManualSandboxRefundGateway` in `refunds.py` becomes an alias import so `apps.payments.services.refunds.ManualSandboxRefundGateway` keeps resolving.

### PayPal refund request/response mapping (R-A)
`POST /v2/payments/captures/{capture_id}/refund`, headers `PayPal-Request-Id: <order.request_id>`, body `{amount:{value,currency_code}, invoice_id, note_to_payer}` (value `format(quantize_money(...),'f')`; JPY whole yen; invoice_id UNVERIFIED in sandbox - omit it if PayPal rejects reuse). Response status: `COMPLETED -> completed`, `PENDING -> submitted`, `FAILED|CANCELLED|DENIED -> rejected`, unknown -> `transient` (never completed). HTTP errors: 400/404/422 business -> `rejected` (`CAPTURE_FULLY_REFUNDED` -> code kept so the service files it as `already_refunded`; `REFUND_TIME_LIMIT_EXCEEDED`, `INSTRUMENT_DECLINED`, `REFUND_AMOUNT_EXCEEDED`, `CAPTURE_NOT_COMPLETED` -> `rejected`); 401 after the single refresh, 403 `NOT_AUTHORIZED|PERMISSION_DENIED`, 404 from a sandbox/live mismatch -> `transient` with `provider_level=True`; 408/409/429 (honour Retry-After)/5xx/transport -> `transient`. `lookup` = `get_refund(order.provider_refund_id)`; a PayPal `PENDING` stays `submitted`, `COMPLETED` -> completed, `FAILED|CANCELLED` -> rejected.

### Webhook fix (R-B, `services/paypal_events.py` `apply_refund`)
Match by `gateway_reference` first; found and `SUBMITTED` -> `mark_processed`, else `duplicate`; the "ours" lookup includes `SUBMITTED`; catch `RefundStateError`: a refund that arrives for a `converted` or `void` request records anomaly `refund_after_convert` (CRITICAL admin alert: money moved twice). `mark_processed` accepts `pending_gateway`, `submitted`, `failed`.

### Security / audit / ops
- Admin API: `GET /admin/refunds/?status=&failure_kind=&gateway=&in_flight=&waiting_manual=` (oldest first, bucket counts) and `POST /admin/refunds/<id>/retry/`, both `IsPlatformAdmin`; the serializer omits raw provider bodies; retry is rate-limited and 409 unless the refund is `failed`. Django-admin "mark as paid" goes through `mark_paid_manually(refund_id, *, actor, reference)` and writes a `RefundAttempt`.
- Logging: never log headers, request bodies, URLs with query strings, PayPal tokens, PayFast passphrase/signature/param strings, or exception text; log `refund_id, booking_id, tx_id, gateway, request_id, attempt, state, http_status, error_code, duration_ms`. Capture id: `quote(safe='')` AND the regex above. PayFast API signing differs from the ITN signature (alphabetical, header fields): do not reuse `build_param_string`.
- Alert codes (key = refund id unless noted): `refund_failed_<kind>`, `refund_manual_waiting` (after `REFUND_MANUAL_ALERT_AFTER_HOURS`=72), `refund_submitted_stale`, `refund_provider_outage` (key = gateway), `refund_after_convert` (critical). `resolve_alert` on processed/converted/retry.
- Settings (exact): `REFUND_GATEWAY_BACKEND`, `REFUND_MAX_ATTEMPTS=8`, `REFUND_TRANSIENT_WINDOW_HOURS=168`, `REFUND_ATTEMPT_LEASE_MINUTES=10`, `REFUND_MANUAL_ALERT_AFTER_HOURS=72`, `REFUND_REPLAY_WINDOW_DAYS=30`, `REFUND_SWEEP_LIMIT=25`, `REFUND_SWEEP_BUDGET_SECONDS=600`, `REFUND_POLL_INTERVAL_MINUTES=60`, `REFUND_FIRST_ATTEMPT_DELAY_MINUTES=60`, `PAYFAST_REFUNDS_ENABLED=False`, `PAYPAL_REFUND_NOTE`.
- `process_pending_refunds()` returns `{'sent','completed','submitted','rejected','transient','manual','polled','skipped_breaker'}` (ints). The three legacy tests in `tests/test_refunds_credits_strikes.py` (~194-215: FakeGateway / BrokenGateway / the asserted dict shape) are rewritten deliberately to the new contract, not deleted, and no str-to-result shim is added.

### Function signatures (refunds.py, R-B)
`claim_due_refunds(*, limit, now=None)` (yields `RefundClaim(refund_id, token, kind, order)`), `apply_result(refund_id, token, result, *, kind)`, `mark_submitted(refund_id, provider_ref, *, token)`, `mark_failed(refund_id, detail, *, kind, token=None)` (accepts pending_gateway and submitted), `mark_processed(refund_id, gateway_reference)` (accepts pending_gateway/submitted/failed), `retry_failed(refund_id, *, actor, confirm_not_refunded=False)`, `mark_paid_manually(refund_id, *, actor, reference)`, `convert_to_wallet(refund_id)` (new rule above).

### Slices (revised)
| Slice | Scope | Depends |
| :--- | :--- | :--- |
| R-A | `gateways/paypal.py` `create_refund` + refund classification; `services/refund_gateways.py` adapters (`PayPalRefundGateway`, `PayFastRefundGateway` stub -> manual, `RoutingRefundGateway`) + `docs/PAYFAST_REFUNDS_UNVERIFIED.md`; tests/test_refund_gateways.py | contract (committed) |
| R-B | models + migration (fields, `SUBMITTED`, `RefundAttempt`), `refunds.py` rewrite per this section, `paypal_events.py` fix, `tasks.py`, settings, Django-admin mark-paid via service, alerts, student e-mail on processed, fix `_gateway_cash_account`, rewrite the 3 legacy tests; tests/test_refund_processing.py | contract |
| R-C | admin API list/retry + OpenAPI + generated TS + student "On its way" label; docs (CANCELLATION_AND_REFUNDS, SETTLEMENT_PATHS, ADR, ops runbook); roadmap | R-B |
| QA | independent review + mutation checks | R-A, R-B, R-C |
| ARCH | final diff review | all |

### Open follow-ups (recorded at slice R-C, 2026-10-04)
- [x] **ERR-092 capture side** (fixed by QA H1): `ledger_service.py` capture-side postings (`record_escrow_capture_entry`, unallocated/quarantine entries, credit-pack capture) still choose cash account 1010/1020 on `gateway == PAYFAST or currency == 'ZAR'`; the refund side now follows `tx.gateway` only. A PayPal payment in ZAR (not offered today) would be captured to 1010 and refunded from 1020. Align before PayPal ZAR is enabled.
- [x] **PayPal 404 `RESOURCE_NOT_FOUND` is provider-level** (fixed by QA M1): the adapter treats it as a sandbox/live mismatch (`provider_level=True`), so a single bad row (an unknown capture id) counts towards the per-gateway breaker and could pause refunds for the rest of a sweep. Decide whether a 404 on a specific capture should fail that row (`rejected`) while a 404 on every row trips the breaker.
- [ ] **Sandbox verification** of everything in slices R-A..R-C (request-id replay, `PENDING` refunds, webhook after poll, invoice_id reuse, `lookup`) and a decision on `REFUND_FIRST_ATTEMPT_DELAY_MINUTES` (provisional 60).
- [ ] **Admin page** for the refund queue (API and typed client `getAdminRefunds` / `retryAdminRefund` exist; UI deferred by the Architect).

---

## QA fixes (2026-10-04)

Branch `feature/10-7f-qa-fixes` (from `feature/10-7-refund-gateways`). Each item was written test-first and mutation-checked.

| Item | Change |
| :--- | :--- |
| H1 | One helper `ledger_service.gateway_cash_account(tx)` (gateway only, never currency) for capture, DEF-501, unallocated, credit-pack and refund postings. A PayPal ZAR payment now nets 1020 to zero after its refund (ERR-110). |
| H2 | `config/settings/guard.py` refuses to boot production on the Manual refund backend (unset/blank resolves to it) unless `ALLOW_MANUAL_REFUNDS_IN_PROD` is truthy. `.env.example` documents `REFUND_GATEWAY_BACKEND` (production value `apps.payments.services.refund_gateways.RoutingRefundGateway`) and the override. `scripts/check_deploy.py` stays as a smoke test of the Routing path. Blank `REFUND_GATEWAY_BACKEND` in base settings now means the default. |
| M1 | PayPal 404 RESOURCE_NOT_FOUND / INVALID_RESOURCE_ID on the SEND path is an ordinary per-row transient (`provider_level` False, code kept): attempts and the exhaustion rule apply (a 404-only row ends `failed(exhausted)`, never `replay_window`); the per-gateway breaker still trips on 3 in a row. New per-refund alert `refund_capture_not_found` after 3 straight 404s of the current request id. Lookup path unchanged (provider-level). |
| M2 | `retry_failed` from `rejected` / `provider_failed` needs `confirm_not_refunded` when attempts > 1 or an earlier send/poll row of the same request id was transient/manual. A single definitive answer keeps the no-confirm retry. |
| M3 | `activate_deferred_refunds` stamps `next_attempt_at = now + REFUND_FIRST_ATTEMPT_DELAY_MINUTES`; the student's wallet-conversion window restarts when the money arrives. |
| M4 | Django-admin "Mark as paid" is a two-step action with a validated form (real gateway refund id per row, `^[A-Za-z0-9_-]{5,64}$`, no invented `MANUAL-<pk>`), per-row error messages (no 500), restricted to superusers / `role == admin` plus Django change permission. |
| M5 | `RefundAttempt.kind` gains `webhook`, `convert`, `guard`, `mark_failed` (migration 0021, choices only). One row per guard / replay-window failure, webhook completion (`mark_processed(..., via_webhook=True)`), wallet conversion (actor = the student) and `mark_failed`; no duplicates on replays. |
| M6 | `paypal_events.apply_refund` returns after the CRITICAL `refund_after_convert` alert (no fall-through to `_external_refund`); the unreachable `except RefundStateError` branch is removed. |
| L1 | A `manual` answer writes no RefundAttempt row and does not count against `REFUND_SWEEP_LIMIT`. |
| L2 | The apply-failure log line carries type name and ids only (no text, no traceback). |
| L3 | Refund e-mail dedupe is an atomic `cache.add` before sending, deleted on failure. |
| L4 | `retry_failed` requires an actor. |

Deviations / notes: a fourth new kind `mark_failed` was added (the brief listed three); `mark_failed` and `convert_to_wallet` gained an optional `actor`. `'manual'` stays in the M2 ambiguity query only for rows written before L1.

**UNVERIFIED:** how long PayPal retains a `PayPal-Request-Id` versus `REFUND_REPLAY_WINDOW_DAYS=30` (the plan assumes ~45 days). Confirm in the PayPal sandbox/docs before go-live; if retention is shorter, lower the replay window.

Follow-up (not done here): split `refunds.py` (about 850 lines).


## Final Architect review (2026-10-04) - APPROVE WITH CONDITIONS

All 12 required changes of the design review were verified in code (file:line in the review). No blocking defect. Conditions and their status:

| # | Condition | Status |
| :--- | :--- | :--- |
| 1 | `select_for_update().select_related()` on `PaymentTransaction` (nullable `booking` / `credit_purchase`) is refused by PostgreSQL ("FOR UPDATE cannot be applied to the nullable side of an outer join") and invisible on SQLite | **Fixed**: the 6 sites in `views.py`, `grace.py`, `paypal_capture.py`, `paypal_events.py` now use `select_for_update(of=('self',))`; a source-scan test forbids the old pattern. **Verify on the Postgres CI job.** Some sites predate this task |
| 2 | `invoice_id` reuse after an epoch-bumped retry might be rejected by PayPal | **Mitigated**: the invoice id is suffixed `-r<epoch>` after a bump; real behaviour UNVERIFIED until the sandbox |
| 3 | Sandbox pass for PENDING refunds, webhook after poll, lookup; confirm `REFUND_FIRST_ATTEMPT_DELAY_MINUTES=60` | Open (needs PayPal sandbox credentials and Anesu) |
| 4 | Tests must never reach a gateway through a developer `.env` | **Fixed**: `tests/conftest.py` pins the Manual refund backend; a test asserts it |
| 5 | Production on Routing with blank PayPal credentials answers `manual` silently | **Fixed (warning)**: the boot guard logs a warning; first alert otherwise comes after 72 h |
| 6 | Runbook/ADR/plan drift | **Fixed**: `refund_capture_not_found` documented, outage and goodwill wording corrected, ERR-092 and the 404 item closed |
| 7 | `refund_submitted_stale` never fired when polls only fail transiently | **Fixed** (shared helper, tests incl. the young-refund negative case) |
| 8 | Payment marked REFUNDED on any completed refund, not only a full one | Follow-up (safe today: every refund is the full captured amount) |
| 9 | Student UI learns that convert is no longer valid only from a 409; split `refunds.py` | Follow-up |

UNVERIFIED because only mocked HTTP and SQLite were available: real PayPal behaviour (Request-Id replay and retention, PENDING refund lifecycle, error names, Retry-After, webhook ordering), real Postgres behaviour (row locks, concurrent claims, FOR UPDATE with joins, migrations 0020-0021 SQL), multi-worker concurrency, PayFast refunds (nothing is called), email delivery, Celery beat.
