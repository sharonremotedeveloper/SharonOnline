# Slice T5a - tutor application funnel backend (Claude, 2026-10-05)

ERR block 420 (no new failures; the existing tests that relied on the staff lead-in were rewritten on purpose:
`test_t1b_review_actions.py`, `test_tutor_status_signoff.py`, `test_tutor_status_integration.py`, `test_t4a_vetting.py`).
Red first (`3505bb9`), green `b48ca14`. Migration `teachers/0014`. Gate: backend 3210, ruff, `makemigrations --check`, OpenAPI
`--validate --fail-on-warn`, TS regenerated, frontend lint/test/build.
**For Antigravity (T5b/T7):** build the funnel UI on `GET|PATCH /teachers/me/application/` and `POST .../submit/`; steps call T3
for uploads; the browser measures the speed test and sends the numbers; route `applied`/`changes_requested` tutors to `/teacher/apply`
using `tutor_status` from `/auth/me`; show `review_feedback` from `/teachers/me/` (T4a) when changes were requested.
