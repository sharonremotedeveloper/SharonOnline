# Cancellation, rescheduling, refunds, strikes and credit expiry (Task 9.6, decision D-6)

Decided by Anesu: student cancel **more than 2 h** before start is free, **2 h or less** forfeits the fee; credits expire after
**30 days**; refunds go back **through the payment gateway**. The remaining rules were recommended by a system-design review of
these docs and the code and adopted as the defaults below. **Every number is a setting** (`config/settings/base.py`), so a
policy change is an environment variable, not a code change. Anesu should still confirm the items under "Please confirm".

## Policy

| Situation | Rule | Setting |
| :--- | :--- | :--- |
| Student cancels, unpaid hold | released, nothing charged | - |
| Student cancels > 2 h before start | full refund of the exact capture, to the original payment method | `STUDENT_FREE_CANCEL_HOURS=2` |
| Student cancels <= 2 h, before start | fee kept; **tutor gets 80 %** at +24 h like a student no-show; student must send `acknowledge_forfeit=true` | same |
| Anyone cancels after the start time | not possible (409 `cancel_window_closed`); outcomes are decided by attendance / dispute | - |
| Student reschedules | once per lesson, only if the lesson starts > 2 h away; new slot is an open slot of the same tutor, 2 h to 14 days out | `RESCHEDULE_MIN_NOTICE_HOURS=2`, `RESCHEDULE_MAX_PER_BOOKING=1`, `RESCHEDULE_MAX_DAYS_AHEAD=14` |
| Tutor wants to move a lesson | cannot; cancels instead | - |
| Tutor cancels >= 24 h ahead | full refund, no bonus, no strike (but the 4th such cancel inside 30 days is 1 strike) | `TUTOR_CANCEL_NO_PENALTY_HOURS=24`, `TUTOR_EARLY_CANCELS_PER_30D=3` |
| Tutor cancels < 24 h ahead | full refund **+ 1 bonus credit** + 1 strike | `TUTOR_CANCEL_BONUS_CREDITS=1` |
| Tutor no-show (T+10) | full refund + 1 bonus credit + 1 strike (refund now goes via the gateway) | - |
| Strikes | each counts 90 days; 3 inside the window deactivate the tutor; only an admin reactivates | `STRIKE_LIMIT=3`, `STRIKE_WINDOW_DAYS=90` |
| Power outage | the lesson's **tutor or staff** can always report it, inside the existing window; a **student only when the provider confirms an active outage in the tutor's area** (409 `outage_unconfirmed` otherwise; their own power or internet problem is a dispute). Student gets a full gateway refund; tutor unpaid, no strike. If the tutor already taught >= 20 min it is a delivered lesson (409 `lesson_delivered`) | `LESSON_DELIVERED_MIN_TEACHER_MINUTES=20` |
| Refund route (all of the above + arbitration "full refund") | gateway refund; while still pending the student may convert it to wallet credit | `REFUND_GATEWAY_BACKEND` |
| Wallet credit | each grant is its own lot that expires **30 days** after it is granted; spent soonest-expiry first; expired lots are written off to breakage revenue | `CREDIT_EXPIRY_DAYS_REFUND/BONUS/BUNDLE=30` |

## Money (ledger)

| Event | Entries |
| :--- | :--- |
| Refund decided (cancel / no-show / outage / arbitration) | DR 2010 escrow, CR **2050 refunds payable** (the booking is now settled; the release job will skip it) |
| Gateway returns the money | DR 2050, CR 1010 PayFast / 1020 PayPal; `PaymentTransaction -> REFUNDED` (`gateway_refund_paid`) |
| Student converts a pending refund | DR 2050, CR 2040 wallet; new 30-day lot, `unit_value` = the refunded amount |
| Late student cancel | nothing now; at +24 h the normal release posts DR 2010, CR 2020 (80 %), CR 4010 (20 %) |
| Bonus credit (tutor cancel / no-show) | DR 5020 compensation expense, CR 2040, in the **captured** currency |
| Reschedule | none: the same booking, payment and escrow move |
| Credit lot expires | DR 2040, CR **4020 breakage revenue** for `remaining x unit_value` (`credit_expired`, not a settlement) |

What is refunded, and in which currency, always comes from the booking's immutable `BookingFunding` record (what it was paid with),
never from the current list price:

* **paid through a gateway** -> `RefundRequest` + ledger 2050 as above;
* **paid with a credit** -> the credit comes back as a new lot (DR 2010, CR 2040), no gateway call;
* **no funding record** (a data fault) -> `MissingFunding`: nothing is refunded, a `SettlementAnomaly` is recorded for finance, and a
  cancel is refused with 409 `funding_unavailable` rather than guessing.

* **paid through PayPal but still PENDING (a grace booking, Task 10.2)** -> **no refund of money not yet received.** Cancelling it (student,
  tutor, tutor no-show, outage, arbitration "full refund") records the obligation as a `RefundRequest` with status `awaiting_clearance`
  and posts **nothing** to the ledger; the cancel preview says "PayPal is still verifying your payment" and shows no refund amount. If the
  payment later **clears**, the capture is posted and the refund becomes real (`pending_gateway`, DR 2010 / CR 2050); if it **fails**, the
  request becomes `void` and nothing is owed. If the payment had already failed (`platform_absorbed` funding or a failed transaction),
  no refund request is created at all. See `SETTLEMENT_PATHS.md`.

`RefundRequest` is unique per (booking, reason). Credits are lots with a wallet history (`CreditWalletEntry`: purchase / redemption /
refund / bonus / expiry), and the per-credit value field is `unit_amount`.

## Booking statuses

New terminal statuses `cancelled_by_student`, `student_late_cancelled`, `cancelled_by_teacher`, reachable **only from `confirmed`**.
They are deliberately *not* `cancelled`: a late payment may re-confirm `cancelled`, which must never resurrect a booking whose money
was refunded or settled. Slot display: only `cancelled_by_student` frees the slot (the tutor earned the late fee for it; a tutor who
cancelled is not available).

## API

| Endpoint | Who | Notes |
| :--- | :--- | :--- |
| `GET /bookings/<id>/cancel-preview/` | the lesson's student or tutor | what would happen now; `can_cancel`, `outcome`, `refund_amount`, `bonus_credits`, `strike`, `free_cancel_until` |
| `POST /bookings/<id>/cancel/` `{reason?, acknowledge_forfeit?}` | student or tutor | 400 `acknowledgement_required`, 409 `not_cancellable` / `cancel_window_closed`; strangers 404, staff 403 |
| `POST /bookings/<id>/reschedule/` `{start_time_utc}` | the student | 400 `invalid_slot`; 409 `not_reschedulable` / `reschedule_limit_reached` / `reschedule_too_late` / `slot_unavailable`; tutors 403 |
| `GET /refunds/`, `POST /refunds/<id>/convert-to-wallet/` | the student | convert is 409 once processed |

Reschedule keeps the booking id; the old Zoom room and calendar event are deleted and fulfilment provisions new ones (best effort,
retried Celery tasks), reminders re-arm. Cancel emails the other party. Frontend client: `lib/bookings.ts` (`getCancelPreview`,
`cancelBooking`, `rescheduleBooking`, `errorCode`) and `lib/refunds.ts`. **The cancel / reschedule screens themselves are part of
the Phase 15 student/tutor screen work**; the contract is ready.

## Operations

* `expire_credits_task` (daily 02:10 UTC) and `process_pending_refunds_task` (every 15 min) on the `financial_escrow` queue.
* **Refund backend (Task 10.7).** `REFUND_GATEWAY_BACKEND` selects the gateway. The code default stays `ManualSandboxRefundGateway`
  (it moves no money: refunds wait for a person); production sets `apps.payments.services.refund_gateways.RoutingRefundGateway`, which
  sends PayPal refunds through the PayPal Payments API and answers `manual` for PayFast (`PAYFAST_REFUNDS_ENABLED` is False until
  `PAYFAST_REFUNDS_UNVERIFIED.md` is cleared) and whenever PayPal credentials are empty. `scripts/check_deploy.py` fails a production
  check while the backend is Manual. A `manual` answer burns no attempt and re-checks every 6 hours; after
  `REFUND_MANUAL_ALERT_AFTER_HOURS` an admin alert fires. Pay such refunds in the gateway console and use the Django admin action
  **Refund requests -> Mark as paid in the gateway** (it goes through `mark_paid_manually` and leaves a `RefundAttempt` audit row).
* **Staff API.** `GET /api/v1/admin/refunds/` (filters `status`, `failure_kind`, `gateway`, `in_flight`, `waiting_manual`; oldest first;
  `buckets` counts for a banner) and `POST /api/v1/admin/refunds/<id>/retry/` `{confirm_not_refunded_in_gateway?}` (admin only,
  throttled `admin_refund_retry`, audited, 409 `not_failed` / `confirmation_required` / `guard_failed`). An admin page is deferred;
  see `RUNBOOK_REFUNDS.md` for what each alert means and what to do.
* **Wallet-conversion rule.** A student may turn a pending gateway refund into wallet credit **only before the gateway has been
  asked**: `attempts == 0`, no live claim, never attempted. Afterwards the money may already be on its way and converting would pay
  the student twice, so the answer is 409 `refund_in_progress`; a `submitted` refund ("On its way") cannot be converted. To keep a
  usable window the first attempt is delayed by `REFUND_FIRST_ATTEMPT_DELAY_MINUTES` (default **60 - PROVISIONAL, Anesu to
  confirm 60 minutes or another value**). Refunds the manual backend is holding stay convertible (they were never attempted). If PayPal
  pays a refund that was already converted or voided, the webhook raises a critical `refund_after_convert` alert and posts nothing.
* **Settings** (all environment-driven; `config/settings/base.py`):

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `REFUND_GATEWAY_BACKEND` | `...refunds.ManualSandboxRefundGateway` | Dotted path of the gateway; production: `...refund_gateways.RoutingRefundGateway` |
| `REFUND_MAX_ATTEMPTS` | 8 | Transient send attempts before a person is asked (and only once the window below has also passed) |
| `REFUND_TRANSIENT_WINDOW_HOURS` | 168 | Retries continue at least this long after the first attempt, so a multi-day provider outage fails no refund |
| `REFUND_ATTEMPT_LEASE_MINUTES` | 10 | How long a worker owns a claimed refund; a crashed worker's row is replayed (same request id) after this |
| `REFUND_MANUAL_ALERT_AFTER_HOURS` | 72 | A refund waiting for a manual payment this long raises `refund_manual_waiting` |
| `REFUND_REPLAY_WINDOW_DAYS` | 30 | A claimed refund with no recorded provider id is never replayed blind after this; it fails `replay_window` for a human |
| `REFUND_SWEEP_LIMIT` | 25 | Refunds claimed per 15-minute sweep |
| `REFUND_SWEEP_BUDGET_SECONDS` | 600 | Wall-clock budget per sweep (beat lock TTL is 800 s) |
| `REFUND_POLL_INTERVAL_MINUTES` | 60 | How often a `submitted` refund is looked up at the provider |
| `REFUND_FIRST_ATTEMPT_DELAY_MINUTES` | 60 | **Provisional.** Student's window to convert to wallet credit before the first gateway call |
| `PAYFAST_REFUNDS_ENABLED` | False | PayFast refunds answer `manual` until this is true (adapter is an unverified stub) |
| `PAYPAL_REFUND_NOTE` | `Refund from Sharon Online` | Note shown to the payer on the PayPal refund |

  Backoff between transient attempts is fixed in code: 15 min, 1 h, 4 h, 12 h, then 24 h (a provider `Retry-After` is honoured).
* Dispute resolution: a booking whose money already left escrow (e.g. a refunded tutor no-show later disputed) can no longer be
  released to the tutor (409 `already_settled`); "full refund" just closes it without paying again.

## Please confirm (Anesu)

1. **Purchased bundles expire in 30 days too** (the pack catalog and redemption came from Codex's batch 2) (you said credits expire in 30 days). A 10- or 20-lesson pack that lapses in a month
   is harsh and may need legal review (D-12, South African consumer-protection rules on prepaid vouchers). Change
   `CREDIT_EXPIRY_DAYS_BUNDLE` before packs go on sale (Task 10.6).
2. **Outage tutor pay is zero** (and a tutor with 10-19 minutes taught gets nothing). The original spec mentioned a 50 % courtesy
   fee for load shedding; that was never implemented. Confirm zero is acceptable given how often load shedding happens.
3. **Refunds route through the gateway everywhere** (your D-6). This replaces the earlier recommendation of wallet credit for
   operational failures; the student can convert, so instant re-booking is still possible.
4. Breakage revenue (4020) on expired credits needs the accountant (D-12).

## Known limits / follow-ups

* The expiry **warning e-mail** (7 days before) is not built; it belongs with the Phase 12 notifications work.
* Credit-funded bookings (Task 10.6) are not modelled yet: when credits can pay for a lesson, a refund must restore the lot instead
  of calling the gateway. `spend_credit()` already spends soonest-expiry first.
* A deactivated tutor's future confirmed lessons are not auto-cancelled; an admin routine is needed.
* `PLATFORM_COMMISSION_RATE` is still the literal 0.80/0.20 in `ledger_service` and the release job.
* Reschedule into a slot that overlaps the lesson's own old time is refused as "taken".
