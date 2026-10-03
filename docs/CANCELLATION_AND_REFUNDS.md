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
| Power outage | **only the lesson's tutor (or staff)** can report it, inside the existing window; student gets a full gateway refund; tutor unpaid, no strike. A student with a problem opens a dispute. If the tutor already taught >= 20 min it is a delivered lesson (409 `lesson_delivered`) | `LESSON_DELIVERED_MIN_TEACHER_MINUTES=20` |
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

Nothing captured (legacy rows / credit-funded bookings): there is no gateway money to return, so the student gets a wallet lot
immediately (DR 2010, CR 2040 at the tutor's list price). `RefundRequest` is unique per (booking, reason).

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
* Until Task 10.7 the default `ManualSandboxRefundGateway` leaves refunds pending. In sandbox, pay them in the gateway dashboard and
  use the Django admin action **Refund requests -> Mark as paid in the gateway**.
* Dispute resolution: a booking whose money already left escrow (e.g. a refunded tutor no-show later disputed) can no longer be
  released to the tutor (409 `already_settled`); "full refund" just closes it without paying again.

## Please confirm (Anesu)

1. **Purchased bundles expire in 30 days too** (you said credits expire in 30 days). A 10- or 20-lesson pack that lapses in a month
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
