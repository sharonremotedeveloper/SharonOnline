# Slice N1a - notifications app core (PRP 12.2 partial)

Branch `feature/n1a-notifications-core` (Claude). Plan: `docs/PHASE_11_12_EXECUTION_PLAN.md` §3.2, §4 (N1a row), §5-§7.
ERR block ERR-200..ERR-209. Migration `notifications/0001`. Mutation table: `docs/mutation/N1a.md`.

## Status
- Done: red tests (first commit).
- Remaining: app (models, registry, rendering, notify, delivery, alerts, retention, tasks), F0 alert sites, settings +
  beat/routes, golden snapshots, docs (NOTIFICATIONS.md §2, ADR-0002, RUNBOOK_NOTIFICATIONS.md), mutation run, full gate.
- Next command (from `backend/`): `venv python -m pytest tests/test_notifications_core.py tests/test_notifications_delivery.py tests/test_notifications_alerts.py tests/test_notifications_retention.py tests/test_notifications_templates.py tests/guards/test_guard_notification_kinds.py -q`

## Red run (first commit, tests only)
```
E   ModuleNotFoundError: No module named 'apps.notifications'
ERROR tests/test_notifications_core.py
ERROR tests/test_notifications_delivery.py
ERROR tests/test_notifications_alerts.py
ERROR tests/test_notifications_retention.py
ERROR tests/test_notifications_templates.py
ERROR tests/guards/test_guard_notification_kinds.py
6 errors in 0.73s
```
