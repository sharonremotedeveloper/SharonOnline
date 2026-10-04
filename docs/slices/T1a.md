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
- [x] red tests (service, integration, migrations + Postgres lock tests, guard (a) emptied + strict teachers-app guard)

## Remaining (brief's commit order)
- [ ] status + training_completed_at + TeacherStatusChange + 0007 + vetting.py
- [ ] ONE green commit: 0008 GeneratedFields + tripwires + admin + serializer pin + strikes + verify shim + seeds + all test sites
- [ ] guard/migration/PG tests green
- [ ] mutation table `docs/mutation/T1a.md`, ERR entries, docs (TUTOR_STATUS_MACHINE.md, ARCHITECTURE §2.1, roadmap), OpenAPI/TS

## Next command
`cd backend; venv python -m pytest -q tests/test_tutor_status_machine.py tests/test_tutor_status_integration.py tests/test_tutor_status_migrations.py tests/guards/test_guard_teacher_status_writes.py`
