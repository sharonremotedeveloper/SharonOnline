# Slice T1a - tutor status machine core (working notes for a replacement agent)

Branch `feature/t1a-tutor-status` (from `feature/q0-quality-infra` + merge of `docs/phase-11-12-plan`). Design: the
Architect's brief (scratchpad `T1a/architect_brief.md`) and plan §3.1. ERR block ERR-150..159.

## Red run (first commit, tests only, 2026-10-04)

```
pytest tests/test_tutor_status_machine.py tests/test_tutor_status_integration.py
ERROR tests/test_tutor_status_machine.py      ImportError: cannot import name 'vetting' from 'apps.teachers'
ERROR tests/test_tutor_status_integration.py  ImportError: cannot import name 'vetting' from 'apps.teachers'
2 errors in 1.04s

pytest tests/test_tutor_status_migrations.py tests/guards/test_guard_teacher_status_writes.py
FAILED tests/test_tutor_status_migrations.py::test_migration_round_trip  (NodeNotFoundError: 0008_generated_flags)
FAILED tests/guards/test_guard_teacher_status_writes.py::test_teacher_status_is_written_only_by_the_service_or_the_baseline
FAILED tests/guards/test_guard_teacher_status_writes.py::test_the_service_itself_is_seen_by_the_strict_detector
3 failed, 5 passed, 4 skipped in 6.56s
```
Baseline before the slice: full suite 1934 passed, 6 skipped.

## Done
- [x] `cbd1aa8` red tests (service, integration, migrations + Postgres lock tests, guard (a) emptied + strict teachers-app guard)
- [x] `009e21a` status + training_completed_at + TeacherStatusChange + 0007 + vetting.py (flags still booleans)
- [x] `5978db0` ONE green commit: 0008 GeneratedFields + tripwires + admin + serializer pin + strikes + verify shim + seeds +
      every test site + OpenAPI/TS regenerated (suite 2069 passed)
- [x] `24c9fd3` merge of `feature/q0-quality-infra` @ `e62016e` (Q0 QA fixes; conflicts in two guard files resolved)
- [x] `e8f4ca5` three extra tests after the first mutation run (a5, l1, m4 survived -> killed)
- [x] docs commit: mutation table (47/47 KILLED), ERR-150..155, TUTOR_STATUS_MACHINE.md, ARCHITECTURE §2.1, roadmap,
      PRP 11.4 note, QUALITY_GATES, CANCELLATION_AND_REFUNDS, docs/README; frontend mock fixture `is_verified: true`

## Final gates (2026-10-04)
- backend `pytest -q`: 2084 passed, 10 skipped (Postgres/Redis-marked); `manage.py check` clean; `makemigrations --check
  --dry-run` no changes; `ruff check .` all passed
- frontend (through a temporary node_modules junction, removed): `check:api-types` ok, `lint` 0 warnings, `tsc --noEmit` ok,
  `npm test` 152/152; `npm run build` not runnable through the junction (ERR-155)

## Remaining
- Nothing in T1a scope. Postgres-marked tests (round trip on Postgres, concurrent suspensions, FOR UPDATE SQL, booking-lock
  ordering) run only in CI (`-m postgres`). Follow-ups for T1b/T1c: `docs/TUTOR_STATUS_MACHINE.md` §7.

## Next command (re-verify)
`cd backend; venv python -m pytest -q tests/test_tutor_status_machine.py tests/test_tutor_status_integration.py tests/test_tutor_status_migrations.py tests/guards/test_guard_teacher_status_writes.py`
