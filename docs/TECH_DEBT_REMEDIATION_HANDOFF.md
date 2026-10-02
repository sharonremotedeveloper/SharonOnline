# Technical-debt remediation handoff

This is the cross-agent handoff for the eight approved Sharon Online remediation batches. Update it at every batch boundary. External providers remain out of scope until the mandatory account check confirms `sharonremotedeveloper@gmail.com` and Anesu approves the specific sandbox action.

## Current state

- Integration branch: `remediation/tech-debt`
- Active branch: `fix/batch-1-containment-locks`
- Isolated worktree: `C:\Dev\Active Projects\Notion\sharon-remediation`
- Shared checkout was deliberately left unchanged because it contains Claude's uncommitted Zoom attendance work.

## Batch 1 - containment and ownership-safe locks

Implemented:

- Removed fabricated admin telemetry floors and payout-preview rows.
- Made payout execution a non-mutating `503 payout_execution_disabled` response and disabled the UI action.
- Added `Booking.slot_lock_token`; production reservations use a unique UUID token persisted in Redis and the booking row.
- Added atomic compare-and-delete and compare-and-expire primitives for Redis, with a synchronized local-memory test fallback.
- Added unique ownership tokens to periodic-task locks; stale workers cannot release successor locks.
- Added stale-release, stale-renewal, successor-ownership, and non-mutating payout tests.

Verification:

- `manage.py makemigrations --check --dry-run`: no changes.
- `manage.py check`: no issues.
- Focused backend suite: 74 passed.
- Frontend tests: 88 passed.
- Next.js production build: passed (the existing homepage catches an unavailable local API during static generation).

Remaining gate before merge:

- Complete backend regression: 679 passed in 57.20s.
- `tests/integration/test_redis_lock_races.py` is the real-backend suite and requires `REDIS_TEST_URL`. This workstation has neither Docker nor `redis-server`, so execution is pending the required Redis 7 CI service in Batch 8; isolated unit tests continue using injected local memory.

## Parallel-work warning

Claude's shared checkout currently contains uncommitted Batch 4-related attendance identity changes, including a migration numbered `0010`. Reconcile that work only at the Batch 4 boundary and renumber migrations if necessary; do not overwrite or clean the shared checkout.
