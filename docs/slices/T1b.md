# Slice T1b - bookable predicate, call sites, admin review actions (working notes for a replacement agent)

Branch `feature/t1b-bookable-review` (from `develop` 47b69c9, fast-forwarded to db0a997 / ERR-192). Plan §3.1, PRP 11.1/11.4.
ERR block ERR-160..169. Mutation table `docs/mutation/T1b.md`.

## Red run (first commit, tests only, 2026-10-05)

```
pytest tests/test_t1b_bookable.py tests/test_t1b_review_actions.py tests/test_t1b_admin_cancel.py
       tests/test_tutor_status_machine.py tests/test_tutor_status_integration.py tests/test_tutor_status_signoff.py -q
...
FAILED tests/test_tutor_status_machine.py::test_allowed_table_matches_the_plan
FAILED tests/test_tutor_status_signoff.py::test_rejecting_a_suspended_tutor_takes_the_direct_edge_and_writes_no_fake_approval
FAILED tests/test_t1b_admin_cancel.py::test_review_locks_the_booking_before_the_tutor
130 failed, 165 passed, 1 skipped, 147 warnings in 14.85s
```

## Done
- [x] red tests (bookable predicate + call sites, review actions + legacy verify + pending queue, admin cancel + work queue
      + strike alert, lock order incl. Postgres deadlock test; PLAN_EDGES gains suspended -> rejected)

## Remaining
- implementation (settings, `bookable()/operational()`, call sites, `teachers/review.py`, admin views, admin cancel service,
  strike alert, lock order), OpenAPI/TS, docs, mutation table, full gates.

## Next command
`backend/`: `python -m pytest tests/test_t1b_bookable.py tests/test_t1b_review_actions.py tests/test_t1b_admin_cancel.py -q`
