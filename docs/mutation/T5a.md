# Mutation table - slice T5a (application funnel)

Run 2026-10-05 with `backend/scripts/mutate.py` on a clean tree (branch `feature/t4a-vetting-backend`). Test file **T** =
`tests/test_t5a_application.py`. a2, a6, a9, a10, a11 survived the first run and were killed by `TestMutationSurvivors`
(re-run: all KILLED). a15 (a redundant `role` check) was deleted instead of tested; a16 is an equivalent mutant (adding `applied`
to the start-review sources is still refused by the state machine's own edge table: defence in depth).

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| a1 | application.py:79 | slow only if BOTH below the minimum | T `test_a_slow_connection...` | KILLED |
| a2 | application.py:79 | minimum exclusive | T `test_a_connection_exactly_at_the_minimum_passes` | SURVIVED -> fixed |
| a3 | application.py:81 | stale test counts, fresh does not | T `test_a_stale_speed_test...` | KILLED |
| a4 | application.py:67 | replaced uploads count | T | KILLED |
| a5 | application.py:68 | missing-kind logic inverted | T | KILLED |
| a6 | application.py:101 | can_submit ignores the status | T `test_a_sent_application_cannot_be_submitted_again...` | SURVIVED -> fixed |
| a7 | application.py:110 | edit allowed after sending | T `test_the_application_is_locked...` | KILLED |
| a8 | application.py:130 | any status may submit | T `test_other_statuses_cannot_submit` | KILLED |
| a9 | application.py:134 | incomplete application accepted | T TestSubmit | SURVIVED (first pattern not found) -> re-run KILLED |
| a10 | application.py:117 | power-backup stamp moved | T `test_confirmation_stamps_are_never_moved` | SURVIVED -> fixed |
| a11 | application.py:119 | declaration stamp moved | T same | SURVIVED -> fixed |
| a12 | application.py:137 | submit by a system actor (no tutor, no staff alert) | T TestSubmit | KILLED |
| a13 | application_views.py:64 | unknown / service-owned keys accepted | T `test_unknown_or_service_owned...` | KILLED |
| a14 | application_views.py:71 | `false` confirmation accepted | T | KILLED |
| a15 | application_views.py:83 | role check removed | redundant (profile presence is the check): deleted | n/a |
| a16 | review.py:43 | `applied` accepted as a start-review source | refused by the status machine anyway | EQUIVALENT |
| a17 | admin_api/views.py:114 | `applied` back in the pending queue | T TestStaffCannotReceive... | KILLED |
