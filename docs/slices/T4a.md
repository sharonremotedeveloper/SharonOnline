# Slice T4a - vetting backend (Claude, 2026-10-05)

Branch `feature/t4a-vetting-backend`; ERR block 300 (no new failures beyond the expected edits of the old approve tests).
Red first: commit `6de3365` (31 failing of 36); green `4ef49f9`. Gate: backend full suite, ruff, `makemigrations --check` (no
migration: the audit row already had `rubric` / `reviewed_assets` JSON columns), OpenAPI + TS regenerated.
Done: rubric, asset integrity, request-changes data, review packet, tutor feedback, submitted alert, settings + `.env.example`.
Existing tests that approve now send a rubric (`test_t1b_review_actions.py`, `test_admin_api.py`, `test_tutor_status_integration.py`).
Hand-off to **T4b (Antigravity)**: the admin vetting page must (1) load `review-packet`, (2) send `rubric` + `reviewed_assets`
on approve, (3) send `requested_changes` on request-changes; `PATCH verify` without a rubric is now 400. Hand-off to **N2c
(Codex)**: tutor mails for approved / changes_requested / rejected / suspended hook into `notify_status_change` (only outcome
statuses; the submitted alert is already there).
