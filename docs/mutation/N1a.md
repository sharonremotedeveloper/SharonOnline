# Mutation table - slice N1a (notifications app core)

Run 2026-10-05 by Claude with `backend/scripts/mutate.py` (driver `scratchpad/N1a/run_mutants.py`: one textual mutant per
run on a clean worktree, original restored and hash-verified; tree clean afterwards). **37 / 37 KILLED.**

Paths relative to `backend/`. `D` = `apps/notifications/delivery.py`, `S` = `service.py`, `A` = `alerts.py`,
`R` = `retention.py` (same app), `F` = `apps/bookings/services/fulfillment.py`, `P` = `apps/bookings/services/attendance_probe.py`.
Test files per mutant: `TD` = `tests/test_notifications_delivery.py`, `TC` = `..._core.py`, `TA` = `..._alerts.py`,
`TR` = `..._retention.py`.

| # | file:line | mutant | class | killed by (file) | result |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | D:33 | resend cutoff `hours=20` -> `24` | idempotency | TD `test_no_resend_after_20_hours_without_review` | KILLED |
| 2 | D:44 | due retry `next_attempt__lte` -> `__gte` | state transition | TD `test_retryable_only_when_due` | KILLED |
| 3 | D:45 | lease `now - lease()` -> `now + lease()` | lock / lease | TD `test_lease_expires_after_15_minutes` | KILLED |
| 4 | D:52 | claim does not count the attempt | state transition | TD `test_pending_is_claimed_once` | KILLED |
| 5 | D:54 | claim always reports success (CAS ignored) | lock | TD `test_pending_is_claimed_once` | KILLED |
| 6 | D:64 | stale check `>=` -> `<=` | idempotency | TD (every send) | KILLED |
| 7 | D:67 | missing-address check inverted | state transition | TD `test_missing_address_fails...` | KILLED |
| 8 | D:71 | no `Idempotency-Key` sent | idempotency | TD `test_sent`, `TestResendIdempotency` | KILLED |
| 9 | D:79 | sent mapping inverted | state transition | TD `test_sent` | KILLED |
| 10 | D:86 | `in_flight` no longer retryable | state transition | TD `test_retryable_and_in_flight_back_off[in_flight]` | KILLED |
| 11 | D:87 | attempts cap `>=` -> `>` | state transition | TD `test_attempts_cap_then_failed_and_alert` | KILLED |
| 12 | D:110 | alert recursion guard inverted | idempotency | TD `test_failed_admin_alert_never_alerts_again` | KILLED |
| 13 | D:118 | result write ignores the claim token | lock | TD `test_a_late_result_after_the_lease_was_taken_over_is_discarded` | KILLED |
| 14 | D:118 | result write expects `pending` | lock | TD `test_sent` | KILLED |
| 15 | D:130 | no jitter | retry | TD `test_first_retry_about_a_minute_with_jitter` | KILLED |
| 16 | D:132 | `retry_after` floor -> ceiling | retry | TD `test_retry_after_is_honoured` | KILLED |
| 17 | D:141 | sweep picks young pending rows | state transition | TD `test_picks_due_rows_only` | KILLED |
| 18 | D:161 | human requeue selects `sent` rows | authorization / state | TD `test_requeue_failed_resets...` | KILLED |
| 19 | D:163 | requeue keeps the old 20 h window | idempotency | TD `test_requeue_failed_resets...` | KILLED |
| 20 | S:28 | `review` not a forbidden payload key | privacy | TC `test_payload_is_ids_only[payload0]` | KILLED |
| 21 | S:54 | duplicate key not short-circuited | idempotency | TC `test_duplicate_key_returns_existing_row...` | KILLED |
| 22 | S:60 | in-app opt-out ignored | preferences | TC `test_optional_in_app_off...` | KILLED |
| 23 | S:66 | insert without its own savepoint | idempotency / txn | TC `test_duplicate_insert_race_never_poisons...` | KILLED |
| 24 | S:70 | enqueue even when e-mail is skipped | state transition | TC `test_optional_email_off_by_preference` | KILLED |
| 25 | S:79 | mandatory set inverted | authorization (prefs) | TC `test_mandatory_kind_always_emails...` | KILLED |
| 26 | S:83 | e-mail opt-out inverted | preferences | TC `test_optional_email_off_by_preference` | KILLED |
| 27 | A:26 | staff filter dropped (any user by address) | authorization | TA `test_setting_selects_staff_accounts_by_address` | KILLED |
| 28 | A:29 | inactive admins receive alerts | authorization | TA `test_default_is_every_active_admin` | KILLED |
| 29 | A:49 | one key for all recipients | idempotency | TA `test_one_notification_per_recipient...` | KILLED |
| 30 | R:18 | read retention 180 -> 170 days | retention | TR `test_read_in_app_items_after_180_days` | KILLED |
| 31 | R:25 | `read_at__lt` -> `__gt` | retention | TR `test_read_in_app_items_after_180_days` | KILLED |
| 32 | R:26 | unfinished e-mail rows purged | retention | TR `test_email_only_rows_after_90_days_when_finished` | KILLED |
| 33 | F:210 | fulfilment-failed alert removed | alert | TA `test_fulfilment_terminal_failure` | KILLED |
| 34 | F:215 | needs-attention alert removed | alert | TA `test_fulfilment_needs_attention...` | KILLED |
| 35 | F:262 | orphaned-meeting alert removed | alert | TA `test_orphaned_zoom_meeting...` | KILLED |
| 36 | F:335 | orphaned-calendar alert removed | alert | TA `test_orphaned_calendar_event...` | KILLED |
| 37 | P:191 | disputed-without-verdict alert removed | alert | TA `test_dispute_without_verdict` | KILLED |
