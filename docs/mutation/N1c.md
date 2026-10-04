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
