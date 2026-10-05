# Slice T1c - tutor profile at signup, `/teachers/me/` (PRP 11.1 partial)

Branch `feature/t1c-tutor-profile` (Claude). Plan: `docs/PHASE_11_12_EXECUTION_PLAN.md` §3.1 (vetting-asset integrity,
`/teachers/me/` writable fields, price deprecation), §4 (T1c row), §8. Contract: `docs/TUTOR_STATUS_MACHINE.md` §8.
Mutation table: `docs/mutation/T1c.md`. ERR block 170-179 (used: ERR-170, 171, 172). Migrations: `teachers/0009` (data),
`teachers/0010` (specialties blank, no DB change).

## Status
- Done: red tests (`4aa15c8`); merged `develop` db0a997 (ERR-192 migration pattern) before writing 0009; implementation
  (`c4b8418`); mutation round 1 + fixes (`60f760a`); docs (this commit).
- Remaining: none in scope. Follow-ups below.
- Next command (from `backend/`): `venv python -m pytest tests/test_t1c_tutor_profile.py tests/test_t1c_profile_backfill.py -q`

## Red run (first commit `4aa15c8`, tests only)
```
tests/test_t1c_tutor_profile.py tests/test_t1c_profile_backfill.py
FAILED tests/test_t1c_tutor_profile.py::TestRegistrationAutoProfile::test_teacher_signup_creates_an_applied_profile_with_a_baseline_audit_row
FAILED tests/test_t1c_tutor_profile.py::TestOwnProfileRead::test_student_is_forbidden   (assert 404 == 403)
FAILED tests/test_t1c_tutor_profile.py::TestRevetHook::...                              (no apps.teachers.profile)
FAILED tests/test_t1c_tutor_profile.py::TestAuthMeTutorStatus::...                      (KeyError 'tutor_status')
FAILED tests/test_t1c_profile_backfill.py::test_backfill_round_trip                     (NodeNotFoundError 0009)
... (all other new tests likewise)
70 failed, 2 passed, 1 skipped
```
The 2 passing were `test_student_signup_creates_no_tutor_profile` and `test_a_new_tutor_is_not_listed_publicly` (already
true before T1c; kept as regression guards); the skip is the Postgres-only round trip.

## Decisions (and why)
1. **Writable whitelist = `headline`, `bio`, `specialties`.** Vetted (accent, intro video/thumbnail, accent audio, TEFL
   certificate, photo) change only through T3 uploads. `eskom_area_id` is **not** tutor-writable: it decides which load-shedding
   schedule waives a tutor's strikes, so self-selection is a fraud vector (stays admin-set; a verified mapping is future work).
   Name/timezone/country stay on `/auth/me/`, power backup on its own endpoint. Every non-whitelisted key is a 400 naming the
   field (not silently ignored), so a client never believes a vetted change was saved.
2. **No row lock on PATCH**: explicit `update_fields` of only the changed whitelisted fields means a stale copy can never write
   `status` / `sla_strikes`, and edits of different fields do not clobber each other; the response re-reads the live status.
   No new `select_for_update`, so no Postgres lock test needed beyond the migration.
3. **Re-vet**: since vetted fields are not writable here, `revet_after_vetted_change` is a tested hook that T3 must call
   (approved -> in_review, actor SELF). T1c never triggers it.
4. **`/auth/me/` field is `tutor_status`** (not `status`): next to `role`/`email_verified` a bare `status` reads like an
   account status. `TutorStatusEnum | null`; null for students, admins and a tutor without a profile.
5. **Price**: `price_per_25min_usd` stays in the public tutor list/detail (and the booking's nested tutor) for one release,
   **deprecated** in OpenAPI, readOnly, nullable, and now reports the **platform catalog USD price** (read once per
   response; `null` if no active USD price) instead of the per-tutor column. Chosen over dropping the field because the
   generated TS and `normalizeBooking` destructure it, and over keeping the column value because that is not what anyone pays.
   TS changed from `price_per_25min_usd?: string` to `readonly price_per_25min_usd: string | null` (compatible for every
   reader: the only one discards it). `?max_price=` removed from the public filter; the frontend's unused `max_price` filter
   state removed. The column itself is dropped in a later release.
6. **`specialties` blank=True** in its own migration 0010 (coordinator: keep 0009 data-only). No DB change.
7. **0009 reverse** deletes only untouched backfilled profiles (baseline row by `system:migration_0009`, still `applied`, no
   other audit row, no availability, no booking). It is deliberately not a full inverse.

## Gates (final run, after the docs commit)
See the hand-off; counts are pasted there.

## Follow-ups for later slices
- **T3**: call `apps.teachers.profile.revet_after_vetted_change` from the asset commit for approved tutors; decide commits for
  other statuses (plan §3.1).
- **T5**: route on `AuthUser.tutor_status` in `proxy.ts` (needs the value in the signed session cookie or a `/me` call).
- **T7**: `frontend/src/app/teacher/profile/page.tsx` is static markup with no API calls; wiring it to `GET|PATCH
  /teachers/me/` (form state, field errors, vetted-field notice) is not trivial, so it is left for T7.
- Later release: drop `TeacherProfile.price_per_25min_usd` and the deprecated API field (and `seed_*` / admin uses).
- Admin `PendingTeacherApplicationSerializer.status` is still derived from the flags (T1b owns it); the pending-vetting
  endpoint has no typed OpenAPI response yet (frontend type `PendingTeacherApplication.eskom_area` is now `string | null`).
