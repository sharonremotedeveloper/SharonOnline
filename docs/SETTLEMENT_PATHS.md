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
| `interrupted_power` | `POST /bookings/<id>/report-outage/` (**that booking's tutor or staff only**; not if the tutor taught >= 20 min) | full gateway refund | nothing, no strike | `outage_refund` |
| `cancelled_by_student` | student cancels > 2 h before start | full gateway refund | nothing | `refund_issued` |
| `student_late_cancelled` | student cancels <= 2 h before start (acknowledged) | pays, no credit back | **80 %** at +24 h (no attendance needed) | `escrow_cleared` |
| `cancelled_by_teacher` | tutor cancels | full gateway refund (+ 1 bonus credit and a strike when < 24 h) | nothing | `refund_issued` (+ `compensation_awarded`) |
| `disputed` -> `cancelled` | admin: *full refund* | full gateway refund (convertible); nothing more if already refunded | nothing | `dispute_resolved` |
| `disputed` -> `completed` | admin: *release tutor* | pays | 80 % | `dispute_resolved` (+ booking/tx marked cleared) |
| `disputed` -> `completed` | admin: *50/50 split* | 1 courtesy credit (platform expense) | 80 % | `dispute_resolved` (+ marked cleared) |

Ledger amounts are always the **captured amount in its own currency** (a PayFast R168.75 payment is settled as R168.75, not as the
tutor's USD list price), so a booking's escrow account returns to exactly zero. The list price is only a fallback when no captured
payment exists.

## Outage reports

* Allowed from **60 min before** the lesson until **30 min after it ends** (`OUTAGE_REPORT_BEFORE_START_SECONDS`, `OUTAGE_REPORT_AFTER_END_SECONDS`). Outside the window: 409. Previously any future booking could be "interrupted" for an instant refund.
* Only for `confirmed` / `in_progress`; one report per booking (state machine + row lock): a second call is a 409 and grants nothing.
* The credit, ledger entry and status change commit together; the free-text `reason` is coerced to a string and cut to 255 characters (a list/dict body no longer crashes the endpoint).

## Bugs found and fixed while doing this

1. **Tutor paid twice after arbitration.** *Release tutor* / *50-50 split* paid the tutor through `record_dispute_settlement_entry`, left `escrow_cleared_at` empty, and the 24 h job then paid the same lesson again (escrow liability driven negative). Now arbitration marks the booking/transaction cleared **and** the job skips anything with a prior settlement entry.
2. **Student no-shows were never paid out** (status missing from the release filter), leaving their escrow in limbo; the outage branch of the attendance check was dead code. Both fixed.
3. **`CreditBundle.objects.get_or_create(user=...)` crashes with `MultipleObjectsReturned`** for any student who has bought two packs - hit by dispute resolution, tutor no-show, memo forfeiture and DEF-501 handling. All six sites now use `payments/services/credits.py::grant_credit()` (latest bundle, F() updates, `remaining <= total`).
4. Arbitration and the teacher no-show refund booked the **USD list price** instead of the captured amount/currency (escrow never reconciled for ZAR payments); fixed as above.
5. The admin escrow view omitted interrupted/no-show lessons and showed arbitrated payouts as "holding".

> **Update (Task 9.6, D-6 decided):** refunds now go back through the payment gateway (see `CANCELLATION_AND_REFUNDS.md`); only the
> lesson's tutor (or staff) can report an outage, and the tutor is not paid for one. The questions below are kept as the history of
> that decision.

## Open questions for Anesu (D-6, now decided - see the update above)

* Should the tutor receive anything when an outage interrupts a lesson part-way (e.g. pro-rata, or full fee if the outage hit the *student*)? Today: nothing, student refunded.
* Should a **student**-reported outage be accepted at all? The platform is built around the tutor's (South African) Eskom schedule; a student claiming "my power went out" refunds them while the tutor goes unpaid. Today any of student/tutor/staff may report. Options: tutor/staff only; or student reports need the tutor's confirmation or an active Eskom stage for the *tutor's* area (data exists from the Eskom sync).
* D-6 still says "gateway refund only": outage, no-show and arbitration refunds currently go to the wallet as credits. The gateway-refund service is Phase 10; revisit these paths then.

## Follow-ups

* Phase 10 refund service should replace wallet-credit refunds where D-6 requires gateway refunds, and handle credit-funded bookings (no gateway transaction, nothing in escrow).
* The release job and memo-SLA job still both act at 24 h (Task 9.9).
