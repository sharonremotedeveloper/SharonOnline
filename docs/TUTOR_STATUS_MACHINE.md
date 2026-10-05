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
- **Never takes a booking lock**, so it cannot join a booking/tutor lock cycle. Cancel / memo / no-show lock booking -> tutor
  (they call `add_strike` while holding a booking row); **not everywhere**: `bookings/services/reviews.py::submit_review` locks
  tutor -> booking (T1b aligns it, §7). On `-> suspended` the result lists the tutor's future `pending_payment` / `confirmed`
  bookings with a plain read; cancelling them is a separate, per-booking admin action (T1b), never done here.
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
- `PATCH /api/v1/admin/teachers/<id>/verify/` (legacy, **T1b replaces it**): walks the shortest legal path to `approved` /
  `rejected` through the service as the admin (reason = `rejection_reason` or `legacy-verify`), in one transaction, reading
  the tutor once under the row lock. Same response shape and codes (200 / 400 / 403 / 404); a target the table cannot reach
  is 409 (`code: invalid_transition`). A path to `rejected` **may not pass through `approved`** (that would write a fake
  reinstatement into the audit trail, and a fake "approved" notification once N1a lands), so **rejecting a suspended tutor is
  409** today. **Decided by Anesu 2026-10-05: add a staff-only `suspended -> rejected` edge (permanent removal)**; slice T1b
adds it to the transition table and the explicit admin review actions (the legacy shim is deleted there).
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

## 7. Hand-off notes for T1b / T1c

- **Legacy pending tutors become `applied`**, not `submitted`: the old schema could not tell "applied" from "sent". T1b's
  pending queue (`submitted|in_review`) must also show (or let staff move) `applied` tutors that have their documents, or they
  disappear from the admin queue. `admin_api/views.py` pending list/count still read `is_verified=False` (T1b owns them).
- Read call sites still use `is_verified` / `is_active` (they keep working): `teachers/views.py`, `bookings/views.py`,
  `reservation.py`, `rescheduling.py`, `payments/views.py`, `admin_api/views.py` (pending, payout preview), `integrations/tasks.py`,
  `users/serializers.py`, `admin_api/serializers.py`. T1b replaces them with `bookable()` per the plan's per-site decisions.
- The verify shim is temporary; T1b deletes it in favour of explicit review actions (submit / start review / approve / request
  changes / reject / suspend / reinstate) that call `transition_teacher` with a rubric. **Merge-train condition: T1b must
  delete the shim before N1a wires `notify_status_change`** (the shim walks several edges per call; each would notify).
- **Lock order (T1b):** `bookings/services/reviews.py::submit_review` locks the tutor row, then the booking (tutor -> booking),
  while cancel / memo / no-show lock booking -> tutor (`add_strike`). A review and a strike on the same lesson can deadlock on
  Postgres (one is retried/aborted). T1b should lock booking -> tutor in the review path (or update the rating with an atomic
  F-expression without a tutor lock) and add a Postgres-marked test.
- `role=teacher` users without a profile are not given one here (T1c, registration auto-profile).
- Full-row saves no longer write `status` / `sla_strikes` (§4); T1c's `/teachers/me/` PATCH should still save with explicit
  `update_fields` limited to the whitelisted fields.
- Notifications (`vetting:{change_id}`, `suspended:{change_id}`) hook into `notify_status_change` (N1a).
