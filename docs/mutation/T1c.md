# Mutation table - slice T1c (tutor profile at signup, `/teachers/me/`)

Run 2026-10-05 by Claude with `backend/scripts/mutate.py` (driven by `scratchpad/T1c/run_mutants.py` and `run_mutants2.py`;
one textual mutant at a time on a clean committed tree, restored and hash-verified by `mutate.py`). Tests per mutant: the
named class of `tests/test_t1c_tutor_profile.py` (`T`) or `tests/test_t1c_profile_backfill.py` (`M`).
Round 1 (commit `c4b8418`): **25 / 29 killed**. Round 2 (after the fixes in ERR-172): **7 / 8 killed, 1 equivalent**.

Paths relative to `backend/`. `prof` = `apps/teachers/profile.py`, `tv` = `apps/teachers/views.py`, `ts` =
`apps/teachers/serializers.py`, `us` = `apps/users/serializers.py`, `as` = `apps/admin_api/serializers.py`, `m9` =
`apps/teachers/migrations/0009_backfill_teacher_profiles.py`. Line numbers are those at each run (round 2 ran on the commit after
the ERR-172 fixes).

| # | file:line | mutant | killing test | result |
| :-- | :-- | :-- | :-- | :-- |
| 1 | prof:34 | whitelist check in `update_own_profile` disabled | r1 SURVIVED -> `TestRevetHook::test_service_refuses_non_whitelisted_fields_even_without_the_serializer` | KILLED (r2) |
| 2 | prof:36 | every whitelisted key counts as changed | `TestOwnProfileUpdate::test_unchanged_values_do_not_touch_the_row` | KILLED |
| 3 | prof:37 | no-op guard removed (save with no changes) | `test_unchanged_values_do_not_touch_the_row` | KILLED |
| 4 | prof:41 | `status` added to `update_fields` | `test_save_never_writes_status_or_strikes` | KILLED |
| 5 | prof:41 | full-row `save()` instead of `update_fields` | `test_save_never_writes_status_or_strikes` | KILLED |
| 6 | prof:55 | re-vet condition inverted | `TestRevetHook::test_approved_tutor_goes_back_to_review` | KILLED |
| 7 | prof:58 | re-vet target `IN_REVIEW` -> `SUSPENDED` | `test_approved_tutor_goes_back_to_review` | KILLED |
| 8 | tv:81 | `IsTeacher` -> `IsAuthenticated` (authorization) | `TestOwnProfileRead::test_student_is_forbidden` | KILLED |
| 9 | tv:81 | `AllowAny` | `test_anonymous_is_unauthorised` | KILLED |
| 10 | tv:88 | PATCH loses the `teacher_profile` scoped throttle | `test_patch_rate_limit_answers_429` | KILLED |
| 11 | tv:89 | GET also counted against the write scope | `test_patch_rate_limit_answers_429` (GET after 429 must be 200) | KILLED |
| 12 | tv:100 | response refresh without `status` | r1 SURVIVED -> `test_a_suspension_racing_the_edit_is_not_undone` (response assertion) | KILLED (r2) |
| 13 | tv:100 | response refresh removed | `test_a_suspension_racing_the_edit_is_not_undone` | KILLED (r2) |
| 14 | ts:58 | catalog cache inverted (KeyError / re-read) | `TestPriceDeprecation` | KILLED |
| 15 | ts:62 | missing catalog price -> invented `'9.00'` | `test_missing_catalog_price_is_null_not_an_error` | KILLED |
| 16 | ts:82 | non-string tags accepted | `test_specialties_must_be_a_short_list_of_short_tags[value1]` | KILLED |
| 17 | ts:119 | every key treated as writable | `test_vetted_or_upload_managed_fields_are_rejected` | KILLED |
| 18 | ts:123 | rejected keys not raised | `test_service_owned_and_unknown_fields_are_rejected` | KILLED |
| 19 | ts:131 (r1) | blank-tag check disabled | r1 SURVIVED: equivalent (`_TagField(allow_blank=False)` already rejects); check **removed** | n/a |
| 20 | ts:130 | no de-duplication | `test_specialties_are_trimmed_and_deduplicated_and_may_be_empty` | KILLED |
| 21 | us:87 | `/auth/me` reports `'approved'` for every tutor | `TestAuthMeTutorStatus::test_tutor_sees_their_status` | KILLED |
| 22 | us:156 | registration not atomic | `TestRegistrationAutoProfile::test_profile_creation_failure_rolls_the_user_back` | KILLED |
| 23 | us:171 | no profile at teacher signup | `test_teacher_signup_creates_an_applied_profile_with_a_baseline_audit_row` | KILLED |
| 24 | us:173 | actor `system:signup` instead of the tutor | `test_signup_goes_through_the_service_as_the_tutor_themself` | KILLED |
| 25 | as:55 | missing area -> `''` instead of null | `test_missing_area_is_null_not_a_placeholder` | KILLED |
| 26 | as:59 | inverter always `True` | `test_real_eskom_area_and_inverter_values` | KILLED |
| 27 | m9:28 | backfill every role | `M::test_backfill_round_trip` | KILLED |
| 28 | m9:28 | backfill users who already have a profile | `M::test_backfill_round_trip` | KILLED |
| 29 | m9:42 | reverse ignores later history | r1 SURVIVED -> `noted_tutor` row | KILLED (r2) |
| 30 | m9:42 | reverse deletes profiles it did not create | r1 SURVIVED -> `old_applicant` row | KILLED (r2) |
| 31 | m9:43 | reverse ignores availability | `busy_tutor` row | KILLED (r2) |
| 32 | m9:42 | `status='applied'` dropped | - | **EQUIVALENT**: every status change writes a `TeacherStatusChange` row (guard (a): only `vetting.py` writes `status`), so a moved tutor is already excluded by the "no other audit row" filter; the status filter is a second, independent safety net |

Not mutated: `bookings__isnull=True` in the 0009 reverse (removing it makes the delete raise `ProtectedError`,
`Booking.teacher` is `PROTECT`, so it cannot silently destroy a lesson); the Postgres `SET CONSTRAINTS ALL IMMEDIATE` line
(only observable on Postgres; covered by `test_backfill_round_trip_on_postgres` in CI).
