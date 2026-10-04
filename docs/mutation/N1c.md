# Mutation table - slice N1c (unified `send_email`)

Run 2026-10-04 by Claude with `scratchpad/N1c/mutate.py` (one textual mutant at a time on a clean worktree, original restored
in `finally`, tree verified clean afterwards). Tests run per mutant: `tests/test_send_email.py`, `tests/test_settings_guard.py`,
`tests/test_account_recovery.py::TestMailPlumbing` (`-x`). **29 / 29 KILLED.**

Paths are relative to `backend/`. `svc` = `apps/integrations/services/email.py`, `leg` = `apps/integrations/email.py`.

| # | file:line | mutant | killing test | result |
| :-- | :-- | :-- | :-- | :-- |
| 1 | svc:134 | `status_code == 409` -> `== 410` | `TestErrorMapping::test_409_is_in_flight` | KILLED |
| 2 | svc:135 | 409 returns `RETRYABLE` instead of `IN_FLIGHT` | `TestErrorMapping::test_409_is_in_flight` | KILLED |
| 3 | svc:136 | drop `== 429` (5xx only) | `test_rate_limit_and_server_errors_are_retryable[429]` | KILLED |
| 4 | svc:136 | drop `>= 500` (429 only) | `test_rate_limit_and_server_errors_are_retryable[500]` | KILLED |
| 5 | svc:138 | other 4xx -> `RETRYABLE` | `test_other_4xx_fail_permanently_with_a_short_code[422]` | KILLED |
| 6 | svc:128 | success range `< 300` -> `< 500` | `test_409_is_in_flight` | KILLED |
| 7 | svc:117 | timeout -> `FAILED` | `test_timeouts_and_connection_errors_are_retryable[timeout]` | KILLED |
| 8 | svc:119 | connection error -> `FAILED` | `test_timeouts_and_connection_errors_are_retryable[connection_error]` | KILLED |
| 9 | svc:82 | `Idempotency-Key` header not set | `TestSuccess::test_idempotency_key_is_sent_as_header` | KILLED |
| 10 | svc:91 | CR/LF check disabled | `test_cr_lf_is_rejected_before_any_send[subject CRLF]` | KILLED |
| 11 | svc:29 | regex `[\r\n]` -> `[\r]` | `test_cr_lf_is_rejected_before_any_send[subject LF]` | KILLED |
| 12 | svc:90 | `reply_to` not checked | `test_cr_lf_is_rejected_before_any_send[reply_to]` | KILLED |
| 13 | svc:93 | idempotency key length cap removed | `test_overlong_idempotency_key_rejected` | KILLED |
| 14 | svc:71 | unknown mode treated as console | `TestConsoleMode::test_unknown_mode_is_a_configuration_error` | KILLED |
| 15 | svc:76 | missing key check removed | `test_missing_key_in_resend_mode_fails_without_calling_the_provider` | KILLED |
| 16 | svc:133 | provider error name kept unfiltered | `test_provider_error_name_is_only_kept_when_it_is_a_plain_identifier` | KILLED |
| 17 | svc:130 | provider message id kept unfiltered | `test_an_odd_provider_id_is_not_kept` | KILLED |
| 18 | svc:119 | log exception text instead of type | `TestLogsCarryIdsOnly::test_exception_text_is_not_logged` | KILLED |
| 19 | svc:167 | console mode logs recipients | `TestMailPlumbing::test_console_mode_never_logs_links_or_addresses` | KILLED |
| 20 | svc:62 | `format_html` -> `str.format` (no escaping) | `TestEscapingHelper::test_hostile_values_are_escaped` | KILLED |
| 21 | svc:107 | attachment not base64 | `test_attachments_are_base64_with_filename_and_content_type` | KILLED |
| 22 | `config/settings/guard.py:63` | production accepts `console` | `TestProductionGuard::test_production_refuses_anything_but_resend[console]` | KILLED |
| 23 | `config/settings/guard.py:35` | mode always resolves to `resend` | `TestProductionGuard::test_mode_resolution[no key]` | KILLED |
| 24 | `config/settings/guard.py:31` | explicit mode not normalised | `TestProductionGuard::test_mode_resolution[' Resend ']` | KILLED |
| 25 | `scripts/check_deploy.py:53` | only literal `console` refused | `TestProductionGuard::test_check_deploy_refuses_console_mode` | KILLED |
| 26 | leg:24 | raising wrapper swallows non-sent | `TestLegacyWrapper::test_anything_but_sent_raises_for_the_celery_retry[409]` | KILLED |
| 27 | leg:88 | confirmation swallows non-sent | `TestBookingConfirmation::test_anything_but_sent_raises_so_fulfilment_retries[409]` | KILLED |
| 28 | leg:61 | confirmation key ignores the generation | `TestBookingConfirmation::test_a_reschedule_changes_the_key` | KILLED |
| 29 | leg:71 | confirmation HTML not escaped | `TestBookingConfirmation::test_names_and_links_are_escaped` | KILLED |

## QA round 1 (2026-10-04): `scratchpad/N1c/mutate_qa.py`, tests `test_send_email_qa.py`, `test_send_email.py`, `test_settings_guard.py`, `TestMailPlumbing`, `test_profiles_support.py`. **23 / 23 KILLED**, tree clean afterwards. Line numbers are after commit `5604623`.

| # | file:line | mutant | killing test | result |
| :-- | :-- | :-- | :-- | :-- |
| Q1 | svc:32 | separator regex `[,;]` -> `[,]` | `TestNits::test_separators_inside_one_address_are_rejected[;]` | KILLED |
| Q2 | svc:95 | separator check disabled | `TestNits::test_separators_inside_one_address_are_rejected[,]` | KILLED |
| Q3 | svc:102 | printable-ASCII key check disabled | `TestIdempotencyKeyCharset::test_non_printable_ascii_is_rejected[é]` | KILLED |
| Q4 | svc:33 | range `\x20-\x7e` -> `\x20-\x7f` (DEL allowed) | `test_non_printable_ascii_is_rejected[del\x7f]` | KILLED |
| Q5 | svc:146 | Retry-After read on every retryable status | `TestRetryAfter::test_only_429_and_503_carry_it[500]` | KILLED |
| Q6 | svc:156 | cap removed | `TestRetryAfter::test_value_is_capped` | KILLED |
| Q7 | svc:154 | digit check removed | `TestRetryAfter::test_http_dates_and_junk_are_ignored[HTTP-date]` | KILLED |
| Q8 | svc:168 | no warning for a 2xx without id | `TestNits::test_2xx_without_id_logs_a_warning` | KILLED |
| Q9 | leg:33 | `failed` raises the plain error | `test_failed_raises_the_permanent_subclass_with_the_result[422]` | KILLED |
| Q10 | leg:33 | everything raises the permanent error | `test_in_flight_and_retryable_raise_the_plain_error[409]` | KILLED |
| Q11 | leg:34 | `.result` not attached | `test_failed_raises_the_permanent_subclass_with_the_result[422]` | KILLED |
| Q12 | leg:40 | permanent-failure log at DEBUG | `test_account_mail_permanent_failure_is_not_retried_and_is_logged_with_ids` | KILLED |
| Q13 | `apps/users/tasks.py:54` | account mail without `dont_autoretry_for` | `test_account_mail_permanent_failure_is_not_retried...` / `test_autoretry_tasks_skip_permanent_failures` | KILLED |
| Q14 | `apps/users/tasks.py:66` | account mail permanent failure not logged | `test_account_mail_permanent_failure_is_not_retried_and_is_logged_with_ids` | KILLED |
| Q15 | `apps/users/tasks.py:90` | support inquiry: permanent branch removed (retries) | `TestManualRetryCallers::test_support_inquiry_permanent_failure_is_not_retried` | KILLED |
| Q16 | `apps/payments/tasks.py:29` | admin alert without `dont_autoretry_for` | `test_autoretry_tasks_skip_permanent_failures[send_admin_alert_email_task]` | KILLED |
| Q17 | `apps/payments/tasks.py:41` | payment failure without `dont_autoretry_for` | `test_autoretry_tasks_skip_permanent_failures[send_payment_failure_email_task]` | KILLED |
| Q18 | `apps/payments/tasks.py:248` | refund processed without `dont_autoretry_for` | `test_autoretry_tasks_skip_permanent_failures[send_refund_processed_email_task]` | KILLED |
| Q19 | `apps/integrations/tasks.py:224` | Eskom: permanent branch removed | `TestManualRetryCallers::test_eskom_permanent_failure_is_not_retried` | KILLED |
| Q20 | `apps/integrations/tasks.py:302` | cancellation: permanent branch removed | `TestManualRetryCallers::test_cancellation_permanent_failure_is_not_retried` | KILLED |
| Q21 | `apps/integrations/tasks.py:225` | Eskom row not marked `permanent:` | `test_eskom_permanent_failure_is_not_retried` | KILLED |
| Q22 | `apps/integrations/tasks.py:301` | cancellation HTML unescaped again | `test_cancellation_mail_escapes_the_student_name` | KILLED |
| Q23 | `config/settings/local.py:54` | console `EMAIL_BACKEND` removed from local | `test_console_mail_backend_is_set_by_local_settings_only` | KILLED |
