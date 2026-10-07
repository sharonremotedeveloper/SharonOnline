# Codex live-failure repair slice

**Branch:** `codex-repair`  
**Scope:** backend/domain repairs from `REPAIR_PLAN_LIVE_FAILURES_CODEX_ANTIGRAVITY.md`  
**Status:** backend implementation complete for this slice; focused and local non-provider gates verified. Full CI parity remains environment-blocked by nested Git execution and PostgreSQL-driver policy.

## RED evidence

- The canonical `backend/venv/Scripts/python.exe` is unusable because its `pyvenv.cfg` points at a missing Python 3.12 executable from an unrelated checkout.
- A fresh isolated `backend/.venv-codex` was created from the bundled Python 3.12.14 runtime and installed from `requirements-dev.txt`; the broken venv was left untouched.
- No external provider, database mutation, payment, booking, payout, refund, or credential action was performed.

## Changes in this slice

- Materials list/detail serializers now expose the frontend-required contract fields without inventing structured vocabulary/questions; list search is server-side.
- Student lesson serialization no longer emits the broken `freetalk-discussion` placeholder slug for an unlinked booking, and local date/time values use the student’s validated IANA timezone.
- Zoom and Video SDK attendance helpers support explicit bounds; authoritative credited attendance is clamped to the booking lesson window and lesson duration while raw audit rows preserve provider session intervals.
- Admin live-radar elapsed minutes are bounded to the lesson window instead of growing indefinitely from the original start time.
- Added regression tests covering those contracts and bounds.

## Remaining backend work

## Verification evidence

- Focused repair/integration suite: **76 passed**.
- Broader focused suite: **102 passed**.
- OpenAPI contract suite: **14 passed** after regenerating `docs/api/openapi.yaml`.
- `manage.py check`: passed.
- `manage.py makemigrations --check --dry-run`: passed, no changes detected.
- Ruff on the real source tree: passed.
- Local non-provider suite: **3381 passed, 26 deselected**, with Q0 nested-Git and deploy-check environment failures described below.

## Remaining verification blockers

- Q0 mutation tests cannot launch nested Git processes under the current Windows application-control sandbox (`WinError 5`).
- `test_refund_deploy_check` cannot load the PostgreSQL driver because the installed native extension is blocked by Windows application control; this is an environment/runtime gate, not a code assertion.
- Guard tests that create temporary source trees must run with a temp root outside the scanned backend tree and with a writable Windows temp directory; the current sandbox temp root returns access denied.
- Provider-backed Redis/Postgres, Google Calendar, R2, Zoom, payment, Resend, and Eskom verification remain intentionally unrun.
