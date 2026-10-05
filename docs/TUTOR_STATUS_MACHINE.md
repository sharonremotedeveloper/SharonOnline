# Tutor status machine (slice T1a)

**Created:** 2026-10-04 · **Owner:** Claude (T1a) · **Plan:** `PHASE_11_12_EXECUTION_PLAN.md` §3.1 · **Code:** `backend/apps/teachers/vetting.py`,
`backend/apps/teachers/models.py` (`TeacherProfile.status`, `TeacherStatusChange`), migrations `teachers/0007_teacher_status`,
`teachers/0008_generated_flags`. Pattern: `BOOKING_STATE_MACHINE.md`.

## 1. States and the truth table (the only one)

`TeacherProfile.status` is the only stored lifecycle column. `is_verified` and `is_active` are Django 5.2 **stored
`GeneratedField`s** computed by the database from `status`, so every existing `.filter(is_verified=..., is_active=...)` keeps
working and nothing can set them.

| status | meaning | is_verified | is_active |
| :--- | :--- | :---: | :---: |
| `applied` | account exists, application not sent (default) | False | True |
| `submitted` | application sent, waiting for a reviewer | False | True |
| `in_review` | a reviewer has it (also: approved tutor being re-vetted) | False | True |
| `changes_requested` | reviewer asked for changes (e.g. re-record the video) | False | True |
| `rejected` | application refused | False | False |
| `approved` | live tutor | True | True |
| `suspended` | was approved; taken off (admin or strike limit) | True | False |

The database also refuses an unknown value (`CHECK teacherprofile_status_valid`).

`training_completed_at` (nullable) records onboarding training (T6). It is **not** part of the truth table; the training gate
is applied by T1b's `bookable()`.

## 2. Transitions and actors

Actor kinds: **STAFF** (a user with `role='admin'`, `is_staff` or `is_superuser`, same rule as `IsPlatformAdmin`), **SELF**
(the tutor's own account), **SYSTEM** (a `'system:<source>'` string). STAFF may take every edge.

| from | to | STAFF | SELF | SYSTEM | why |
| :--- | :--- | :---: | :---: | :---: | :--- |
| applied | submitted | yes | yes | - | the applicant sends the application |
| submitted | in_review | yes | - | - | a reviewer picks it up |
| in_review | approved | yes | - | - | |
| in_review | changes_requested | yes | - | - | |
| in_review | rejected | yes | - | - | |
| changes_requested | submitted | yes | yes | - | re-submitted |
| approved | suspended | yes | - | yes | admin decision, or the strike limit (`system:strikes`) |
| approved | in_review | yes | yes | yes | re-vet after a vetted asset changed (INV TEA-11) |
| suspended | approved | yes | - | - | only a human reinstates |
| suspended | rejected | yes | - | - | permanent removal (decided by Anesu 2026-10-05, added in T1b) |
| rejected | applied | yes | - | - | re-application |

Every other pair is illegal. Adding an edge: change `ALLOWED_TRANSITIONS` **and** `PLAN_EDGES` in
`tests/test_tutor_status_machine.py` (the test compares them) and this table.

## 3. Service contract (`apps/teachers/vetting.py`)

```python
transition_teacher(teacher, to_status, *, actor, reason='', rubric=None, reviewed_assets=None) -> TeacherTransitionResult
create_teacher_profile(user, *, status='applied', actor, reason='', **fields) -> TeacherProfile
```

- `TeacherTransitionResult(changed, from_status, to_status, change_id, affected_booking_ids)`.
- Inside `transaction.atomic()`: `TeacherProfile.objects.select_for_update().only('id', 'status', 'user_id', 'updated_at')` (the
  tutor row only, no `select_related`). The decision is made on the locked row, not on the caller's possibly stale instance.
- Order of checks: unknown status -> `ValueError`; missing/malformed actor -> `ValueError`; a user who is neither staff nor the
  tutor -> `TransitionNotPermitted` (403, also for a same-state request); same state -> no-op (`changed=False`, no audit row,
  no error); illegal edge -> `InvalidTeacherTransition` (409); actor kind not allowed on the edge -> `TransitionNotPermitted`
  (403). All three error classes derive from `VettingError` and carry `http_status`.
- On a change: `save(update_fields=['status', 'updated_at'])`, one `TeacherStatusChange` row (reason truncated to 500),
  `transaction.on_commit(notify_status_change(change_id))` (a no-op log shim until N1a), and the caller's instance is
  refreshed (`status`, `is_verified`, `is_active`, `updated_at`).
- **Never takes a booking lock**, so it cannot join a booking/tutor lock cycle. Every booking path locks booking -> tutor:
  cancel / memo / no-show (they call `add_strike` while holding a booking row) and, since T1b, `bookings/services/reviews.py`
  (Postgres deadlock test `tests/test_t1b_admin_cancel.py::test_postgres_review_and_strike_on_the_same_lesson_do_not_deadlock`).
  On `-> suspended` the result lists the tutor's future `pending_payment` / `confirmed` bookings with a plain read; cancelling
  them is a separate, per-booking admin action (§10), never done here.
- `create_teacher_profile` writes the baseline audit row (`from_status=''`). STAFF and SYSTEM may create any status; the
  tutor (SELF) only `applied`; anyone else gets `TransitionNotPermitted`. Seeds use it. `record_baseline(profile, actor=...)`
  writes the same row for a profile created elsewhere (the Django admin "add" form uses it; the new profile is `applied`).
- Logs carry ids and statuses only.

### Audit trail (`TeacherStatusChange`)
Append-only: `save()` on an existing row, `delete()`, and queryset `update()` / `delete()` raise `ValueError`; the Django admin
is read-only (plus an inline on the tutor page). Deleting the tutor still cascades (the collector does not use the queryset
`delete`). Fields: `teacher`, `from_status`, `to_status`, `actor`, `actor_user`, `reason`, `rubric` (JSON), `reviewed_assets`
(JSON, for T3's ETag pinning), `created_at`.

Consequence: **the Django admin cannot delete a tutor** (or their User): the admin's delete confirmation needs delete permission
on every cascaded model, and `TeacherStatusChange` grants none. Deleting from code / the shell still cascades. The
retention / erasure policy for tutor audit rows (POPIA/GDPR) is an open item for Phase 14. **Accepted by Anesu 2026-10-05**
as the interim behaviour until Phase 14 defines retention.

## 4. Tripwires (Django silently drops writes to GeneratedFields; we refuse them)

| Write | Django 5.2 default | Now |
| :--- | :--- | :--- |
| `TeacherProfile(is_active=False)` / `objects.create(is_verified=True)` | value silently dropped | `TypeError` (`from_db` passes positional args, so loading rows is unaffected) |
| `profile.save(update_fields=['is_active'])` | silent no-op | `ValueError` |
| `TeacherProfile.objects.filter(...).update(is_active=False)` | silently dropped | `ValueError` |
| `bulk_update(objs, ['is_active'])` | - | `ValueError` |
| `profile.is_active = False` (instance assignment) | accepted, then ignored on save | `AttributeError` (Django's own loading / INSERT RETURNING / `bulk_create` / `refresh_from_db` are allowed) |
| `profile.save()` on an existing row (no `update_fields`), e.g. a DRF ModelSerializer PATCH or the admin form | writes every column, so a **stale copy writes an old `status` / `sla_strikes` back** (a suspension undone with no audit row) | saves every concrete non-generated column **except `status` and `sla_strikes`** (the service-owned columns, written only with explicit `update_fields` by `vetting.py` / `strikes.py`) |
| `profile.status = 'x'; profile.save()` (or `sla_strikes`) | written, no audit row | `ValueError` (the value differs from the one loaded / last saved) |

After an UPDATE Django does not refresh generated values: the service refreshes the caller's instance; other code must call
`refresh_from_db()`. INSERTs return them (`db_returning`).

Guard (a) (`tests/guards/test_guard_teacher_status_writes.py`) has an **empty** allowlist: only `teachers/vetting.py` (and
migrations) may write `status` / the flags; a stricter detector fails any `status` write in `apps/teachers/` outside the
service on a possible TeacherProfile receiver (neutral names such as `locked` included; another model's `Model.objects...`
chain, `self` in another class, and document / application / training / progress names are not flagged). In tests use `factories.make_teacher_profile(status=...)` to create and `factories.advance_teacher(...)` to change.

## 5. Callers converted in T1a

- `teachers/strikes.py::add_strike`: still records every strike and mirrors `sla_strikes`; at `STRIKE_LIMIT` it calls
  `transition_teacher(locked, 'suspended', actor='system:strikes')` **only when the tutor is `approved`** (any other status:
  strike recorded, status unchanged, never raises).
- `PATCH /api/v1/admin/teachers/<id>/verify/`: T1a's path-walking shim (`_legacy_verify_path`) was **deleted in T1b**; the
  endpoint now runs the explicit review actions (§9). **Decided by Anesu 2026-10-05: staff-only `suspended -> rejected` edge
  (permanent removal)**, added in T1b.
- Django admin: `status`, the flags, `training_completed_at` and `sla_strikes` are read-only; filter by `status`.
- Seeds: `seed_data` creates `approved` (trained) tutors, `seed_phase41_data` `submitted` applications, both through
  `create_teacher_profile`, idempotent.
- API: `TeacherListSerializer.is_verified` is pinned `read_only` (OpenAPI readOnly + required; TS `readonly is_verified: boolean`).

## 6. Migration mapping (0007 forwards, 0007/0008 backwards)

| old (is_verified, is_active) | status after 0007 | | status | (is_verified, is_active) after reverse |
| :--- | :--- | :-- | :--- | :--- |
| (True, True) | `approved` + `training_completed_at = migration time` (grandfathered) | | approved | (True, True) |
| (False, False) | `rejected` | | suspended | (True, False) |
| (False, True) | `applied` | | rejected | (False, False) |
| (True, False) | `suspended` + `training_completed_at = migration time` (vetted and once live) | | applied, submitted, in_review, changes_requested | (False, True) |

Any (True, False) row becomes `suspended`, whatever produced it: a strike deactivation, a Django-admin edit, or a rejection
recorded that way by hand. The old booleans cannot tell these apart; staff should review the suspended list after the deploy.

Every profile gets a baseline audit row (`'' -> status`, actor `system:migration_0007`). 0008 replaces the booleans with
GeneratedFields (RemoveField + AddField; AlterField to a generated field is unsupported) and adds the CHECK constraint; its
reverse re-adds plain booleans and recomputes them from `status` before 0007's own reverse runs. Round trip tested on SQLite
and (CI, `-m postgres`) on Postgres: `tests/test_tutor_status_migrations.py`.

### Deploying 0007 / 0008 (stop-the-world)
There is no deploy runbook yet (Phase 16); until there is, this is the procedure for any environment with data:
1. Stop the web process **and** every Celery worker and beat (old code writes `is_verified` / `is_active` and inserts profiles
   without `status`; on Postgres those writes fail against the generated columns, and old code would also bypass the audit).
2. `python manage.py migrate teachers` (0007 then 0008). On Postgres 0008 rewrites `teachers_teacherprofile` under an
   ACCESS EXCLUSIVE lock (drop + add stored generated columns, CHECK constraint): every read of the table blocks for the
   duration. The table is small (hundreds of rows), so expect seconds.
3. Start the new code (web, workers, beat). Then review the `suspended` tutors (see the mapping note above).
Rollback: stop everything, run `migrate teachers 0006_teacherstrike` while the **new** code is still deployed (the reverse
operations live in its migration files), then deploy and start the old code. The audit table is dropped by the rollback.

## 7. Hand-off notes for T1b / T1c (T1b and T1c items done 2026-10-05, see §8-§11)

- [x] (T1b) Legacy pending tutors are `applied`: the pending queue lists `applied|submitted|in_review` (§9).
- [x] (T1b) Read call sites moved to `bookable()` / `operational()` per site (§8).
- [x] (T1b) The verify shim is deleted; the endpoint runs the explicit actions. **Merge-train condition met: the shim is gone
  before N1a wires `notify_status_change`.** A legacy call can still take up to three edges (`applied -> submitted ->
  in_review -> approved`), each with its own audit row and `change_id`; N1a must notify the tutor only on outcome statuses
  (`approved`, `changes_requested`, `rejected`, `suspended`) and raise the admin "vetting submitted" alert only when the actor
  of `-> submitted` is the tutor (SELF), never for a staff lead-in.
- [x] (T1b) Lock order: reviews lock booking -> tutor (Postgres-marked test).
- [x] (T1c) `role=teacher` users without a profile get one at signup and by the 0009 backfill (§11).
- [x] (T1c) Full-row saves no longer write `status` / `sla_strikes` (§4); `/teachers/me/` saves with explicit
  `update_fields` limited to the whitelisted fields (§11).
- Notifications (`vetting:{change_id}`, `suspended:{change_id}`) hook into `notify_status_change` (N1a).

## 8. The bookable predicate and its call sites (slice T1b)

`bookable` = **approved** (`is_verified` and `is_active`) **and** `training_ok` (`TUTOR_TRAINING_GATE_ENABLED` off, or
`training_completed_at` set). `TeacherProfile.objects.bookable()` (queryset) and `profile.is_bookable` (instance) are the only
two spellings. `TUTOR_TRAINING_GATE_ENABLED=False` is **provisional** (no training content yet): **it must be ON before launch**;
`validate_production_settings` logs a warning while it is off, and the launch checklist (PRP Task 16.4 and plan §9) carries the
line "turn `TUTOR_TRAINING_GATE_ENABLED` on".
`operational()` = approved tutors plus any tutor with a confirmed / in-progress lesson that has not ended (suspended tutors
still teach their lessons): used by Eskom sync and GCal reconcile; applicants are excluded.

| # | Site | Rule |
| :-- | :--- | :--- |
| 1 | `teachers/views.py` list | `bookable()` |
| 2 | `teachers/views.py` detail | `bookable()` (evaluated per request) |
| 3 | `bookings/views.py` `TeacherSlotsView` | `bookable()` (404 otherwise) |
| 4 | `reservation.py` | `bookable()` (404 "not available for booking") |
| 5 | `rescheduling.py` | `teacher.is_bookable` for the NEW slot (the lesson itself stays) |
| 6 | `payments/views.py` checkout `_validate_booking` | `is_bookable` (409) |
| 7 | `credits.py::redeem_booking_credit` | `is_bookable` (409): a hold can outlive a suspension |
| 8 | payment webhook / PayPal capture / reconcile (`webhook_handler.slot_unavailable_reason`) | `tutor_not_bookable` -> DEF-501 quarantine (DISPUTED, restitution credit, DisputeCase, ledger 2030), never confirmed; **grace** (`confirm_grace_booking`) uses the same guard and is refused |
| 9 | `admin_api/views.py` pending list / telemetry count | `applied|submitted|in_review`, oldest first, no rejected |
| 10 | payout preview | **not** bookable and not status-filtered: a suspended / removed tutor is paid what they earned |
| 11 | Eskom sync, GCal reconcile (`integrations/tasks.py`) | `operational()` |
| 12 | serializers | `admin_api/serializers.py` reports `status`; `users/serializers.py` / public `is_verified` stay derived from `status` (T1c owns `/auth/me`) |

Operations on **existing** lessons (cancel, reschedule by the student, memo, attendance, escrow release, strikes) never call
`bookable()` (test: a student can still cancel a lesson with an untrained tutor once the gate is on). Seeds already create
`approved` + trained tutors. Because the gate hides untrained tutors, turning it on never breaks live holds only because
live tutors were grandfathered (`training_completed_at` set by migration 0007).

## 9. Staff review actions (slice T1b)

`teachers/review.py` (no path search; each action names its target and the statuses it may start from). All
`POST /api/v1/admin/teachers/<id>/<action>/ {reason}`, `IsPlatformAdmin`, throttle `admin_teacher_review`, typed result
`{teacher_id, action, previous_status, status, changed, change_ids, affected_booking_ids}`; the service re-checks staff
itself. 404 unknown tutor, 409 `invalid_transition`, 400 on a missing reason where one is required (*).

| Action | From | To | Notes |
| :--- | :--- | :--- | :--- |
| `start-review` | submitted | in_review | also `applied` / `changes_requested` via a `submitted` lead-in (staff receive the application on the tutor's behalf: until slice T5a there is no tutor "submit" step). **TODO(T5a): drop the `applied` / `changes_requested` lead-ins.** |
| `approve` | in_review | approved | |
| `request-changes` (*) | in_review | changes_requested | |
| `reject` (*) | in_review, suspended | rejected | the `suspended -> rejected` edge is staff-only (permanent removal) |
| `suspend` (*) | approved | suspended | returns `affected_booking_ids`, cancels nothing |
| `reactivate` | suspended | approved | |
| `revet` | approved | in_review | INV TEA-11 |
| `reopen` | rejected | applied | re-application |

Repeating an action whose target is already reached is a 200 no-op (`changed=false`, no audit row). The reason is stored on the
audit row (truncated to 500; the API caps it at 500). `PATCH /admin/teachers/<id>/verify/` (Slice 8 contract: `{is_verified,
rejection_reason?}` -> `{success, teacher_id, is_verified, message}`) is `legacy_verify`: optional `start-review` lead-in
then `approve` / `reject`, in one transaction under the tutor lock (a failed step rolls all back); a live tutor cannot be
rejected through it (409: suspend first), a suspended tutor can (direct edge); approve of suspended / rejected is 409.
The admin pending queue is `applied|submitted|in_review` (TODO(T5a): drop `applied`); `PendingTeacherApplicationSerializer.status`
is the real status (the frontend type was widened; T1c removes the fake Eskom area).

## 10. Suspension with future lessons (slice T1b)

`suspend` returns `affected_booking_ids` (read-only). Staff cancel with `POST /admin/teachers/<id>/cancel-future-lessons/
{reason, booking_ids?}` (`bookings/services/admin_cancellation.py`): per lesson its own transaction, only while the tutor is
`suspended` / `rejected`; paid lesson -> `cancelled_by_teacher` (`cancelled_by` = admin) with a full refund through
`refunds.request_refund` (public API only), **no strike**, `ADMIN_CANCEL_BONUS_CREDITS=0` (provisional); unpaid hold ->
`cancelled`; idempotent; the student gets the existing cancellation e-mail (`admin` / `admin_unpaid` variants) until N1a/N2.
A hold whose payment is in flight (INITIALIZED attempt younger than `PAYMENT_INFLIGHT_GRACE_SECONDS`, or a PENDING capture) is
**not** released: outcome `payment_in_flight`, listed in `payment_in_flight_ids`, left to the capture / webhook path; retry once the
payment resolved. The default list is capped at 50 lessons per call (`remaining` says whether more are left; flagged holds do
not count). Per-lesson domain errors (`MissingFunding`, refund state errors, invalid transitions) are reported per lesson and
never abort the rest. The tutor row is locked after the booking (booking -> tutor) and re-checked, so a concurrent `reactivate`
wins. PayPal's capture endpoint also refuses (409 `tutor_not_bookable`) BEFORE calling PayPal when the tutor is no longer bookable
(no charge); PayFast checkout initiation already did (a PayFast payment made after initiation is quarantined by the webhook guard).
An automatic strike suspension logs `[ADMIN ALERT] tutor <id> suspended by strikes with N future lessons needing action: <ids>`
after commit (N1a routes it) and the tutor shows in `GET /admin/teachers/suspended-with-lessons/` until the lessons are
cancelled. `add_strike` on a non-approved tutor records the strike only (idempotent per booking+kind; test
`test_a_tutor_who_is_not_approved_only_records_the_strike`).

## 11. Tutor profile at signup and `/teachers/me/` (slice T1c)

**Signup.** `POST /api/v1/auth/register/` with `role=teacher` creates the user and, in the same transaction
(`RegisterSerializer.create` is `@transaction.atomic`), the profile through
`create_teacher_profile(user, status='applied', actor=<the new user>, reason='signup')`: status `applied`, baseline audit row
`'' -> applied` with `actor='user:<username>'`, `actor_user` = the tutor (SELF may only create `applied`). If the profile
cannot be created, the user is rolled back too. A new tutor is never public (`applied` is not verified).

**Backfill.** Migration `teachers/0009_backfill_teacher_profiles` (data only) gives every existing `role=teacher` user
without a profile an `applied` profile and a baseline row with actor `system:migration_0009`. Each row is written once
(`bulk_create`), and on PostgreSQL the step ends with `SET CONSTRAINTS ALL IMMEDIATE` (ERR-192 pattern). Reverse: deletes
only profiles whose baseline row is `system:migration_0009` and that are untouched (still `applied`, no other audit row,
no availability, no booking); anything else is kept. Round trip: `tests/test_t1c_profile_backfill.py` (SQLite + Postgres-marked).
`teachers/0010_specialties_optional`: `specialties` is `blank=True` (no DB change; ERR-158).

**`GET|PATCH /api/v1/teachers/me/`** (`TeacherOwnProfileView`, `TeacherOwnProfileSerializer`, service `apps/teachers/profile.py`):
- Permission `IsAuthenticated` + `IsTeacher`; the object is always the caller's own profile (no id in the URL), 404 when a
  tutor account has no profile. `PUT` is 405. Throttles: `UserRateThrottle` always, plus the `teacher_profile` scope
  (30/hour) on PATCH.
- Response (`TeacherOwnProfile`): `id, status, is_verified, is_active, headline, bio, specialties, accent, intro_video_url,
  intro_video_thumbnail, avatar_url, intro_audio_url, has_tefl_certificate, eskom_area_id, has_inverter_backup,
  has_lte_failover, rating_avg, rating_count, sla_strikes, training_completed_at, created_at, updated_at`. Private document
  locations (TEFL certificate URL / key) are never returned, only `has_tefl_certificate`.
- **Writable whitelist** (`WRITABLE_FIELDS`): `headline` (<= 255), `bio` (<= 5000), `specialties` (list of <= 10 strings,
  each 1..40 chars after trimming; duplicates dropped; may be empty). Every other key in a PATCH body is a **400 naming the
  field** (never silently ignored): vetted fields (`VETTED_FIELDS`: accent, intro video + thumbnail, accent audio, TEFL
  certificate, photo) say "reviewed by vetting, changes only through the upload flow"; service-owned (`status`,
  `sla_strikes`, `training_completed_at`), derived (ratings, flags), staff-owned (`eskom_area_id`: it drives the Eskom
  shield that waives strikes, so a tutor must not pick it) and deprecated (`price_per_25min_usd`) fields and unknown keys say
  "cannot be changed here". Name, timezone and country live on the User (`PATCH /auth/me/`); power backup on
  `PATCH /teachers/profile/power-backup/`.
- Save: `update_own_profile` writes only the changed whitelisted fields + `updated_at` with explicit `update_fields` (never
  `status` / `sla_strikes`; nothing at all when nothing changed). No row lock: a concurrent suspension is never undone, and
  the response re-reads the live `status` / flags / strikes.
- **Re-vet hook for T3:** `revet_after_vetted_change(profile, *, actor, fields)` moves an `approved` tutor to `in_review`
  (SELF edge `approved -> in_review`, reason `re-vet: <fields> changed`) and returns the transition result; any other status
  -> `None`. Vetted fields are not writable in T1c, so nothing calls it yet: **T3's asset commit must call it** after it
  swaps a vetted asset of an approved tutor (and decides whether commits are allowed for other statuses, plan §3.1).

**`GET /api/v1/auth/me/`** has a read-only `tutor_status` (`TutorStatusEnum` | null): the tutor's status, `null` for students,
admins and a tutor account without a profile. T5 uses it in `proxy.ts` to route unverified tutors. (Named `tutor_status`, not
`status`, so it cannot be read as an account status; the TS type is `AuthUser.tutor_status`.)

## 12. Rubric, asset integrity, review packet and tutor feedback (slice T4a)

**Provisional until D-11:** four criteria scored 1-5 (`pronunciation`, `teaching_presence`, `professionalism`, `credentials`),
every score at least `VETTING_MIN_RUBRIC_SCORE` (3); `VETTING_REQUIRED_ASSET_KINDS` (default empty) lists the uploads that
must exist before approval. Code: `teachers/rubric.py`, `teachers/review.py`, `admin_api/teacher_packet_views.py`.

- **`approve` needs a rubric** (`POST /admin/teachers/<id>/approve/ {rubric, reviewed_assets?, reason?}`): missing -> 400
  `rubric_required`; wrong keys, non-integer (bool and float included) or out-of-range score -> 400 `rubric_invalid`; any score
  below the minimum -> 400 `rubric_below_threshold`; a required upload kind missing -> 400 `required_assets_missing`. The legacy
  `PATCH /admin/teachers/<id>/verify/` accepts the same `rubric` / `reviewed_assets` and **cannot bypass them** (approve without
  a rubric is 400). **The current admin vetting page still calls verify without a rubric, so approving from the UI is refused
  until slice T4b adds the rubric form.**
- **Asset integrity.** If the tutor has live uploads (`TeacherAsset`, `replaced_at` null) the reviewer must send
  `reviewed_assets` = `{kind: etag}` of what they looked at (from the review packet). Not sent -> 409 `assets_review_required`;
  different from the live set (a file swapped or added after the reviewer opened it) -> 409 `assets_changed`. The approval audit
  row stores the rubric (`{"version":1,"scores":{...}}`) and the reviewed etags. A tutor with no uploads needs none.
- **`request-changes`** accepts `requested_changes` (a list of upload kinds the tutor must redo; unknown kind -> 400
  `invalid_requested_changes`) stored on the audit row (`rubric.requested_changes`); the reason stays mandatory.
- Evidence is recorded on the decision step only (never on a legacy `submitted`/`in_review` lead-in); a repeat of a decision
  already reached is a 200 no-op and re-validates nothing.
- **`GET /admin/teachers/<id>/review-packet/`** (staff, throttled): profile, status, strikes, the criteria and minimum, required
  kinds, live upload fingerprints (kind, etag, type, size, time; **no storage key or URL**: documents open only through the
  audited download) and the last 50 decisions with scores and requested changes.
- **Tutor view (`GET /teachers/me/` -> `review_feedback`)**: only while the tutor is `changes_requested` or `rejected`:
  `{status, reason, requested_changes, decided_at}` from the latest such decision. **Scores are staff-only** and never serialised
  to the tutor (asymmetric-privacy rule, as for lesson reviews).
- **Staff alert**: when the tutor themself submits (`applied`/`changes_requested -> submitted`) `notify_status_change` raises one
  `vetting_submitted` staff alert (`admin:vetting-submitted:<change id>`); a staff lead-in raises none. Tutor-facing mails for the
  outcomes remain N2c.
- Work queue for suspended tutors with future lessons already exists (T1b §10).

## 13. Onboarding training and the gate backfill (slice T6)

Infrastructure only: Sharon writes the content (Django admin: **Training modules**, publish when ready). Code:
`teachers/training.py`, `teachers/training_views.py`, models `TrainingModule` / `TrainingProgress` (migration `teachers/0013_t6_training`).

- **Counting rule.** Only `is_published AND is_required` modules count. A tutor finishes training when every such module has a
  `TrainingProgress` row; `training_completed_at` is then set **once** by a conditional UPDATE (`... WHERE training_completed_at IS
  NULL`): a concurrent completion, a repeat or a module published later never overwrites or removes it. With **no** required
  published module nobody can finish: switching `TUTOR_TRAINING_GATE_ENABLED` on before the content exists would hide every
  new tutor.
- **Who trains.** Only an `approved` tutor (409 `training_unavailable` otherwise; the gate hides approved-but-untrained tutors, and
  nobody else has been vetted). A draft module is 404 for tutors.
- **API (`IsTeacher`, throttle scope `training` 120/h, owner-only):** `GET /teachers/me/training/` (published modules in order with
  `completed`, `required_total`, `required_completed`, `completed_at`, `can_train`), `GET .../<slug>/` (adds the Markdown `body`),
  `POST .../<slug>/complete/` (idempotent, returns the new overview).
- **Backfill before the gate (launch checklist):** `python manage.py backfill_training_completed [--dry-run]` stamps every
  `approved` tutor without a date (tutors approved after migration 0007 have none and would vanish from search once the gate is
  on). Idempotent; warns when no published required module exists. **Order: publish the modules -> run the backfill -> set
  `TUTOR_TRAINING_GATE_ENABLED=True`.**
