# Codex remediation branch: review and integration (2026-10-03)

Codex worked in an isolated worktree (`C:\Dev\Active Projects\Notion\sharon-remediation`, branch `remediation/tech-debt`, eight batches, 128 files, +7,000 lines; its own log is `TECH_DEBT_REMEDIATION_HANDOFF.md`) while I built Tasks 9.5-9.8. It was never merged because it forked before 9.6. This page records my review and how the two lines of work were reconciled.

## Verdict

**Sound, and worth keeping. Merged.** I read the security-sensitive code, re-ran its suite (774 passed, 3 environment skips, as claimed), and then ran everything together after integrating (backend **980 passed, 3 skipped**; frontend 95 tests, zero-warning ESLint, API-type drift check and `next build` clean).

| Batch | What it does | Review |
| :--- | :--- | :--- |
| 1 Containment + locks | Fake admin numbers removed; payout execution disabled (503, non-mutating); slot and task locks carry a unique token and use atomic compare-and-delete / compare-and-expire in Redis | Correct and conservative. The Lua scripts compare then mutate in one step. Real-Redis race tests are gated to CI. |
| 2 Funding, credit packs, checkout | Immutable `BookingFunding` (what a lesson was paid with, in what currency, at what FX), `CreditPack` catalog (USD/ZAR/EUR/JPY), `CreditPurchase`, immutable `CreditWalletEntry` history, row-locked credit redemption, no list-price fallbacks | Good design and the right invariant: **settlement never guesses from the current list price**; missing provenance stops and records a `SettlementAnomaly`. Backfills legacy rows instead of inventing data. |
| 3 Payment + ledger hardening | FX rate/source and provider-fee snapshots, journals balance per currency and in ZAR, provider-aware reconciliation (only an authoritative failed state fails a transaction), Postgres trigger making the ledger append-only, durable retryable fulfilment dispatch | Good. EUR/JPY are deliberately rejected until an approved FX source exists (our open decision). |
| 4 Zoom attendance | Builds on my 9.8 (cherry-picked) and adds registrant ids, event ids, 5-minute disconnect grace merged into attendance minutes, and drops "participant count > 0 means the tutor is here" from the probe | A strict superset: my own 9.8 test file passes unchanged against it. |
| 5 Profiles, support, contracts | One-to-one `StudentProfile`, validated profile PATCH, support inquiries, schema-derived TS types, API-type drift CI | Fine. |
| 6 Tutor wallet + payout settings | Ledger-derived tutor wallet; versioned Fernet keyring for bank details; masked reads; password re-auth on change; SA bank/branch validation; production guard validates the keyring | Good. **One gap fixed in integration:** the password re-check was not rate-limited (a stolen session could guess it at 300/min); now 5 changes per hour. Follow-ups below. |
| 7 Eskom Power Guard | EskomSePush client (timeouts, quota), durable per-area status, outage windows, tutor backup flags, 4-hour warnings, stale/fresh labelling | Fine; needs a real API key to verify. |
| 8 Quality gates | ESLint config, GitHub Actions: Django checks, migration drift, backend suite, frontend tests/lint/build, API-type drift, Postgres 16 and Redis 7 service jobs | Solid base (Task 13.3). Missing: `check --deploy`, `pip-audit` / `npm audit`, branch protection. |

## What had to be reconciled (and the decision taken)

| Area | Conflict | Resolution |
| :--- | :--- | :--- |
| Credits | Both sides had made credits into lots. Codex added immutable wallet history, packs and funding value (`unit_amount`); I added expiry, soonest-expiry-first spending and an expiry job. | One model: Codex's lot + wallet history **plus** my `source`, `expires_at`, `expired_credits`, `expired_at`. My `unit_value` became their `unit_amount`. `grant_credit()` has one signature; redemption and `spend_credit()` use soonest-expiry-first and ignore expired lots; the expiry job also writes an `expiry` wallet entry. |
| Refunds | I refunded a captured payment through the gateway and fell back to the list price when nothing was captured; Codex forbids list-price fallbacks. | Adopted Codex's rule. `request_refund` reads the booking's `BookingFunding`: **gateway-funded -> gateway refund** (ledger 2050); **credit-funded -> the credit is restored as a new lot**; **no funding -> `MissingFunding`**, anomaly recorded, nothing guessed. Cancelling such a booking is refused (409 `funding_unavailable`) and tells finance, rather than refunding from the price. |
| Student outage reports | I had made outage reports tutor-only; Codex let a student report only when the provider confirms an outage in the tutor's area. | **Combined:** the tutor or staff can always report; a student only with provider-confirmed evidence (409 `outage_unconfirmed` otherwise). This keeps the abuse protection and gives students a route now that real Eskom data exists. The refund goes through the gateway (D-6). |
| Tutor no-show, memo SLA, dispute, DEF-501 | Both rewrote the grant calls. | Funding-based amounts (Codex) + my gateway refund, bonus lot and windowed strikes. DEF-501 keeps Codex's idempotent grants. |
| Zoom attendance | Both implemented 9.8. | Codex's version (superset). My tests stay as `tests/test_zoom_attendance_9_8.py`. |
| Migrations | Both sides numbered new migrations from the same fork point (bookings 0010/0011, payments 0008, teachers 0005). | Dropped mine and regenerated on top of Codex's chain: bookings `0013`, payments `0013` + `0014` (30-day expiry backfill for existing credits), teachers `0006`. Nothing had been deployed. |
| Error IDs | Both sides used ERR-018 onwards for different things. | Codex's kept; mine renumbered to ERR-026 (Zoom attendance), ERR-027 (refunds, credits, strikes), ERR-028 (payout-settings throttle) and ERR-029 (post-merge audit). |
| OpenAPI enum names | Booking and refund `status` enums collided. | `ENUM_NAME_OVERRIDES` (`BookingStatusEnum`, `RefundStatusEnum`, `RefundReasonEnum`); frontend types follow. |
| Generated files | Both regenerated them. | Regenerated from the merged code. |

## Follow-ups from the review (none block the merge)

1. **Payout settings:** password re-auth only. The plan (Task 11.7) also wanted a one-time code, and a notification e-mail to the tutor whenever bank details change (the standard account-takeover defence). Add both before payouts go live.
2. **A lesson paid in EUR or JPY cannot be settled yet** (no approved FX source). Same open decision as Phase 10 item 6.
3. **CI:** add `manage.py check --deploy`, `pip-audit` / `npm audit`, Dependabot, and (Anesu) branch protection on `develop` / `main`. The Postgres and Redis jobs have never run: the first run may need fixes.
4. `TECH_DEBT_REMEDIATION_HANDOFF.md` says "external actions out of scope until Anesu approves": still true. Nothing here touched a provider.
5. Codex's no-show path stops with the booking already marked `teacher_no_show` when funding is missing (it logs and records an anomaly). That is safe, and finance sees it, but an admin view of open `SettlementAnomaly` rows is needed (Phase 15 admin).

## Post-merge consistency audit (same day)

After merging I audited the result for places where the two lines of work still followed different rules. Findings, all fixed and covered by tests (ERR-029):

| Finding | Fix |
| :--- | :--- |
| `record_student_refund_entry` and `record_outage_refund_entry` had no production callers any more but still booked refunds to the *wallet* (the old rule) | Deleted. `refunds.request_refund` is the only place a refund is booked. The dispute helper's `full_refund_student` branch (also wallet, and unreachable) now raises, pointing to the refund service. Ledger tests moved onto the live path. |
| Admin escrow view listed only the old statuses, so lessons cancelled with the three new statuses were invisible to finance | Added them; test checks refunded / kept-fee cancellations show correctly |
| Wallet history contract did not list the new `expiry` entry type | Added to the schema; OpenAPI and TS types regenerated |
| Reschedule locked the new slot with the student id; Codex's rule is a unique ownership token (also stored on the booking) | Reschedule now uses `new_slot_lock_token()`; test asserts the token |

Verified clean: no conflict markers or unmerged index entries; migrations apply on a **brand-new database** and on a database built at the **pre-merge schema with legacy rows** (booking, captured payment, partly spent credit pack): the booking funding and opening wallet entry are backfilled, the legacy credits get a 30-day expiry and stay spendable, nothing is lost. Attendance reads outside the Zoom service only use rows with an identified role, so unrecognised participants cannot affect anything.

## First real CI run (2026-10-03)

`backend`, `frontend` and `postgres-ledger` (the append-only ledger trigger on real PostgreSQL 16) **passed** on their first run. `redis-races` **failed**, and it found a genuine production bug rather than a test problem (ERR-030): the lock scripts compared the plain token against Django's pickled value, so on a real Redis the rightful owner could never extend or release a lock. That would have blocked checkout for every payment. Fixed in `common/cache_locks.py`, with a byte-exact Redis stand-in test that reproduces it and real-Redis positive controls; the next CI run is the final proof.

## CI completion (2026-10-03)

| Gate | What it enforces |
| :--- | :--- |
| `backend` | `check`, migration drift, **`check --deploy` against the production settings** (`scripts/check_deploy.py`: throwaway valid values, proven to fail on unsafe settings), full test suite |
| `frontend` | tests, zero-warning ESLint, generated API-type drift, `next build` |
| `dependency-audit` | `pip-audit --strict` (**blocking**); `npm audit` for production deps (informational until the Next.js upgrade, Task 8.9, because the open advisories are in Next 14 itself) |
| `postgres-ledger` | **migrates a fresh PostgreSQL database from zero**, then the Postgres-only tests (append-only ledger trigger) |
| `redis-races` | real Redis 7 lock races and owner checks |
| `api-contract` | schema + TS types cannot drift |

Dependabot (weekly, grouped) covers pip, npm and GitHub Actions and proposes **minor and patch updates only**: a major version is a deliberate migration (the first auto-proposed batch of majors failed CI), so Next.js 15/16 + React 19 + `eslint-config-next` 16 stay Task 8.9, Tailwind 4 and `@types/node` majors are done by hand when wanted. Dependencies adopted after testing: icalendar 7, drf-spectacular 0.30, celery 5.6.3, django-filter 26, dj-database-url 3, lucide-react 1.49, date-fns 4.4. **Left for Anesu:** turn these jobs into *required* checks (Settings -> Branches -> branch protection for `develop` and `main`).
