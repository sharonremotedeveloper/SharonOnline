# Slice T1b - bookable predicate, call sites, admin review actions (working notes for a replacement agent)

Branch `feature/t1b-bookable-review` (from `develop` 47b69c9, fast-forwarded to db0a997 / ERR-192). Plan §3.1, PRP 11.1/11.4.
ERR block ERR-160..169 (used: 160, 161). Mutation table `docs/mutation/T1b.md`. Design: `docs/TUTOR_STATUS_MACHINE.md` §8-§10.

## Red run (first commit `14be9ce`, tests only, 2026-10-05)

```
pytest tests/test_t1b_bookable.py tests/test_t1b_review_actions.py tests/test_t1b_admin_cancel.py
       tests/test_tutor_status_machine.py tests/test_tutor_status_integration.py tests/test_tutor_status_signoff.py -q
130 failed, 165 passed, 1 skipped
```

## Done
- [x] `14be9ce` red tests
- [x] `a3d6d90` implementation (settings, bookable/operational, call sites, review.py, admin views + urls, admin_cancellation,
      strike alert, review lock order, OpenAPI + TS, frontend type widening)
- [x] `d9250d7` mutation survivors killed
- [x] docs (status machine, cancellation, settlement, roadmap, PRP, plan launch checklist), ERR-160/161, mutation table

## Remaining
- nothing for T1b. Integrator: run `npm run build` (not possible through the node_modules junction, ERR-155), the Postgres CI job
  (new deadlock test), re-regenerate OpenAPI/TS after merging T1c.

## Next command
`backend/`: `python -m pytest -q` (expect 2491+ passed, 13 skipped).
