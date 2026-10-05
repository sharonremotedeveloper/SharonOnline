# Where the money goes (Task 9.7)

A captured payment sits in **escrow** (ledger 2010) until exactly one settlement posts against it. Every settlement writes
`LedgerEntry` rows whose `event_type` is in `payments/services/settlement.py::SETTLEMENT_EVENT_TYPES`; the 24-hour release
job refuses any booking that already has one, so no two paths can pay for the same lesson (`already settled` is read from the
ledger, not from a flag that could be forgotten).

| Outcome (booking status) | Who decides / when | Student | Tutor | Ledger event |
| :--- | :--- | :--- | :--- | :--- |
| `completed`, `completed_pending_memo`, `completed_memo_forfeited` | release job, 24 h after lesson end, needs >= 20 tutor minutes **and no open staff-host hold** (row "staff-hosted lesson" below) | pays | **80 %** (platform 20 %) | `escrow_cleared` |
| `student_no_show` (also subject to the staff-host hold, see below) | adjudicated at T+10m (tutor present **per attendance records**; a tutor known only from a `started` Zoom probe never produces a student no-show, the lesson-end check decides); release job 24 h after end, needs a tutor attendance record (not the 20-minute rule) | pays, no credit back | **80 %** (platform 20 %) | `escrow_cleared` |
| `teacher_no_show` | adjudicated at T+10m, **only** when the lesson has a Zoom meeting id, Zoom answers `waiting` and the meeting has no past instance (Slice F0; an OAuth or any other Zoom error is never "absent") | full **gateway refund** (convertible to wallet credit) **+ 1 bonus credit** | nothing, 1 strike (3 in 90 days = deactivated) | `refund_issued` + `compensation_awarded` |
| `disputed` (no verdict possible) | T+10m when the lesson has **no Zoom meeting id**, or lesson end when the Zoom probe stayed **unknown** (error/timeout) the whole window; an open `DisputeCase` is created | nothing yet: the admin decides (rows below) | nothing yet, **no strike** | none until arbitration |
| `interrupted_power` | `POST /bookings/<id>/report-outage/` (that booking's tutor or staff; a student only with a provider-confirmed outage in the tutor's area; never if the tutor taught >= 20 min) | full gateway refund | nothing, no strike | `outage_refund` |
| `cancelled_by_student` | student cancels > 2 h before start | full gateway refund | nothing | `refund_issued` |
| `student_late_cancelled` (also subject to the staff-host hold, see below) | student cancels <= 2 h before start (acknowledged) | pays, no credit back | **80 %** at +24 h (no attendance needed) | `escrow_cleared` |
| `cancelled_by_teacher` | tutor cancels | full gateway refund (+ 1 bonus credit and a strike when < 24 h) | nothing | `refund_issued` (+ `compensation_awarded`) |
| `cancelled_by_teacher` (admin cancel, slice T1b) | staff, `POST /admin/teachers/<id>/cancel-future-lessons/`, only for a `suspended` / `rejected` tutor's future lessons; `cancelled_by` = the admin | full gateway refund (credit-funded: credit restored; grace: waits for clearance) + `ADMIN_CANCEL_BONUS_CREDITS` (0) | nothing, **no strike**, not counted as the tutor's own cancel | `refund_issued` (+ `compensation_awarded` only if the bonus setting is > 0) |
| `disputed` (DEF-501 `tutor_not_bookable`, slice T1b) | payment webhook / capture for a hold whose tutor was suspended (or fails the training gate) after reserving | 1 restitution credit, open `DisputeCase` (same as the other DEF-501 reasons) | nothing | `late_payment_quarantine` (ledger 2030) |
| staff-hosted lesson: **HOLD only** (slice Z1, `bookings.HostLinkIssue`) | trigger: platform staff (not the tutor) was issued the Zoom host link through `GET /bookings/<id>/host-link/`, which attendance credits to the **tutor** (the `host_id` rule). The row (staff user id, time) holds the **release job** for `completed*`, `student_no_show` and `student_late_cancelled` (`settlement.attendance_verified_for_release` is False while an unreviewed row exists). **Not blocked:** disputes / arbitration (the `disputed -> ...` rows), refunds and outage refunds, which never go through the release job. Cleared by an admin (`is_staff` and superuser or role admin, never the person the link was issued to unless superuser) in Django admin, "Host link issues" -> action "Mark reviewed", after checking who really attended. Only people who can clear it can obtain a staff host link. Part of the legacy Meetings path: retires with the Video SDK migration (V5). | unchanged (pays on release) | unchanged (80 %, delayed until reviewed) | none (no ledger event; only delays `escrow_cleared`) |
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

## Refund states (Task 10.7)

A gateway refund is one `RefundRequest`. The decision to refund posts `DR 2010 escrow / CR 2050 refunds payable` (see
`CANCELLATION_AND_REFUNDS.md`); everything below is about returning that 2050 liability. `Gateway cash` = 1010 PayFast or 1020 PayPal
(chosen by the payment's gateway, never its currency). Full design: `TASK_10_7_REFUND_GATEWAYS_PLAN.md` section 2b; claim protocol:
`adr/ADR-0001-refund-claim-protocol.md`; operations: `RUNBOOK_REFUNDS.md`.

| Status | Meaning | Moved to it / out of it by | Ledger effect of entering |
| :--- | :--- | :--- | :--- |
| `awaiting_clearance` | Cancelled while the PayPal payment was still pending: nothing owed yet | created by `request_refund`; -> `pending_gateway` (payment cleared) or `void` (payment failed), both system | none (no money has arrived) |
| `pending_gateway` | Owed, not yet sent or being retried | -> in from `awaiting_clearance`, from admin retry; the sweeper claims it (stays `pending_gateway`), student may convert it before the first attempt | `DR 2010 / CR 2050` when activated (already posted for ordinary refunds at decision time) |
| `submitted` | The provider accepted it but has not finished it (PayPal `PENDING`) | sweeper send result; out by the sweeper's poll, the `PAYMENT.CAPTURE.REFUNDED` webhook, or `failed(provider_failed)`; **never** convertible or admin-paid | none |
| `processed` | Money returned to the original payment method | sweeper (send or poll result `completed`), the webhook, or an admin "mark paid" (reference required, audited); from `pending_gateway`, `submitted` or `failed` | `DR 2050 / CR gateway cash`; payment -> `REFUNDED`; student e-mail |
| `converted` | Student took wallet credit instead | the student, only while `attempts == 0`, no live claim, never attempted | `DR 2050 / CR 2040 student wallet` + a 30-day credit lot |
| `failed` | A person must look at it; `failure_kind` says why | sweeper (`rejected`, `already_refunded`, `guard`, `exhausted`, `replay_window`) or poll (`provider_failed`); out by admin retry (back to `pending_gateway`) or admin mark-paid / webhook (-> `processed`) | none (2050 stays owed) |
| `void` | The payment never cleared; nothing was owed | system | none |

Transitions that move no status: a `transient` or `manual` answer only schedules the next attempt (`manual` also restores the attempt
count and does not close the student's conversion window). Every claim result and every admin action writes one immutable
`RefundAttempt` row (retries have the admin as `actor`). Terminal rows (`processed`, `converted`, `void`) ignore any later apply.

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
