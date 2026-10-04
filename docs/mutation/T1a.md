# Mutation table - slice T1a (tutor status machine core)

Every row was run with `backend/scripts/mutate.py` on a clean tree (2026-10-04, branch `feature/t1a-tutor-status`), driven by
a scratchpad script that passes the arguments as an argv list (no shell quoting). The helper injected the mutant, ran the
listed test files, restored the file and verified the restore by hash; every run reported `restored: ok` and
`git status --porcelain` was empty afterwards. Line numbers refer to commit `24c9fd3` (unchanged at `e8f4ca5`).

Test files: **M** = `tests/test_tutor_status_machine.py`, **I** = `tests/test_tutor_status_integration.py`,
**Mig** = `tests/test_tutor_status_migrations.py`, **G** = `tests/guards/test_guard_teacher_status_writes.py`,
**S** = `tests/test_refunds_credits_strikes.py`.

## Transition table (`apps/teachers/vetting.py`)

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| t1 | `vetting.py:35` | applied->submitted loses SELF | M `test_allowed_table_matches_the_plan`, `test_self_and_system_take_only_their_edges` | KILLED |
| t2 | `vetting.py:35` | applied->submitted becomes applied->in_review | M (table, staff edges, illegal pairs) | KILLED |
| t3 | `vetting.py:36` | submitted->in_review gains SELF | M | KILLED |
| t4 | `vetting.py:38` | in_review->approved gains SYSTEM | M | KILLED |
| t5 | `vetting.py:39` | in_review->changes_requested gains SELF | M | KILLED |
| t6 | `vetting.py:40` | in_review->rejected becomes in_review->suspended | M | KILLED |
| t7 | `vetting.py:42` | changes_requested->submitted loses SELF | M | KILLED |
| t8 | `vetting.py:44` | approved->suspended loses SYSTEM (strikes could not suspend) | M, I | KILLED |
| t9 | `vetting.py:45` | approved->in_review loses SELF | M | KILLED |
| t10 | `vetting.py:47` | suspended->approved gains SYSTEM (automatic reinstatement) | M | KILLED |
| t11 | `vetting.py:48` | rejected->applied becomes rejected->submitted | M | KILLED |

## Actor policy, no-op, lock, suspension read, audit/notify

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| a1 | `vetting.py:87` | `role == 'admin'` no longer makes STAFF | M `test_staff_is_any_platform_admin[role_admin]` | KILLED |
| a2 | `vetting.py:87` | `is_staff` no longer makes STAFF | M `test_staff_is_any_platform_admin[is_staff]` | KILLED |
| a3 | `vetting.py:93` | any string accepted as a system actor | M `test_missing_actor_unknown_status_and_bad_actor_string_are_value_errors` | KILLED |
| a4 | `vetting.py:101` | any user counts as SELF | M `test_another_tutor_or_a_student_is_not_permitted_even_on_a_self_edge` | KILLED |
| a5 | `vetting.py:130` | stranger check removed | M `test_a_stranger_is_refused_even_when_nothing_would_change` (added after the first run SURVIVED) | KILLED |
| a6 | `vetting.py:136` | illegal-edge check removed | M `test_every_illegal_pair_raises_and_changes_nothing` | KILLED |
| a7 | `vetting.py:138` | actor-kind check removed | M `test_self_and_system_take_only_their_edges` | KILLED |
| n1 | `vetting.py:132` | same-state no-op removed | M `test_same_state_is_a_no_op` | KILLED |
| l1 | `vetting.py:127` | `.select_for_update()` removed | M `test_the_service_row_locks_the_tutor_only` (queryset spy, added after the first run SURVIVED: SQLite drops FOR UPDATE); Mig Postgres tests check the SQL in CI | KILLED |
| b1 | `vetting.py:144` | affected bookings reported on every transition | M `test_other_transitions_report_no_bookings` | KILLED |
| b2 | `vetting.py:113` | pending-payment holds left out of the suspension report | M `test_suspension_returns_future_pending_and_confirmed_bookings_without_touching_them` | KILLED |
| b3 | `vetting.py:114` | past instead of future lessons | same | KILLED |
| h1 | `vetting.py:145` | notification hook not scheduled | M `test_a_notification_hook_runs_after_commit` | KILLED |
| h2 | `vetting.py:146` | caller's instance not refreshed | M `test_every_allowed_edge_works_for_staff_and_writes_one_audit_row` | KILLED |
| h3 | `vetting.py:120` | reason truncation 500 -> 900 | M `test_rubric_and_reviewed_assets_are_recorded_and_reason_is_truncated` | KILLED |

## Tripwires and the generated truth table (`apps/teachers/models.py`)

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| w1 | `models.py:97` | constructor accepts `is_verified=` / `is_active=` | M `test_constructor_refuses_the_derived_flags` | KILLED |
| w2 | `models.py:102` | `save(update_fields=['is_active'])` silently no-op | M `test_save_with_update_fields_on_a_flag_raises` | KILLED |
| w3 | `models.py:24` | `QuerySet.update(is_active=...)` silently dropped | M `test_queryset_update_of_a_flag_raises` | KILLED |
| w4 | `models.py:28` | `bulk_update([...], ['is_active'])` allowed | same | KILLED |
| w5 | `models.py:200` | audit row editable | M `test_audit_rows_cannot_be_edited_or_deleted` | KILLED |
| w6 | `models.py:169` | audit queryset `update()` allowed | same | KILLED |
| w7 | `models.py:8` | `VERIFIED_STATUSES` loses `suspended` | M `test_status_choices_are_the_seven_plan_states` | KILLED |

## Migration mapping (`0007_teacher_status.py`, `0008_generated_flags.py`)

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| m1 | `0007:22` | (True, False) -> rejected instead of suspended | Mig `test_migration_round_trip` | KILLED |
| m2 | `0007:23` | reverse suspended -> (False, False) | same | KILLED |
| m3 | `0007:35` | every tutor grandfathered as trained | same | KILLED |
| m4 | `0008:20` | 0008 reverse does not restore `is_active` | same (now also checks the 0007 state; first run SURVIVED because 0007's own reverse recomputed it) | KILLED |
| m5 | `0008:12` | generated `is_verified` expression loses `suspended` | M `test_generated_flags_follow_the_truth_table[suspended-flags6]` | KILLED |

## Strike hook (`apps/teachers/strikes.py`), legacy verify shim (`apps/admin_api/views.py`), guard (a)

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| s1 | `strikes.py:36` | suspend regardless of status (not-approved tutor would raise) | I `test_a_tutor_who_is_not_approved_only_records_the_strike` | KILLED |
| s2 | `strikes.py:36` | `>=` -> `>` on the strike limit | I `test_the_limit_suspends_through_the_service`, S | KILLED |
| s3 | `strikes.py:39` | caller's copy not refreshed | I `test_the_limit_suspends_through_the_service` | KILLED |
| s4 | `strikes.py:37` | actor label changed | same | KILLED |
| v1 | `views.py:133` | reject targets `suspended` | I `test_reject_records_the_reason` | KILLED |
| v2 | `views.py:137` | unreachable-path 409 removed | I `test_unreachable_target_is_409_and_changes_nothing` | KILLED |
| v3 | `views.py:128` | default reason `legacy-verify` dropped | I `test_approve_walks_the_shortest_legal_path` | KILLED |
| g1 | `views.py:130` | adds `profile.is_verified = True` | G `test_teacher_status_is_written_only_by_the_service_or_the_baseline` (NEW offender, allowlist empty) | KILLED |
| g2 | `strikes.py:34` | adds `locked.status = 'approved'` | G `test_teachers_app_writes_status_only_in_the_service` | KILLED |

Totals: 47 mutants, 47 KILLED (3 needed a new test after a first SURVIVED run: a5, l1, m4).
