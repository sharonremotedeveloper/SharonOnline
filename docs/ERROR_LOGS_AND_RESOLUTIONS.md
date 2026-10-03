# Error Logs & Resolution History Ledger

This document serves as the **authoritative system log** for tracking bugs, runtime exceptions, build failures, and architectural issues encountered during development by AI coding agents (**Claude**, **Codex**, **Antigravity/Gemini**) and human developers (**Anesu MUPESA**).

---

## 🛠️ Error Logging Protocol

Whenever an error, test breakage, build failure, or unexpected API behavior occurs:

1. **Assign Error ID**: Assign a sequential ID (`ERR-001`, `ERR-002`, ...).
2. **Log Details**: Record exact timestamp, component (`backend`, `frontend`, `database`, `redis`), severity, error message, and stack trace.
3. **Analyze Root Cause**: Identify why the underlying contract broke (never mask symptoms or suppress exceptions silently).
4. **Document Fix Diff**: Include the exact code snippet or configuration change that resolved the issue.
5. **Verify**: Record the verification command and output confirming clean resolution.

---

## 📋 Historical Error & Resolution Ledger

| Error ID | Date | Component | Severity | Log / Stack Trace Summary | Root Cause Analysis | Fix Summary & Code Diff | Status | Logged By |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ERR-001` | 2026-09-25 | Backend (Pytest) | `High` | `redis.exceptions.ConnectionError: Error 10061 connecting to 127.0.0.1:6379...` | Pytest suite attempted to connect to local host Redis server when running outside Docker container. | Updated `conftest.py` to override cache settings with `LocMemCache` and `CELERY_TASK_ALWAYS_EAGER = True`. | `RESOLVED` | Antigravity |
| `ERR-002` | 2026-09-25 | Notion Workspace | `Medium` | `This page couldn't be found. You may not have access...` | Renamed/moved subpages left stale hardcoded URLs in Notion table. | Replaced obsolete markdown content with direct links to published Master Hub. | `RESOLVED` | Antigravity |
| `ERR-003` | 2026-09-25 | Notion API | `Low` | `This page's ancestor is in the trash...` | Moving `Team Space` parent page created trashed ancestor flag on child pages. | Called `API-patch-page` with `in_trash: false` to restore pages to active status. | `RESOLVED` | Antigravity |
| `ERR-004` | 2026-10-02 | Backend (PostgreSQL) | `High` | `psycopg2.errors.FeatureNotSupported: FOR UPDATE cannot be applied to the nullable side of an outer join` | In PostgreSQL, `select_for_update` on a query containing reverse-relation `.exclude(dispute__status=OPEN)` generates a SQL outer join which cannot be row-locked. | Replaced reverse-relation filter with subquery `exclude(id__in=DisputeCase...values_list('booking_id'))` and added `of=('self',)` locking only `bookings_booking`. | `RESOLVED` | Antigravity |
| `ERR-005` | 2026-10-02 | Frontend (Docker SSR) | `Medium` | `TypeError: fetch failed [cause]: AggregateError [ECONNREFUSED] 127.0.0.1:8000` | During Docker staging SSR, Next.js server-side fetches targeted `localhost:8000` instead of the Docker internal bridge network `backend:8000`. | Added `INTERNAL_API_URL=http://backend:8000/api/v1` to `docker-compose.yml` and dual-environment `API_BASE` resolution in `src/lib/api.ts`. | `RESOLVED` | Antigravity |
| `ERR-006` | 2026-10-02 | Backend (local dev) | `High` | `redis.exceptions.ConnectionError: Error 10061 connecting to localhost:6379` on every API request (`/api/v1/teachers/` -> 500) | `local.py` defaulted `REDIS_URL` to `redis://localhost:6379/0`, so with no Redis the cache was Redis; since Phase 7A throttling touches the cache on EVERY request. Default is now empty -> LocMem cache + `memory://` Celery broker; Docker/Redis opts in via `REDIS_URL`. |
| `ERR-007` | 2026-10-02 | Frontend (runtime) | `High` | `TypeError: tutor.rating_avg.toFixed is not a function` on `/student/book/[tutorId]` | Django `DecimalField`s (`rating_avg`, `price_per_25min_usd`) serialise as STRINGS; the page was only ever exercised against fabricated numeric fixtures. Fixed at the source: `normalizeTutor()` in `lib/api.ts` coerces them once. |
| `ERR-008` | 2026-10-02 | Frontend/Backend contract | `High` | `TypeError: Cannot read properties of undefined (reading 'toFixed')` on `/student/checkout/[bookingId]` | `BookingDetail` (frontend type) required `price_usd`, `price_zar`, `lock_expires_at`, `booking_reference`, local times, etc. that `BookingDetailSerializer` never returned; masked by the fake-booking fallback. Serializer now supplies the full contract (host `zoom_start_url` only to the booking's tutor; student email only to the student) and is pinned by `tests/test_booking_detail.py`. |
| `ERR-009` | 2026-10-02 | Frontend (security, pre-release) | `Critical` | Response header `x-middleware-set-cookie: sharon_refresh=eyJ...` on `/api/session/login` (also in the PRODUCTION build) | Setting cookies with Next's `NextResponse.cookies.set()` also mirrors them into the internal `x-middleware-set-cookie` response header, which browser JS can read - it would have exposed the refresh token to any XSS and defeated HttpOnly. Found by inspecting raw headers of a live production build before release. Fix: cookies are serialised by our own tested `serializeCookie()` and appended as plain `Set-Cookie`; `noStore()` also strips the header; verified 0 leaks on a rebuilt production server. |
| `ERR-010` | 2026-10-02 | Backend (`/auth/me/`) | `High` | `TypeError: 'str' object is not callable` -> HTTP 500 on `GET /auth/me/` for tutors (caught by `test_api_contract.py` before release) | New `avatar_url` field called `TeacherProfile.resolved_avatar_url()`, but it is a `@property`, not a method. | Use the property (`profile.resolved_avatar_url`). Contract tests now cover student/teacher/admin payloads. | Resolved | Claude |
| `ERR-011` | 2026-10-02 | Frontend (deploy safety) | `Medium` | Production config fail-fast threw inside `instrumentation.ts` but `next start` kept running and answered every request with 500 (exit code 0/timeout, no failed deploy signal) | Next 14 logs `Failed to prepare server` for a throwing instrumentation hook yet leaves the process alive. | `lib/server/boot.ts` (Node-only) logs the problems and calls `process.exit(1)`; verified `next start` with empty env exits 1. | Resolved | Claude |
| `ERR-012` | 2026-10-02 | Backend (admin disputes) | `High` | Found by the new state-machine test: after one `full_refund_student` / `split_50_50` resolution a student with no bundle held **2** credits (`CreditBundle 2/1`) | `ResolveDisputeView` created the bundle with `remaining_credits=1` as the get_or_create default and then did `+= 1`. The old test asserted `>= 1`, which hid it. | `_grant_credit()` creates the bundle at 0 and adds exactly 1 (total and remaining); test now asserts `== 1`. | Resolved | Claude |
| `ERR-013` | 2026-10-02 | Backend (payments settlement) | `Critical` | Found while reviewing escrow paths for Task 9.7: after an admin resolved a dispute as *release tutor* / *50-50 split* the tutor was credited, then credited **again** by `release_cleared_escrow_task` 24 h later (escrow liability driven negative) | Arbitration posted its own ledger entries but never set `escrow_cleared_at`; the release job selected the now-`completed` booking again. Student no-shows were never released at all (status missing from the filter) and the outage branch was dead code. | Settlement rule in `payments/services/settlement.py`: the job excludes any booking with a prior settlement ledger entry; arbitration marks booking/transaction cleared; `student_no_show` is releasable on tutor presence. Tests: `test_settlement_paths.py::TestNoDoubleSettlement`. | Resolved | Claude |
| `ERR-014` | 2026-10-02 | Backend (credits) | `High` | Latent: `MultipleObjectsReturned` from `CreditBundle.objects.get_or_create(user=...)` for any student owning 2+ bundles (dispute resolution, tutor no-show, memo forfeiture, DEF-501 handling all 500) | Six hand-rolled copies assumed one bundle per user. | `payments/services/credits.py::grant_credit()` (latest bundle, F() updates, keeps `remaining <= total`) used everywhere; `TestGrantCredit` covers multi-bundle users. | Resolved | Claude |
| `ERR-015` | 2026-10-02 | Backend/Frontend (lesson memo) | `High` | Tutor-typed **grammar notes were silently discarded** (UI sends `grammar_notes`; the model had no field) and the student's memo showed the *homework* text as "grammar notes", falling back to an invented sentence ("Focus on natural conversational phrasing."); flashcard errors were swallowed (`except Exception: pass`); re-submitting a memo reset every flashcard to *new* (progress wiped) | `SubmitMemoView` read raw `request.data` with no serializer; `srs.get_memo` mapped the wrong field and fabricated a fallback. | `grammar_notes` field + migration, `LessonMemoInputSerializer` (limits, NUL/shape checks, per-word normalisation), `get_or_create` flashcards inside the memo transaction, student serializer returns the real field. `tests/test_memo_endpoint.py`. | Resolved | Claude |
| `ERR-016` | 2026-10-02 | Backend (lesson memo / escrow) | `Medium` | A memo could be posted for an `in_progress` lesson (and by staff impersonating the tutor), moving it to `completed` before the end-of-lesson attendance evaluation ever ran, so the <20-minute dispute path was skipped | Memo allowed-state set included `confirmed`/`in_progress`; the staff override was copied from the permission checks. | Only the lesson's tutor, only `completed_pending_memo` / `completed` / `completed_memo_forfeited`; the in_progress -> completed edge is removed from the state machine. | Resolved | Claude |
| `ERR-017` | 2026-10-02 | Backend (lesson reviews, privacy) | `High` | The student's **private written review was returned to the tutor** it was about (`student_review` in `GET /bookings/<id>/`); two divergent review endpoints; a lesson could be reviewed any number of times and in any state (rating could be changed at will, or posted for an unpaid/cancelled booking); `tags` the UI sent were discarded and every rated lesson showed an invented tag list; the tutor's average was computed in Python and written back with a whole-row `teacher.save()` from a stale copy (could undo a concurrent deactivation/strike) | Review code was duplicated in `bookings/views.py` and `srs/views.py` with no state/ownership rules; `BookingDetailSerializer` exposed the column to every viewer. | `bookings/services/reviews.py` (once-only, finished lessons only, tutor-row lock, DB `Avg`/`Count`, 2-column update), one `SubmitReviewView` + deprecated alias, staff-only text, stored tags + `reviewed_at`, immutable in Django admin. `tests/test_review_endpoint.py` (43). | Resolved | Claude |
| `ERR-018` | 2026-10-02 | Frontend (local verification) | `Low` | `tsc` and `next` were not found when first invoking the isolated worktree's npm scripts. | The dependency junction was accidentally created at `frontend/frontend/node_modules` because its path was resolved twice from the frontend working directory. | Removed that exact junction and recreated `frontend/node_modules` pointing to the existing project dependency tree; `npm test` passed 88/88 and `npm run build` completed. | `RESOLVED` | Codex |
| `ERR-019` | 2026-10-02 | Redis integration test environment | `Low` | `docker` was not recognized and no local `redis-server` executable was installed. | This workstation has no callable disposable Redis runtime, so a real-backend race cannot run locally without adding infrastructure. | Added a dedicated `pytest -m redis` suite that requires `REDIS_TEST_URL`; Batch 8 CI will provision Redis 7 and make this a required gate. In-memory tests remain only for isolated unit coverage. | `OPEN - CI GATE` | Codex |
| `ERR-020` | 2026-10-03 | Frontend (production build) | `Low` | TypeScript rejected rendering `packsError && ...` because the caught value was `unknown` and therefore not a valid `ReactNode`. | The wallet page retained the raw caught-value type in JSX instead of converting it to the existing boolean/error-message state. | Rendered the explicit error branch with a ternary and a safe message. Frontend tests passed 88/88 and `npm run build` completed. | `RESOLVED` | Codex |
| `ERR-022` | 2026-10-03 | Profiles, support, API contracts | `High` | Student profile GET invented level, country, timezone, and goals; PATCH did not persist learning fields or validate country/timezone. The support form posted to a missing endpoint, handwritten booking statuses omitted valid backend states, and dashboard calendar boundaries used the browser timezone while counts could be limited to fetched rows. | UI-complete placeholder behavior was never replaced by durable models and generated contracts. | Added `StudentProfile` and `SupportInquiry`, validated serializer-backed endpoints, retryable post-commit notification delivery, OpenAPI-derived frontend contracts with drift CI, and viewer-timezone/server-count dashboard queries. Focused 74 passed; full backend 749 passed/3 infrastructure skips; frontend 90 passed and build passed. | Resolved | Codex |
| `ERR-023` | 2026-10-03 | Tutor wallet and payout settings | `Critical` | Tutor earnings and bank-setting screens were backed by hand-written/demo values; no tutor wallet endpoint or protected bank model existed, and mock mode could report a fabricated successful payout batch. | Financial UI was implemented ahead of ledger-backed read models and secure storage, leaving contract drift and a misleading dead action. | Added account-2020/funding-derived wallet data, encrypted versioned payout storage, masking, password reauthentication, strict bank validation and tutor scoping; admin previews now require real configured accounts; removed fabricated finance rows and fake payout success. Focused 67 passed; full backend 764 passed/3 infrastructure skips; frontend 90 passed, contract/build passed. | Resolved | Codex |
| `ERR-024` | 2026-10-03 | Eskom Power Guard and outage restitution | `Critical` | The periodic task always asserted Stage 2, emitted only log messages, the expected status/backup endpoints did not exist, LTE failover was not stored, and an uncorroborated student claim could immediately issue a wallet credit. | A static UI and placeholder beat task were treated as operational provider integration without durable evidence or notification state. | Added an injectable quota-aware provider client, durable fresh/stale area status, real stage-zero handling, tutor-only backup flags, idempotent retryable notifications, generated API contracts, and fresh active provider corroboration for student reports. Focused 220 passed; full backend 774 passed/3 infrastructure skips; frontend 90 passed and build passed. | Resolved | Codex |
| `ERR-025` | 2026-10-03 | CI and frontend lint | `High` | ESLint was interactive/unconfigured and CI only checked generated API contracts; migration drift, complete regressions, production build, PostgreSQL triggers, and Redis races were not required merge gates. | Quality checks existed as local conventions instead of a complete executable matrix, leaving backend-specific invariants unproved on every change. | Added non-interactive zero-warning ESLint and CI jobs for Django/migrations/backend, frontend test/lint/contract/build, PostgreSQL 16 ledger tests, and Redis 7 race tests. Local backend 774 passed/3 service skips; frontend 90 passed; lint/build/contracts/checks passed. | Resolved - CI service execution pending first run | Codex |
| `ERR-026` | 2026-10-02 | Backend (Zoom attendance) | `High` | Attendance was credited to the wrong people: any unrecognised Zoom participant was recorded as **the student**; the tutor was matched on a **self-typed e-mail** (a guest could stop a teacher no-show verdict); the host check compared `host_id` with the per-session `user_id`; a **student no-show was unreachable** (the tutor's join moved the booking to `in_progress`, which the T+10 job never examined); a stranger or the wrong party could open a dispute after a no-show verdict; a rejoin/retry could erase a recorded leave; `meeting.ended` used our clock; `meeting.started` ignored; non-object payloads 500'd; `create_meeting` returned `None` on a Zoom rejection | Identity was decided by ad-hoc e-mail comparisons inside the webhook view, defaults favoured the student, and one row per (booking, e-mail) could not represent sessions. | `integrations/services/attendance.py::classify` (host id / signed-in account / student e-mail / unmatched with an empty e-mail), session-keyed idempotent rows (`identity`, `zoom_session_id`, unique per booking; migration 0010), Zoom `end_time`, `meeting.started`, role-specific late-telemetry disputes, T+10 job covers `in_progress`, `ZoomError`. `tests/test_zoom_attendance.py` (37); `tests/test_zoom_webhooks.py` updated so the tutor joins as the host account. | Resolved | Claude |
| `ERR-027` | 2026-10-03 | Backend (refunds, credits, strikes, disputes) | `High` | Found while building the D-6 cancellation engine: **a refunded lesson that was later disputed could also be paid to the tutor** (arbitration "release" ran on escrow that had already been refunded, driving it negative); a student could file a power outage and be refunded while the tutor went unpaid; every credit grant was **merged into one bundle**, so credits could not expire or be spent oldest-first; **strikes never decayed** (a tutor was permanently one slip from deactivation); refunds went to the wallet although D-6 says gateway; the 20-minute rule was hard-coded in 3 places; the new `status` fields collided in the OpenAPI enum names | The settlement paths were built one by one and did not know about each other's outcomes; credits had no lot/expiry concept; strikes were a bare counter. | `payments/services/refunds.py` (RefundRequest, 2050 refunds payable, gateway plug-in, convert to wallet), `credits.py` as expiring lots (`spend_credit`, `expire_credits`), `teachers/strikes.py` (90-day window, once per booking+kind), cancel / reschedule services, outage tutor-only + `lesson_delivered`, dispute guard `already_settled`, rules as settings, `ENUM_NAME_OVERRIDES`. Tests: `test_cancellation.py` (34), `test_reschedule.py` (20), `test_refunds_credits_strikes.py` (33). | Resolved | Claude |
| `ERR-028` | 2026-10-03 | Backend (payout settings, found in review of the remediation branch) | `Medium` | `PATCH/POST /payments/payout-settings/` re-checks the tutor's password on every bank-detail change but was only covered by the default 300 requests/minute limit, so a stolen session could guess the password and then redirect payouts | The password re-authentication had no dedicated rate limit | `payments/throttles.py::WritesOnlyScopedThrottle` + scope `payout_settings` (5 changes/hour; reads unlimited). Test in `test_tutor_wallet_payout_settings.py`. Still to do before payouts go live: e-mail the tutor on every change and add a one-time code (see `REMEDIATION_INTEGRATION.md`). | Resolved | Claude |
| `ERR-029` | 2026-10-03 | Integration audit (refunds, finance view, contracts, locks) | `Medium` | After merging the remediation branch: two orphaned refund helpers still booked refunds to the wallet (the superseded rule); the admin escrow view could not see lessons cancelled with the new statuses; the wallet history contract lacked the `expiry` type; reschedule locked slots without an ownership token | Two parallel changes touched the same concepts and the merge resolved the conflicting lines but not the code that no longer had a caller or a list that needed the new values | Orphans deleted (single refund path), statuses added to the finance view, schema + types regenerated, reschedule uses token locks. Tests added for each. See `REMEDIATION_INTEGRATION.md`. | Resolved | Claude |
| `ERR-030` | 2026-10-03 | Backend (Redis locks), found by the first real CI run (`redis-races` job) | `Critical` | On a real Redis the atomic lock scripts **never matched the owner's token**: `release_slot_lock` returned False for the rightful holder and `extend_slot_lock` too, so checkout would have refused every payment as "slot just taken" and slot / periodic-task locks were never released early. The in-memory test cache and the old "stale owner" integration test (which passes when every comparison fails) hid it | Django's built-in Redis cache **pickles** string values, but the Lua `GET == ARGV[1]` compared the stored pickled bytes against the plain token | `common/cache_locks.py` now passes the token through the cache's own serializer before comparing. New `tests/test_cache_lock_serialization.py` (12) drives Django's real `RedisCache` backend against a byte-exact Redis stand-in (reproduced the CI failure first); real-Redis integration tests gained positive controls (extend, release, periodic-task release). | Resolved (re-verify on the next CI run) | Claude |
| `ERR-031` | 2026-10-03 | Dependencies (security), found by the new `pip-audit` CI step | `High` | Django **5.1.15 had 8 known vulnerabilities** (PYSEC-2026-198/199/201/2090-2092/3717/4035), fixed only in 5.2.15-5.2.17 / 6.0.x, and the 5.1 line is past support | `requirements.txt` allowed `Django>=5.1,<5.2` and nothing audited dependencies | Upgraded to the Django 5.2 LTS (`>=5.2.17,<5.3`): all 992 tests, system check, migration drift, production deploy check, OpenAPI contract, fresh-database migrate unchanged. `pip-audit --strict` is now a blocking CI step and Dependabot watches pip, npm and actions. | Resolved (confirm on the next CI run) | Claude |
| `ERR-032` | 2026-10-03 | CI / Dependabot | `Low` | The first Dependabot batch opened 10 PRs and 9 failed CI: 8 because their base predated the Django security upgrade (`pip-audit` correctly failed on Django 5.1.15), `django-filter` 26 needs Django 5.2, `tailwindcss` 4 breaks the build, and the informational `npm audit` step showed a red error annotation that read like a failure | The Dependabot config proposed every update including majors, and the audit step used `continue-on-error`, which still marks the step red | Candidates were tested instead of guessed: icalendar 7, drf-spectacular 0.30, celery 5.6.3, django-filter 26, dj-database-url 3, lucide-react 1.49 and date-fns 4.4 pass the full suites and the build and were adopted; Tailwind 4, `eslint-config-next` 16 (Next 16 only) and `@types/node` 26 (we ship Node 22) were rejected. Dependabot now proposes minor/patch only (majors are deliberate tasks); `npm audit` reports a yellow warning, not a red error. | Resolved | Claude |
| `ERR-033` | 2026-10-03 | Backend tests (tutor wallet), found while testing the Dependabot bumps | `Low` | `test_wallet_uses_funding_for_pending_and_ledger_2020_for_cleared` failed about 1 run in 3, also on untouched `develop`, so it looked like a dependency regression and was not | The wallet lists transactions newest first and the test created three records back to back, relying on distinct timestamps; on Windows the clock can return the same instant for two of them, so the order was undefined | The test now pins explicit creation times (12/12 targeted runs and 6/6 full-suite runs pass). No wallet code changed. | Resolved | Claude |
| `ERR-034` | 2026-10-03 | Next 16 upgrade (Task 8.9): `npm i`, lint | `Medium` | `npm i next@16 react@19 eslint-config-next@16` failed with ERESOLVE (peer `eslint >=9`); after the upgrade `eslint .` reported 18 errors from the new `react-hooks/set-state-in-effect` and `react-hooks/purity` rules, and `next lint` no longer exists | eslint-config-next 16 needs ESLint 9+ as a direct dependency and ships eslint-plugin-react-hooks 7 (React Compiler heuristics); Next 16 removed `next lint` | Installed eslint 9 in the same npm command; flat `eslint.config.mjs` + `npm run lint` = `eslint . --max-warnings 0`; fixed the one real purity finding (`useState(() => Date.now())`); `set-state-in-effect` switched off with a written reason (the working loader/timer effects are out of scope for a framework upgrade) and the deliberate hard-reload `window.location` rule off; `eslint-config-next` moved to devDependencies so `npm audit --omit=dev` is 0 vulnerabilities (now a blocking CI step). Verified: `npm test` 95/95, lint, `npm run build`, `next start` smoke test | Resolved | Claude |
| `ERR-035` | 2026-10-03 | Ledger required FX (Task 10.1 slice B): full `pytest` | `Medium` | 960 test errors (`IndentationError` while loading `payments.0016_ledgerentry_fx_required`) | A PowerShell one-liner that added a header comment to the generated migration wrote a literal backslash-n instead of a newline, producing an invalid migration file | Rewrote the migration file by hand (schema-only `AlterField` x2, comment on its own lines); full suite re-run: 1025 passed, 6 skipped. Lesson: edit generated files with the editor tool, not shell string escapes | Resolved | Claude |
| `ERR-036` | 2026-10-03 | Task 10.1 Slice C: `npm run build` in a fresh git worktree | `Low` | `next build` (Turbopack) failed with "Symlink [project]/node_modules is invalid, it points out of the filesystem root" | To avoid an install the worktree's `frontend/node_modules` was a directory junction to the main checkout; Turbopack refuses links that leave the project root. Tests and lint passed through the junction, only the build failed | Removed the junction and ran `npm ci` in the worktree; build, lint, `npm test` (114) and `check:api-types` pass. Not a code defect; use a real `npm ci` in worktrees | Resolved | Claude |
| `ERR-060` | 2026-10-03 | Task 10.2e grace bookings: `grace.on_failed` test | `Medium` | `InvalidTransition: illegal status change 'confirmed' -> 'cancelled'` when a grace booking's PENDING payment failed before the lesson | The state machine had no way to undo a confirmation: `confirmed` could only go to the outcome statuses (`cancelled_by_student` etc.), and those are refund statuses that would mislabel a payment failure as a student cancel; `cancelled` was reachable only from `pending_payment` | Added one documented edge `confirmed -> cancelled` (reason `grace_payment_failed`, used only by `payments/services/grace.py`), updated `docs/BOOKING_STATE_MACHINE.md`; `cancelled` stays re-confirmable only by a payment that has no funding yet (see ERR-061) | Resolved | Claude |
| `ERR-061` | 2026-10-03 | Task 10.2e, found while designing "a cancelled grace booking" (webhook handler) | `High` | Latent: a *different* payment landing on a `cancelled` booking that already had a `BookingFunding` (a failed grace payment, or a dispute decided as a full refund) was allowed to re-confirm it, and `ensure_gateway_funding` then re-used the stale funding row (pointing at the old transaction) so the settlement gate never lifted | `PAYABLE_BOOKING_STATES` includes `cancelled` (for late payments after a purged hold) but nothing checked that the booking was still unfunded | `process_payment_webhook` now treats a booking whose funding belongs to another transaction as not payable: the money is held as UNALLOCATED for a gateway refund (`booking_not_payable`). Test `test_a_different_payment_for_a_booking_whose_grace_payment_failed_cannot_resurrect_it` | Resolved | Claude |
| `ERR-062` | 2026-10-03 | Task 10.2e design: grace funding upgrade vs ledger immutability | `Medium` | `BookingFunding.save()` raises `LedgerImmutabilityError` on any update, so a pending funding could not become `gateway` (or `platform_absorbed`) once the payment resolved; the first design would have needed a delete + re-create of an immutable row | The funding row is deliberately immutable, but its provenance flag is the only field that legitimately changes when a pending payment resolves | Added `BookingFunding.resolve_pending()`: the only permitted write, restricted to `gateway_pending -> gateway / platform_absorbed` and to the `source_type` column (amount, currency, FX and the payment link stay frozen). Covered by the grace completion and failure tests | Resolved | Claude |

---

## 🔎 Detailed Error Resolution Case Studies

### `ERR-009`: Token mirrored into a JS-readable header (Task 8.4)

Caught before any release by checking raw response headers of a `next start` build, not just the browser's cookie jar (which correctly showed HttpOnly cookies). **Lesson:** verify HttpOnly claims at the HTTP layer; a cookie being HttpOnly says nothing about the same value appearing elsewhere in the response. Regression guard: `serializeCookie` unit tests, plus the manual check "no `eyJ` outside `Set-Cookie`" recorded in `docs/PHASE_8_SESSION_COOKIES.md`.

---

### `ERR-006`/`ERR-007`/`ERR-008`: Defects exposed once fake data was removed (Phase 8)

All three were invisible while `lib/api.ts` silently returned fixtures on any failure, and only appeared when the frontend was first run against the real backend with the fallbacks removed. See the table above for root cause and fix. Verification: live browser run (login -> book -> reserve -> checkout -> failed pay -> expired-session redirect), `pytest` 236+ passing, `npm test` (12 HTTP-client tests), `npm run build`.

---


### `ERR-001`: Redis Connection Error in Pytest Environment

#### Stack Trace:
```python
redis.exceptions.ConnectionError: Error 10061 connecting to 127.0.0.1:6379. 
No connection could be made because the target machine actively refused it.
```

#### Root Cause:
When tests were executed using Python's virtual environment (`pytest backend/`) without Docker running, the Django settings attempted to instantiate a Redis connection for lock testing and Celery task dispatch, leading to host socket rejection.

#### Solution & Code Diff (`Project-files/backend/conftest.py`):
```python
# conftest.py
import pytest
from django.conf import settings

@pytest.fixture(autouse=True)
def configure_test_settings(settings):
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
```

#### Verification:
- Executed `pytest` in `Project-files/backend/venv`:  
  `3 passed in 1.93s (100% success)`.

---

### `ERR-004`: PostgreSQL Row Lock on Nullable Outer Join in Escrow Clearance Task

#### Stack Trace:
```python
django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
psycopg2.errors.FeatureNotSupported: FOR UPDATE cannot be applied to the nullable side of an outer join
```

#### Root Cause:
In PostgreSQL, executing `Booking.objects.select_for_update(skip_locked=True)` with `.exclude(dispute__status=DisputeCase.Status.OPEN)` generated a `LEFT OUTER JOIN` against the nullable `disputes_disputecase` table. PostgreSQL strictly prohibits `FOR UPDATE` locking across outer joins.

#### Solution & Code Diff (`Project-files/backend/apps/payments/tasks.py`):
```python
open_dispute_booking_ids = DisputeCase.objects.filter(
    status=DisputeCase.Status.OPEN
).values_list('booking_id', flat=True)

candidates = list(
    Booking.objects.select_for_update(of=('self',), skip_locked=True)
    .filter(
        status__in=[
            Booking.Status.COMPLETED,
            Booking.Status.COMPLETED_PENDING_MEMO,
            Booking.Status.COMPLETED_MEMO_FORFEITED
        ],
        end_time_utc__lte=cutoff_24h,
        escrow_cleared_at__isnull=True
    )
    .exclude(id__in=open_dispute_booking_ids)
    .select_related('teacher__user')[:50]
)
```

#### Verification:
- Executed in-container `docker compose exec backend pytest`:  
  `74 passed in 29.94s (100% success)`.

---

### `ERR-005`: Multi-Container Next.js SSR Backend Address Resolution

#### Stack Trace:
```javascript
TypeError: fetch failed
  [cause]: AggregateError [ECONNREFUSED]: 
    at internalConnectMultiple (node:net:1135:18)
    code: 'ECONNREFUSED'
```

#### Root Cause:
Next.js 14 App Router executes server components within the Node container environment. When `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` was used unconditionally for server-side fetches, the request attempted to bind to container localhost rather than the internal Docker bridge network hostname (`http://backend:8000/api/v1`).

#### Solution & Code Diff:
1. `docker-compose.yml`:
```yaml
environment:
  - NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
  - INTERNAL_API_URL=http://backend:8000/api/v1
  - NEXT_PUBLIC_APP_URL=http://localhost:3000
```
2. `Project-files/frontend/src/lib/api.ts`:
```typescript
const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
```

#### Verification:
- HTTP SSR status check across `/`, `/tutors`, `/materials`, `/pricing`:  
  `All returned HTTP 200 with 0 connection errors`.

---

## 🔎 Detailed Error Resolution Case Studies

### `ERR-001`: Redis Connection Error in Pytest Environment

#### Stack Trace:
```python
redis.exceptions.ConnectionError: Error 10061 connecting to 127.0.0.1:6379. 
No connection could be made because the target machine actively refused it.
```

#### Root Cause:
When tests were executed using Python's virtual environment (`pytest backend/`) without Docker running, the Django settings attempted to instantiate a Redis connection for lock testing and Celery task dispatch, leading to host socket rejection.

#### Solution & Code Diff (`Project-files/backend/conftest.py`):
```python
# conftest.py
import pytest
from django.conf import settings

@pytest.fixture(autouse=True)
def configure_test_settings(settings):
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
```

#### Verification:
- Executed `pytest` in `Project-files/backend/venv`:  
  `3 passed in 1.93s (100% success)`.
