# Mutation table - slice T4a (vetting rubric, asset integrity, review packet, tutor feedback, submitted alert)

Run 2026-10-05 with `backend/scripts/mutate.py` on a clean tree (branch `feature/t4a-vetting-backend`, commit `4ef49f9`), driven by
an argv-list script. Test file **T** = `tests/test_t4a_vetting.py`. Two mutants survived the first run (m3, m7) and were killed by
the tests added in `TestMutationSurvivors` (re-run of those two: see the last rows).

| # | File:line | Mutant | Killing test | Verdict |
| :-- | :--- | :--- | :--- | :--- |
| m1 | teachers/rubric.py:44 | rubric always accepted as present | T TestRubricOnApproval | KILLED |
| m2 | teachers/rubric.py:52 | `<` -> `<=` (minimum off by one) | T | KILLED |
| m3 | teachers/rubric.py:50 | bool accepted as a score (`isinstance`) | T `test_a_boolean_or_float_score_is_invalid...` | SURVIVED -> fixed |
| m4 | teachers/rubric.py:50 | upper bound exclusive | T | KILLED |
| m5 | teachers/rubric.py:73 | reviewed etags not compared with live | T TestReviewedAssetsMustMatch | KILLED |
| m6 | teachers/rubric.py:70 | missing `reviewed_assets` allowed | T | KILLED |
| m7 | teachers/rubric.py:66 | required kinds inverted | T `test_approval_succeeds_when_every_required...` | SURVIVED -> fixed |
| m8 | teachers/rubric.py:60 | replaced uploads counted as live | T | KILLED |
| m9 | teachers/review.py:101 | evidence on the first step instead of the decision | T TestReviewRounds | KILLED |
| m10 | teachers/review.py:125 | evidence validated on a no-op repeat | T TestReviewRounds | KILLED |
| m11 | teachers/vetting.py:94 | alert on any actor (staff lead-in alerts) | T TestSubmittedAlert | KILLED |
| m12 | teachers/vetting.py:94 | alert on the wrong status | T TestSubmittedAlert | KILLED |
| m13 | teachers/serializers.py:249 | rejection feedback hidden | T TestTutorFeedback | KILLED |
| m14 | teachers/serializers.py:251 | oldest instead of latest decision | T TestReviewRounds | KILLED |
| m15 | teachers/serializers.py:256 | scores leaked in place of requested changes | T TestTutorFeedback | KILLED |
| m16 | admin_api/teacher_packet_views.py:61 | packet lists replaced uploads | T TestReviewRounds | KILLED |
| m17 | admin_api/views.py:145 | legacy verify drops the rubric | T | KILLED |
| m18 | admin_api/teacher_review_views.py:110 | review endpoint drops the rubric | T | KILLED |
