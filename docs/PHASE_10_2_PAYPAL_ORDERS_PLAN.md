# Task 10.2 / 10.3 / 10.4 - PayPal Orders v2, real buttons, event coverage, pending-payment grace

**Created:** 2026-10-03 · **Parent:** `PHASE_10_EXECUTION_PLAN.md` Sprint 10-B · **Status:** plan agreed in part; items marked PROVISIONAL proceed on the stated default unless Anesu changes them.

## 1. Decisions

| # | Decision | Status |
| :--- | :--- | :--- |
| P-1 | A PayPal capture that comes back **PENDING** confirms the booking and shows the Zoom link anyway (a *grace booking*). The payment is awaited; it never fails the student at checkout. | Decided (Anesu, 2026-10-03) |
| P-2 | Grace exposure is **one lesson at a time**: at most 1 open grace booking per **student account AND per PayPal payer** (payer id, falling back to payer e-mail). A second pending payment from either identity gets no grace. | Decided |
| P-3 | If a pending payment **fails after the lesson was delivered, the platform pays the tutor** (the 80% share is not clawed back). The loss is the platform's. | Decided |
| P-4 | Failure handling is manual-assisted: the **admin is alerted** and the student is contacted by **e-mail plus a support ticket**. There is no chat room yet. | Decided |
| P-5 | Grace applies only to these pending reasons: `RECEIVING_PREFERENCE_MANDATES_MANUAL_ACTION`, `INTERNATIONAL_WITHDRAWAL`, `TRANSACTION_APPROVED_AWAITING_FUNDING` (merchant-side: our PayPal account settings, not the student) and `PENDING_REVIEW`. **No grace** for `ECHECK`, `VERIFICATION_REQUIRED`, `OTHER`, DECLINED or FAILED. | Decided (Anesu, 2026-10-03) |
| P-6 | **Circuit breaker:** if more than **`GRACE_MAX_OPEN` (default 5, a setting, review after the first month)** risk-based grace bookings (`PENDING_REVIEW`) are open at once, new grace is switched off and the admin is alerted; students then wait for completion. Merchant-side reasons (our PayPal account settings) carry no fraud risk, so they do **not** count toward the limit, but each one immediately alerts the admin to fix the account. Worst-case exposure is about `GRACE_MAX_OPEN` lessons (about $9 each). | Decided (Anesu, 2026-10-03; start value 5, review after the first month) |
| P-7 | **No grace on credit-pack purchases** (a pack is 5-20 credits, over the 1-lesson cap). | Decided (Anesu, 2026-10-03) |
| P-8 | The **capture endpoint confirms** the booking through the same verified, locked, idempotent path the webhook uses (the backend re-reads the capture from PayPal; the browser is never trusted). The webhook and the reconcile job remain the fallback. The Phase 10 gate wording "only after the verified webhook" becomes "only after a server-verified capture". | Decided (Anesu, 2026-10-03: option B; `PAYPAL_CAPTURE_CONFIRMS` setting can flip to webhook-only) |
| P-9 | `payment_source.paypal.experience_context.payment_method_preference = IMMEDIATE_PAYMENT_REQUIRED` is **off** at first; turn on only if the sandbox shows eCheck-type pendings. | PROVISIONAL |
| P-10 | Return/cancel URLs come from `FRONTEND_BASE_URL` (config, not code); the production domain is supplied when staging exists. No CSP exists today, so no allowance is needed now; document `paypal.com` / `sandbox.paypal.com` for whoever adds one. | Deferred / documented |

Still needed from Anesu: confirm or change P-5, P-6 (threshold), P-7, P-8; PayPal sandbox credentials and webhook id (`backend/.env`, never chat) and a check of the PayPal Business account's *receiving preferences* (auto-accept, auto-convert foreign currency) - the pending reasons in P-5 depend on them.

## 2. What the grace booking changes (invariants touched)

1. **Transaction state:** `PaymentTransaction` gains `PENDING_CAPTURE` (money not guaranteed). A new `BookingFunding.SourceType.GATEWAY_PENDING` records provenance for a provisionally confirmed booking.
2. **Booking:** `pending_payment -> confirmed` is allowed on a COMPLETED capture, or on a PENDING capture that passes the grace gate (P-2/P-5/P-6/P-7). Everything goes through `transition_booking`; the transition is audited with `reason=grace_pending_capture`.
3. **Ledger:** **nothing is posted while the capture is PENDING** (no cash has arrived). The capture/escrow journal is posted when PayPal reports COMPLETED, at the rate stamped at checkout.
4. **Escrow and payout gate:** the 24 h escrow release, settlement and tutor payout **refuse** while the funding is `GATEWAY_PENDING`. A lesson finished with the payment still pending raises a `SettlementAnomaly` and an admin alert at T+24 h.
5. **Resolution paths:**
   - PENDING -> COMPLETED (webhook `PAYMENT.CAPTURE.COMPLETED` or reconcile): post the journal, mark funding `GATEWAY`, release the gate.
   - PENDING -> DENIED/FAILED **before** the lesson: cancel the booking, release the slot, e-mail the student, open a support ticket, alert the admin.
   - PENDING -> DENIED/FAILED **after** the lesson (P-3): the tutor's share is paid from platform funds. **As built (slice E/G):** the funding becomes `platform_absorbed`; the normal 24 h release job (same attendance rule, dispute exclusion and `settled` guard) then posts DR new account **5040** "platform-absorbed payment failure" / CR 2020 tutor payable for 80 % (event `payment_failure_absorbed`; escrow is not touched and there is no commission, because nothing was collected). The student's `User.booking_blocked_reason` is set (reserve, checkout and credit redemption answer 409 with the reason; staff clear it in Django admin), plus support ticket + admin alert.
6. **Reconciliation:** `reconcile_pending_transactions_task` polls `PENDING_CAPTURE` rows by capture id until they resolve; a pending older than 7 days alerts the admin.
7. **Support ticket:** `SupportInquiry` today is an inbound contact form (no booking or transaction link). Extend it with a `category` (`general`, `payment_failure`), nullable `booking` and `payment_transaction` FKs, and a system-created path that also e-mails the student. Reuse the existing delivery/retry task.

## 3. Task breakdown (about 8-9 days; branch `feature/10-2-paypal-orders` + sub-branches)

| Slice | Work | Size |
| :--- | :--- | :--- |
| A | Gateway client in `gateways/paypal.py`: `create_order`, `capture_order`, `get_order`; `PayPal-Request-Id` idempotency from the transaction reference; per-currency amount formatting (JPY 0 decimals); mocked-HTTP tests (401 retry, 422 declined, `ORDER_ALREADY_CAPTURED`, network error) | S |
| B | Migration: nullable unique `gateway_order_id`, `PENDING_CAPTURE`, `GATEWAY_PENDING`, `SupportInquiry` extension | S |
| C | Init branch creates the order and returns `order_id` (503 when PayPal is unconfigured; reuse a live INITIALIZED order for the same target; bounded orders per booking) | M |
| D | Capture endpoint `POST /payments/paypal/capture/`: owner-only, hold/status re-check, shared `apply_paypal_capture` extracted from the webhook, amount/currency re-verified from PayPal (mutation check on those lines), COMPLETED / PENDING / DECLINED paths, concurrency test (endpoint vs webhook, both orders) | L |
| E | **DONE 2026-10-03** (`feature/10-2e-grace-bookings`). Grace gate: eligibility (reason list, per-account and per-payer caps, packs excluded, circuit breaker), funding type, escrow/payout gate, T+24 h anomaly. Also: completion path (`grace.on_completed`), reconcile polling of PENDING captures, deferred refunds for a cancelled grace booking | L |
| F | 10.4 events: `PAYMENT.CAPTURE.DENIED/REFUNDED/REVERSED`, `CUSTOMER.DISPUTE.*`; PayFast CANCELLED -> FAILED; unknown booking id -> quarantine without a 500; resolution paths from §2.5 | M |
| G | **DONE 2026-10-03** (same branch). Failure runbook code: admin alert (de-duplicated `GatewayAnomaly` + one e-mail to `SUPPORT_TO_EMAIL`), student e-mail, support ticket, `User.booking_blocked_reason` booking block, platform-absorbed tutor payment ledger posting (5040). F still calls `grace.on_failed` / `grace.on_completed` for DENIED/REVERSED/COMPLETED events | M |
| H | PayFast `return_url` / `cancel_url` fields (signature order matters) and settings with production https guard | S |
| I | Frontend (agent): `@paypal/react-paypal-js` buttons (createOrder -> init, onApprove -> capture), pending "payment under review" screen that still shows the lesson and Zoom link, return/cancel pages, wallet pack flow, remove fakes, regenerate API types | L |
| J | Docs, ERR log, roadmap, full suites, CI | S |

## 4. Student experience (target)

| Capture result | What the student sees |
| :--- | :--- |
| COMPLETED | Confirmed. Zoom link and e-mail. |
| PENDING (grace allowed) | Confirmed. Zoom link and e-mail, plus a notice: "PayPal is still verifying this payment. Your lesson is booked. If it cannot be completed we will contact you." |
| PENDING (no grace: cap reached, ECHECK, pack, breaker on) | "Payment under review." Slot held for the normal hold window; auto-resolves; an e-mail follows either way. |
| DECLINED / FAILED | Clear error, retry with another method, slot stays held for the hold window. |

## 5. Risks

- Grace is fraud exposure: `PENDING_REVIEW` is itself a risk signal. Bounded to one lesson per account **and** payer, but a fraudster using several PayPal accounts and several student accounts still gets one lesson each; the circuit breaker and admin alerts are the backstop.
- The grace booking weakens the "confirm only after verified payment" invariant; every path that reads "booking is confirmed" and assumes "payment is cleared" (escrow release, settlement, payout, refunds, cancellation refunds) must be audited. Cancelling a grace booking before clearance must not issue a refund of money not yet received.
- Merchant-side pending reasons depend on the PayPal Business account settings and can only be confirmed in the sandbox.

## 6. As built: slice E + G (2026-10-03)

* **Code:** `payments/services/grace.py` (policy, confirmation, `on_completed`, `on_failed`), `alerts.py` (de-duplicated admin alerts), `notices.py` (plain-wording tickets and e-mails), `payments/tasks.py` (release gate, reconcile of PENDING captures, e-mail tasks), `refunds.py` (`awaiting_clearance` / `void` refunds), `ledger_service.record_absorbed_tutor_payment_entry`, `funding.require_cleared`.
* **Policy details chosen where the plan was silent:** grace needs an identifiable payer (no payer id and no payer e-mail = no grace); a student with a booking block gets no grace; the cap counts only grace bookings that still carry tutor-payment exposure (cancelled, tutor no-show and outage bookings do not count); the breaker allows exactly `GRACE_MAX_OPEN` open risk-based grace bookings and refuses the next one; `PAYPAL_CAPTURE_CONFIRMS=False` also disables grace (grace is a confirmation by the endpoint); an eligibility decision is re-made under a lock (a Postgres advisory lock serialises the caps).
* **DEF-501 guards** are shared (`webhook_handler.slot_unavailable_reason`, `finish_confirmed_booking`): a slot taken by someone else or a lesson already started means no grace (nothing is quarantined because no cash arrived); the normal path handles it when the money clears.
* **Capture response:** new outcome `pending_confirmed` (with `booking_id`) beside `pending`; a replay of the capture request reports the same.
* **Open for Anesu / frontend:** the admin finance ledger items gained `payment_pending` (additive); the UI should show "awaiting PayPal" for those rows. Booking blocks are cleared in Django admin (Users -> Booking block); there is no admin API for it yet.
