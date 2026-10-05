# Mutation table - slice T1b (bookable predicate, review actions, admin cancel, lock order)

Run with `backend/scripts/mutate.py` on a clean tree (2026-10-05, branch `feature/t1b-bookable-review`), driven by a scratchpad
script that passes arguments as an argv list. Every run reported `restored: ok (byte-identical)`. Line numbers refer to commit
`a3d6d90` (the survivors r2, r5, r7, r8 were fixed in `d9250d7`; r7/r8 by removing the redundant condition, r2/r5 by new tests).

Test files: **B** `tests/test_t1b_bookable.py`, **R** `tests/test_t1b_review_actions.py`, **C** `tests/test_t1b_admin_cancel.py`,
**M** `tests/test_tutor_status_machine.py`.

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| b1 | teachers/models.py:55 | `bookable()` without `is_active` | B TestPredicate | KILLED |
| b2 | teachers/models.py:56 | gate check always off | B `test_the_gate_needs_training_when_on` | KILLED |
| b3 | teachers/models.py:57 | `training_completed_at__isnull=True` | B | KILLED |
| b4 | teachers/models.py:198 | `status ==` approved (instance) | B | KILLED |
| b5 | teachers/models.py:200 | `is None` | B | KILLED |
| b6 | teachers/models.py:200 | gate polarity inverted | B | KILLED |
| b7 | teachers/models.py:67 | `end_time_utc__lte` (operational) | B TestOperationalTutors | KILLED |
| b8 | teachers/models.py:69 | approved branch removed | B | KILLED |
| c1-c2 | teachers/views.py:17,65 | list / detail use `.all()` | B TestPublicSurfaces | KILLED |
| c3 | bookings/views.py:55 | slots view not bookable | B | KILLED |
| c4 | reservation.py:41 | reserve not bookable | B TestNewBookingPaths | KILLED |
| c5 | rescheduling.py:62 | reschedule guard off | B | KILLED |
| c6 | payments/views.py:215 | checkout guard off | B | KILLED |
| c7 | credits.py:193 | credit redemption guard off | B | KILLED |
| c8 | webhook_handler.py:101 | late-payment guard off | B TestLatePaymentForAnUnbookableTutor | KILLED |
| c9-c10 | integrations/tasks.py:72,186 | Eskom / GCal use `.all()` | B TestOperationalTutors | KILLED |
| c11 | admin_api/views.py:389 | payout preview filtered by status | B TestPayoutPreview | KILLED |
| c12-c13 | admin_api/views.py:115 | `applied` dropped / `rejected` listed | R TestPendingQueue | KILLED |
| r1 | vetting.py:49 | `suspended -> rejected` open to SYSTEM | R, M | KILLED |
| r2 | vetting.py:95 | `is_staff_user` skips the staff check | R TestServiceAuthorization | SURVIVED, then KILLED |
| r3 | review.py:72 | idempotency check inverted | R repeat-action tests | KILLED |
| r4 | review.py:76 | any start status allowed | R 409 matrix | KILLED |
| r5 | review.py:90 | service staff check removed | R TestServiceAuthorization | SURVIVED, then KILLED |
| r6 | review.py:92 | reason never required | R | KILLED |
| r7 | review.py:101 | `if result.changed` always true | redundant condition removed | SURVIVED, code simplified |
| r8 | review.py:128 | `current != final.target` | redundant condition removed | SURVIVED, code simplified |
| r9 | admin_api/views.py:151 | legacy `is_verified` ignores approved | R | KILLED |
| a1 | admin_cancellation.py:79 | allow cancel for non-suspended tutor | C `test_only_for_suspended_or_removed_tutors` | KILLED |
| a2 | admin_cancellation.py:99 | booking not scoped to the tutor | C `test_explicit_ids_are_checked_one_by_one` | KILLED |
| a3 | admin_cancellation.py:102 | idempotency check removed | C `test_it_is_idempotent` | KILLED |
| a4 | admin_cancellation.py:110 | started lessons cancellable | C | KILLED |
| a5 | admin_cancellation.py:114 | missing funding not refused | C `test_one_failure_does_not_undo_the_others` | KILLED |
| a6 | admin_cancellation.py:132 | bonus `< 0` (default 0 grants) | C `test_default...` / bonus tests | KILLED |
| a7 | admin_cancellation.py:117 | refund not requested | C | KILLED |
| a8 | admin_cancellation.py:61 | `start_time_utc__lt` | C `test_the_default_list_is_the_future_lessons_only` | KILLED |
| a9 | admin_cancellation.py:71 | work queue lists tutors with 0 lessons | C TestWorkQueue | KILLED |
| a10 | admin_cancellation.py:156 | wrong e-mail variant | C | KILLED |
| a11 | cancellation.py:68 | admin cancels counted as the tutor's | C `test_the_admin_cancel_does_not_count...` | KILLED |
| a12 | admin_cancellation.py:104 | re-check of the locked tutor inverted | C | KILLED |
| s1 | strikes.py:54 | alert even with no lessons | C `test_no_alert_without_future_lessons` | KILLED |
| l1 | reviews.py:38 | booking read without a lock (order test) | C `test_review_locks_the_booking_before_the_tutor` | KILLED |

## Review conditions (commits 66240e2 / ec81b89; test file `tests/test_t1b_conditions.py`, **K**)

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| m1a | payments/views.py:525 | capture guard `is_bookable` off (M1) | K TestCaptureRefusesUnbookableTutor | KILLED |
| m1b | payments/views.py:215 | checkout guard off | K PayFast init test (and B) | KILLED |
| m2a | admin_cancellation.py:88 | PENDING_CAPTURE not counted in flight | K TestPaymentInFlight[pending_capture] | KILLED |
| m2b | admin_cancellation.py:89 | `created_at__lte` (abandoned vs recent attempt) | K `test_an_abandoned_initialised_attempt_does_not_block` | KILLED |
| m2c | admin_cancellation.py:151 | in-lock in-flight check off | K `test_explicit_ids_get_the_same_protection` | SURVIVED, then KILLED |
| m2d | admin_cancellation.py:114 | list-level in-flight partition off | K `test_flagged_holds_do_not_use_up_the_batch` | SURVIVED, then KILLED |
| m3a | admin_cancellation.py:118 | `remaining` always False | K `test_the_default_batch_is_capped_and_says_so` | KILLED |
| m3b | admin_cancellation.py:118 | cap removed | K | KILLED |
| m3c | admin_cancellation.py:130 | `MissingFunding` not caught | K `test_domain_errors_are_reported_per_lesson` | KILLED |
| m3d | admin_cancellation.py:132 | refund state / invalid transition not caught | K | KILLED |
| m1c | admin_cancellation.py:148 | tutor re-check off | K `test_a_reactivated_tutor_keeps_the_paid_lesson`, C | KILLED |
| m1d | admin_cancellation.py:145 | tutor read without lock (order test) | K `test_admin_cancel_locks_booking_then_tutor` | KILLED |

The money-edge tests (grace awaiting clearance, already settled, PayPal vs PayFast currency, lesson starting in minutes) pass on
the unchanged code: they pin existing behaviour, so they have no mutant of their own (they sit under rows a5-a7, a11 above).
The Postgres concurrency test `test_postgres_a_concurrent_reactivate_wins_over_the_admin_cancel` runs in the Postgres CI job only.

Not mutated: the Postgres-only deadlock test (skipped locally; runs in the Postgres CI job).
