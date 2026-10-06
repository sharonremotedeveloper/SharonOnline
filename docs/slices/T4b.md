# Slice T4b — Admin Tutor Vetting Studio UI

Branch: `feature/t4b-vetting-ui` · ERR block: 410 · dependency: T4a, T1b.

## Overview
Upgrades `/admin/teachers/vetting` to consume the T4a rubric scoring engine, review packet inspector, and ETag verification:
- `GET /api/v1/admin/teachers/<id>/review-packet/`
- `POST /api/v1/admin/teachers/<id>/approve/` (requires rubric scores $\ge 3$ per criterion, total $\ge 12/20$, and matching asset ETags)
- `POST /api/v1/admin/teachers/<id>/request-changes/` (requires reason + array of upload kinds to redo)
- `POST /api/v1/admin/teachers/<id>/reject/` (requires formal reason)
- `POST /api/v1/admin/teachers/<id>/start-review/` (moves submitted to in-review)

## Key Components
1. Interactive 4-criterion 1–5 rubric scoring widget.
2. Review packet inspector (audited media player, TEFL credentials, speed test metrics, power backup).
3. Request changes modal with specific asset kind checkboxes.
4. Unit tests in `frontend/test/vettingStudio.test.ts`.
