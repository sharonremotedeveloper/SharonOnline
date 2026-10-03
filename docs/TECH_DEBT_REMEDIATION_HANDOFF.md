# Technical-debt remediation handoff

This is the cross-agent handoff for the eight approved Sharon Online remediation batches. Update it at every batch boundary. External providers remain out of scope until the mandatory account check confirms `sharonremotedeveloper@gmail.com` and Anesu approves the specific sandbox action.

> **Update 2026-10-03:** reviewed by Claude and merged into `develop` together with Tasks 9.5-9.8; see [`REMEDIATION_INTEGRATION.md`](REMEDIATION_INTEGRATION.md) for the review, the reconciliation decisions and follow-ups.

## Current state

- Integration branch: `remediation/tech-debt`
- Active branch: `remediation/tech-debt` (all eight local batch branches merged)
- Isolated worktree: `C:\Dev\Active Projects\Notion\sharon-remediation`
- Shared checkout was deliberately left unchanged. Claude's Zoom attendance work was imported from commit `2181dbd` and augmented on this isolated branch.

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

Deferred environment gate:

- Complete backend regression: 679 passed in 57.20s.
- `tests/integration/test_redis_lock_races.py` is the real-backend suite and requires `REDIS_TEST_URL`. This workstation has neither Docker nor `redis-server`, so execution is pending the required Redis 7 CI service in Batch 8; isolated unit tests continue using injected local memory.

## Batch 2 - funding provenance, credit catalog, and checkout

Implemented:

- Added immutable booking-funding snapshots, settlement anomalies, database-backed launch credit packs, credit purchases, and immutable wallet entries.
- Backfilled legacy credit balances as opening wallet entries and existing successful lesson payments as booking funding.
- Enforced that each payment transaction targets exactly one booking or one credit purchase.
- Removed current-list-price settlement fallbacks. Missing funding now stops settlement and creates a durable anomaly.
- Added row-locked oldest-credit redemption, actual captured per-credit valuation for discounted packs, immutable wallet history, booking confirmation, owned-lock release, and post-commit fulfillment.
- Extended checkout initialization to accept exactly one server-authoritative booking or credit-pack target. Added pack catalog and purchase-status APIs.
- Made gateway webhooks authoritative for payment success. The checkout and wallet UIs poll server state and never call the unsafe client confirmation endpoint.
- Updated operational restitution to issue new immutable wallet-credit lots valued from the booking funding snapshot.
- Regenerated OpenAPI and frontend API types with the new contracts.

Verification:

- Focused Batch 2 suite: 9 passed; four funding-invariant legacy regressions: 4 passed.
- Complete backend regression: 688 passed, 2 Redis integration tests skipped pending Batch 8 CI infrastructure.
- Frontend tests: 88 passed.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes.
- Next.js production build: passed (the existing homepage catches an unavailable local API during static generation).

External-action boundary:

- No gateway, email, hosting, database-cloud, or other external-provider action was performed in this batch. Sandbox verification remains gated by account confirmation and Anesu's explicit approval.

## Parallel-work reconciliation

Claude's `feature/task-9-8-zoom-attendance` commit `2181dbd` was cherry-picked at the Batch 4 boundary. Its bookings migration was renumbered from `0010` to `0011` behind the Batch 1 lock-token migration; the expanded identity migration is `0012`. The shared checkout was not modified.

## Batch 3 - payment and ledger hardening

Implemented:

- Persisted capture-time FX rate/source and provider-fee snapshots on payment transactions; ledger rows retain the valuation source.
- Gateway fee data now posts to account 5030 while preserving a balanced gross customer liability and net gateway asset.
- Enforced balancing independently in transaction currency and ZAR, and rejected mixed-currency journals or non-USD currency without an explicit FX snapshot.
- Replaced age-based transaction failure with provider-aware reconciliation. Only an authoritative failed provider state marks a transaction failed; inconclusive PayFast/PayPal state stays initialized with a durable unresolved anomaly.
- Added a PostgreSQL update/delete rejection trigger for the append-only ledger, complementing application-level guards.
- Added durable post-payment fulfillment dispatch state, component progress, retryable error details, and a periodic retry dispatcher. Queue state is committed before dispatch so a fast worker cannot be overwritten by its producer.

Verification:

- Focused payment/ledger/fulfillment/lifecycle suite: 103 passed, 1 PostgreSQL-only test skipped.
- Complete backend regression: 693 passed, 3 environment-specific tests skipped (2 Redis and 1 PostgreSQL trigger test).
- Frontend tests: 88 passed; Next.js production build passed.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes.
- PostgreSQL trigger execution remains a required Batch 8 CI service gate; the migration safely no-ops on SQLite.

External-action boundary:

- Gateway reconciliation logic was verified with injected provider results only. No PayFast, PayPal, hosting, or other external-provider request was made.

## Batch 4 - Zoom attendance correctness

Implemented:

- Removed the unknown-participant-to-student fallback and centralized identity classification as explicit `teacher`, `student`, or `unknown`.
- Persisted participant ID, registrant ID, reported email, host ID, event IDs, session ID, match method, raw payload, and event timestamps.
- Made join/leave handling idempotent across retries, reconnects, reused participant IDs, and leave-before-join delivery.
- Used Zoom join/leave/start/end timestamps; malformed timestamps fall back visibly without failing webhook ingestion.
- Unknown participants remain visible in Django administration but cannot start a booking, satisfy attendance, prevent a no-show, or authorize settlement.
- Removed participant-count inference from the active probe. Only an authoritative started meeting can corroborate tutor presence.
- Applied the five-minute disconnect grace to T+10 presence and merged short reconnect gaps into completion/settlement attendance minutes.
- Imported Claude's late-telemetry dispute guard, host-start handling, malformed-payload hardening, and explicit Zoom API errors.

Verification:

- Focused Zoom/no-show/settlement suite: 91 passed.
- Complete backend regression: 734 passed, 3 infrastructure-specific tests skipped.
- Frontend tests: 88 passed; Next.js production build passed.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes.

External-action boundary:

- All Zoom behavior was verified with signed local webhook fixtures and injected client responses. No Zoom account, API, or sandbox was accessed.

## Batch 5 - profiles, support, and API contracts

Implemented:

- Added one-to-one student profiles and backfilled every existing student with blank learning fields rather than invented defaults.
- Replaced the ad-hoc profile GET/PATCH path with one serializer that persists learning goals and validates full name, ISO country, IANA timezone, and field lengths.
- Added durable support inquiries, a public throttled submission endpoint, administration inbox, and post-commit Resend notification with retryable delivery state.
- Regenerated OpenAPI and frontend types. Booking status now derives from all backend states, conditional student e-mail is optional, and profile/student-wallet contracts are schema-derived.
- Added a generated-type drift command and an API-contract CI workflow.
- Corrected tutor dashboard day/month boundaries to use the authenticated viewer timezone and server pagination counts.

Verification:

- Focused profile/support/booking/contract suite: 74 passed.
- Complete backend regression: 749 passed, 3 infrastructure-specific tests skipped.
- Frontend tests: 90 passed; generated-contract check and Next.js production build passed.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes.

External-action boundary:

- Resend behavior was verified with an injected local sender only. No Resend account, provider API, remote Git, or cloud service was accessed.

## Batch 6 - tutor wallet and protected payout settings

Implemented:

- Added a ledger-derived tutor wallet from account 2020, including pending funded escrow, cleared payable balance, capture-time FX context, and real transaction history.
- Added one payout account per tutor with a versioned Fernet keyring. Full account-holder, account-number, bank, branch, account-type, and optional identification data remain encrypted; only account-number last-four metadata is plaintext.
- Added masked payout-settings GET and password-reauthenticated create/update. Responses and logs never include full account or identification numbers.
- Validated the supported South African bank catalog, exact universal branch codes, account-number format, and account type; tutor permissions prevent cross-account access.
- Restricted admin payout previews to ledger-derived positive balances for verified tutors with configured payout accounts. Payout execution remains disabled and non-mutating.
- Regenerated OpenAPI/frontend types and made the tutor wallet and payout UI consume those generated contracts. Removed remaining fabricated financial fallback rows and the fake successful payout execution result.

Verification:

- Focused payout/wallet/admin/settings/contract suite: 67 passed.
- Complete backend regression: 764 passed, 3 infrastructure-specific tests skipped.
- Frontend tests: 90 passed; generated-contract check and Next.js production build passed.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes.

External-action boundary:

- Encryption, password reauthentication, masking, rotation, and wallet behavior were verified locally only. No banking rail, provider, remote Git, cloud database, or other external service was accessed. Payout execution remains disabled.

## Batch 7 - Eskom Power Guard

Implemented:

- Added an injectable EskomSePush client with bounded timeouts, structured provider/quota errors, configurable base URL, and strict response normalization.
- Replaced hardcoded Stage 2 behavior with durable per-area provider status, outage windows, retrieval timestamps, fresh/stale state, and an explicit unavailable response when no evidence exists. Real stage zero is preserved.
- Added `has_lte_failover` and an authenticated tutor-only power-backup PATCH endpoint; the UI can only update the current tutor's two backup flags.
- Added cached-status GET with generated frontend contracts. Stale/quota/error data is visibly labelled with the original retrieval time.
- Added outage-window overlap detection for lessons in the next four hours, combined inverter/LTE exemption, durable idempotent notification attempts, and retryable delivery through the existing email infrastructure.
- Student outage reports now require a fresh active provider outage for the tutor area. Tutor/staff confirmation remains accepted only inside the existing booking-time window.
- Removed fabricated stage fallback and corrected frontend claims that implied unimplemented slot blocking, bonus credits, or live request-path provider calls.

Verification:

- Focused Eskom/outage/task/settings suite: 220 passed.
- Complete backend regression: 774 passed, 3 infrastructure-specific tests skipped.
- Frontend tests: 90 passed; generated-contract check and Next.js production build passed.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes.

External-action boundary:

- Provider behavior was tested only with injected local clients and responses. No EskomSePush account, API, Resend provider, remote Git, cloud database, or other external service was accessed.

## Batch 8 - quality gates and final stabilization

Implemented:

- Added a committed non-interactive ESLint configuration and resolved every reported warning; lint now exits cleanly without prompting.
- Added required GitHub Actions jobs for Django checks, migration drift, the backend suite, frontend tests, ESLint, generated OpenAPI drift, production build, PostgreSQL ledger-trigger tests, and Redis 7 race tests.
- Provisioned disposable PostgreSQL 16 and Redis 7 service containers in CI so the three locally skipped infrastructure tests execute against their real backends.
- Removed the unused frontend payout-execution client action and verified no fabricated payout totals/batch IDs or hardcoded Eskom stages remain in application code.
- Re-ran all local gates after the final lint fixes and validated the workflow files as parseable YAML.

Verification:

- Complete local backend regression: 774 passed, 3 infrastructure tests skipped locally and assigned to required CI service jobs.
- Frontend tests: 90 passed.
- ESLint: zero warnings/errors.
- Generated-contract drift: passed.
- Next.js production build: passed (the marketing homepage intentionally renders an empty tutor state when no local API is running).
- `manage.py check`: no issues; migration drift: none.
- Workflow YAML: parsed successfully.

Outstanding gated evidence:

- The PostgreSQL and Redis jobs require the first CI run because this workstation has no local Docker/Redis runtime.
- PayFast, PayPal, Resend, and EskomSePush sandbox verification was not performed. Per the project rule, each remains blocked until the active account is confirmed as `sharonremotedeveloper@gmail.com` and Anesu explicitly approves that provider action.
- No remote branch, pull request, deploy, provider API, or cloud database action was performed.
