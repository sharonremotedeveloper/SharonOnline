# Where the money goes (Task 9.7)

A captured payment sits in **escrow** (ledger 2010) until exactly one settlement posts against it. Every settlement writes
`LedgerEntry` rows whose `event_type` is in `payments/services/settlement.py::SETTLEMENT_EVENT_TYPES`; the 24-hour release
job refuses any booking that already has one, so no two paths can pay for the same lesson (`already settled` is read from the
ledger, not from a flag that could be forgotten).

| Outcome (booking status) | Who decides / when | Student | Tutor | Ledger event |
| :--- | :--- | :--- | :--- | :--- |
| `completed`, `completed_pending_memo`, `completed_memo_forfeited` | release job, 24 h after lesson end, needs >= 20 tutor minutes | pays | **80 %** (platform 20 %) | `escrow_cleared` |
| `student_no_show` | adjudicated at T+10m (tutor present); release job 24 h after end, needs a tutor attendance record (not the 20-minute rule) | pays, no credit back | **80 %** (platform 20 %) | `escrow_cleared` |
| `teacher_no_show` | adjudicated at T+10m | full **gateway refund** (convertible to wallet credit) **+ 1 bonus credit** | nothing, 1 strike (3 in 90 days = deactivated) | `refund_issued` + `compensation_awarded` |
| `interrupted_power` | `POST /bookings/<id>/report-outage/` (that booking's tutor or staff; a student only with a provider-confirmed outage in the tutor's area; never if the tutor taught >= 20 min) | full gateway refund | nothing, no strike | `outage_refund` |
| `cancelled_by_student` | student cancels > 2 h before start | full gateway refund | nothing | `refund_issued` |
| `student_late_cancelled` | student cancels <= 2 h before start (acknowledged) | pays, no credit back | **80 %** at +24 h (no attendance needed) | `escrow_cleared` |
| `cancelled_by_teacher` | tutor cancels | full gateway refund (+ 1 bonus credit and a strike when < 24 h) | nothing | `refund_issued` (+ `compensation_awarded`) |
| `disputed` -> `cancelled` | admin: *full refund* | full gateway refund (convertible); nothing more if already refunded | nothing | `dispute_resolved` |
| `disputed` -> `completed` | admin: *release tutor* | pays | 80 % | `dispute_resolved` (+ booking/tx marked cleared) |
| `disputed` -> `completed` | admin: *50/50 split* | 1 courtesy credit (platform expense) | 80 % | `dispute_resolved` (+ marked cleared) |

### Grace bookings (PayPal capture still PENDING, Task 10.2 slice E/G)

A *grace booking* is confirmed while PayPal has not yet guaranteed the money (`BookingFunding.source_type = gateway_pending`).
**Nothing is posted to the ledger while it is pending**, so there is no escrow to release, refund or pay out. Every path that
reads "booking confirmed" must therefore ask "is the money cleared?" first (`funding.py::require_cleared`, `UNCLEARED_SOURCES`).

| Grace outcome | Who decides / when | Student | Tutor | Ledger event |
| :--- | :--- | :--- | :--- | :--- |
| PENDING -> COMPLETED (webhook `PAYMENT.CAPTURE.COMPLETED` or the hourly reconcile job) | `grace.on_completed` | pays; funding becomes `gateway` | normal 80 % path resumes (release job at +24 h) | `payment_captured` at the **checkout-stamped FX** (the booking is not touched and the money is never "surplus") |
| lesson finished (+24 h) but still pending | release job | - | **not paid**; a `SettlementAnomaly` `grace_payment_still_pending` and an admin alert are raised once | none |
| PENDING -> DENIED/FAILED **before** the lesson | `grace.on_failed` | booking `confirmed -> cancelled`, slot freed, **no refund** (nothing was received), ticket + e-mail | nothing (e-mailed that the lesson was cancelled) | none |
| PENDING -> DENIED/FAILED **after** the lesson started/was delivered (P-3) | `grace.on_failed` then the normal release job (same 24 h window, attendance rule and dispute exclusion) | not charged; **booking blocked** (`User.booking_blocked_reason`) until staff clear it; ticket + e-mail | **80 % paid by the platform**: funding becomes `platform_absorbed` | `payment_failure_absorbed`: DR **5040** platform-absorbed payment failure 80 %, CR 2020 tutor payable 80 % (escrow untouched, no commission) |
| grace booking cancelled / tutor no-show **before the payment clears** | `refunds.request_refund` | no refund yet: a `RefundRequest` in `awaiting_clearance` | nothing | none |
| ... then the payment **clears** | `grace.on_completed` -> `refunds.activate_deferred_refunds` | the money is refunded for real (convertible to wallet credit as usual) | nothing | `payment_captured`, then DR 2010 / CR 2050 (`refund_issued` / `outage_refund` / `dispute_resolved`) |
| ... or the payment **fails** | `grace.on_failed` -> `refunds.void_deferred_refunds` | owes nothing; refund request becomes `void` | nothing | none |
| arbitration on a grace booking: *release tutor* / *split* | `ResolveDisputeView` | pending -> 409 `payment_not_cleared`; absorbed + release -> platform pays the tutor; absorbed + split -> 409 `payment_not_collected` | as stated | `dispute_resolved` (absorbed journal for release) |
| PayPal reports COMPLETED after the payment had been written off as failed | `grace.on_completed` | money is real: held in 2030 for a gateway refund (`GatewayAnomaly` `payment_completed_after_failure`) | - | `unallocated_payment` |

Chart of accounts addition: **5040** `5040_expense_absorbed_payment_failure` - tutor share funded by the platform because the student's
pending payment failed after the lesson. It is counted in the telemetry expense totals and nets against platform commission.

Ledger amounts are always the **captured amount in its own currency** (a PayFast R168.75 payment is settled as R168.75, not as the
tutor's USD list price), so a booking's escrow account returns to exactly zero. There is no list-price fallback: a missing immutable
`BookingFunding` snapshot blocks settlement and creates a durable `SettlementAnomaly` for reconciliation.

Capture journals persist the FX rate and named source accepted with the payment. When verified provider data includes a
processing fee, the gateway asset is debited for the net receipt, account 5030 is debited for the fee, and escrow or wallet
liability is credited for the gross capture. Every journal must balance independently in its transaction currency and ZAR.

## Gateway events that touch money after capture (Task 10.4)

Every row is signature-gated, re-reads PayPal (the webhook body is never trusted for amount or status) and is idempotent.
Handlers live in `payments/services/paypal_events.py`; PayFast in `PayFastWebhookView`.

| Gateway event | Matched by | Effect | Ledger |
| :--- | :--- | :--- | :--- |
| PayPal `PAYMENT.CAPTURE.COMPLETED` | capture `custom_id` / capture id | settle through `settle_completed_capture` | capture journal (escrow 2010) |
| `PAYMENT.CAPTURE.DENIED` / `DECLINED` | same | INITIALIZED or PENDING_CAPTURE -> FAILED only when PayPal still reports DECLINED/DENIED/FAILED; a PENDING_CAPTURE tx also calls `grace.on_failed` exactly once; a settled tx is never touched | none |
| `PAYMENT.CAPTURE.PENDING` | same | `record_pending_capture` (reason, payer); no booking change; never revives a FAILED/settled tx | none while the money is not guaranteed |
| `PAYMENT.CAPTURE.REFUNDED`, a refund **we** requested | refund re-read -> capture -> pending `RefundRequest` of the same amount | `refunds.mark_processed` (once) | `2050 -> gateway cash`, tx `REFUNDED` |
| `PAYMENT.CAPTURE.REFUNDED`, **dashboard** refund, full amount, booking escrow unsettled | none of ours | `GatewayAnomaly('external_refund')` + `request_refund(reason='external_refund')` + `mark_processed` | `2010 -> 2050`, then `2050 -> gateway cash` |
| `PAYMENT.CAPTURE.REFUNDED`, partial / foreign-currency / credit-pack / already settled or already refunded | none of ours | `GatewayAnomaly('external_refund')` only, finance corrects it | **none posted automatically** |
| `PAYMENT.CAPTURE.REVERSED`, `CUSTOMER.DISPUTE.CREATED` | capture, or dispute -> `disputed_transactions` -> capture | `GatewayAnomaly('chargeback_opened')` + open `DisputeCase` (an existing case gets a note); the 24 h release skips an open dispute | **none: a human decides** |
| `CUSTOMER.DISPUTE.RESOLVED` | same | `GatewayAnomaly('chargeback_resolved')` with PayPal's outcome + note on the DisputeCase | **none: a human decides** |
| any of the above for a payment we cannot match | - | `GatewayAnomaly('unknown_reference')`, HTTP 200 | none |
| PayFast `payment_status=CANCELLED` / `FAILED` | `m_payment_id` | INITIALIZED -> FAILED after the server postback; settled tx untouched; a later `COMPLETE` for the same form still settles | none |
| PayFast `PENDING` / unknown status | - | acknowledged; unknown statuses logged at WARNING | none |
| Reconciliation (hourly) of an INITIALIZED PayPal order | `paypal.get_order` | captured -> settled once; pending capture -> PENDING_CAPTURE; declined / VOIDED / unpaid past the hold -> FAILED; PayPal unreachable -> left INITIALIZED + anomaly | as COMPLETED |

## Outage reports

* Allowed from **60 min before** the lesson until **30 min after it ends** (`OUTAGE_REPORT_BEFORE_START_SECONDS`, `OUTAGE_REPORT_AFTER_END_SECONDS`). Outside the window: 409. Previously any future booking could be "interrupted" for an instant refund.
* Only for `confirmed` / `in_progress`; one report per booking (state machine + row lock): a second call is a 409 and grants nothing.
* The credit, ledger entry and status change commit together; the free-text `reason` is coerced to a string and cut to 255 characters (a list/dict body no longer crashes the endpoint).

## Bugs found and fixed while doing this

1. **Tutor paid twice after arbitration.** *Release tutor* / *50-50 split* paid the tutor through `record_dispute_settlement_entry`, left `escrow_cleared_at` empty, and the 24 h job then paid the same lesson again (escrow liability driven negative). Now arbitration marks the booking/transaction cleared **and** the job skips anything with a prior settlement entry.
2. **Student no-shows were never paid out** (status missing from the release filter), leaving their escrow in limbo; the outage branch of the attendance check was dead code. Both fixed.
3. **`CreditBundle.objects.get_or_create(user=...)` crashes with `MultipleObjectsReturned`** for any student who has bought two packs - hit by dispute resolution, tutor no-show, memo forfeiture and DEF-501 handling. All six sites now use `payments/services/credits.py::grant_credit()` (latest bundle, F() updates, `remaining <= total`).
4. Arbitration and the teacher no-show refund booked the **USD list price** instead of the captured amount/currency (escrow never reconciled for ZAR payments); all settlement paths now require the immutable booking-funding snapshot.
5. The admin escrow view omitted interrupted/no-show lessons and showed arbitrated payouts as "holding".

> **Update (Task 9.6, D-6 decided):** refunds now go back through the payment gateway (see `CANCELLATION_AND_REFUNDS.md`); only the
> lesson's tutor, staff, or a student with provider-confirmed evidence can report an outage, and the tutor is not paid for one. The questions below are kept as the history of
> that decision.

## Open questions for Anesu (D-6, now decided - see the update above)

* Should the tutor receive anything when an outage interrupts a lesson part-way (e.g. pro-rata, or full fee if the outage hit the *student*)? Today: nothing, student refunded.
* Should a **student**-reported outage be accepted at all? The platform is built around the tutor's (South African) Eskom schedule; a student claiming "my power went out" refunds them while the tutor goes unpaid. Today any of student/tutor/staff may report. Options: tutor/staff only; or student reports need the tutor's confirmation or an active Eskom stage for the *tutor's* area (data exists from the Eskom sync).
* D-6 still says "gateway refund only": outage, no-show and arbitration refunds currently go to the wallet as credits. The gateway-refund service is Phase 10; revisit these paths then.

## Follow-ups

* Explicit cash refunds still require a separately approved gateway-refund service. Operational restitution remains wallet credit and credit-funded bookings settle from their immutable funding snapshot.
* The release job and memo-SLA job still both act at 24 h (Task 9.9).
