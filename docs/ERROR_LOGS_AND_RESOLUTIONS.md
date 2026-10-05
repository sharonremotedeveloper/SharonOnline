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
| `ERR-050` | 2026-10-03 | Frontend (Task 10.2 slice I), `npm run lint` and `next build` | `Low` | The confirmed page failed to parse (`Expected </, got ident`) after the pending-payment notice was added | The JSX was inserted by a scripted edit whose shell quoting turned `role="status"` into `role=status` (and, before that, `className=\"...\"`), producing invalid JSX; the editing script, not the design, was wrong | Fixed the attributes by hand; lint, build, tests and `check:api-types` re-run green. Process note: insert JSX with the Edit tool, not shell-quoted one-liners. | Resolved | Claude |
| `ERR-070` | 2026-10-03 | Task 10.4 / 10.2F: PayPal + PayFast webhooks, unmatched payments | `High` | A signed `PAYMENT.CAPTURE.COMPLETED` (or PayFast `COMPLETE` ITN) whose `custom_id` / `m_payment_id` matched no transaction answered **400**; `custom_id` values that were not strings (list, number, object) and capture ids longer than the 255-char column were never validated before reaching the ORM | The handlers treated 'cannot apply' as 'bad request'. The gateway keeps retrying a non-200 for days, so a real payment we could not match produced a retry storm and a single anomaly row instead of one acknowledged, durable quarantine; type-confused identifiers could reach `filter(merchant_reference=<list>)` / an over-long insert (a 500 on Postgres). | Matching moved to `services/paypal_events.py` (`match_transaction`: string `custom_id` else capture id); unmatched -> `GatewayAnomaly('unknown_reference')` + **200**; ids validated (str, 1..255) -> clean 400; lookup answers that are not JSON objects -> 503 retry. PayFast unknown reference -> anomaly + 200, oversized ids -> 400. Tests: `test_webhook_events.py::TestUnmatchedPaymentsAreQuarantinedNot500`. | `RESOLVED` | Claude |
| `ERR-071` | 2026-10-03 | Task 10.4: PayFast ITN `CANCELLED` / `FAILED`, PayPal `DENIED` / `DECLINED` / `PENDING` / `REFUNDED` / `REVERSED` / `CUSTOMER.DISPUTE.*` | `High` | Only `COMPLETE` / `PAYMENT.CAPTURE.COMPLETED` did anything; every other event was acknowledged and dropped, so an abandoned or declined checkout stayed `INITIALIZED` forever, a dashboard refund left the ledger saying the money was still in escrow and a chargeback was invisible to admins | Webhook coverage was only written for the happy path. | New handlers (all signature-gated, re-read from PayPal, idempotent under the transaction row lock): denied/declined -> FAILED (+ `grace.on_failed` once for a PENDING_CAPTURE tx), pending -> `record_pending_capture`, refunded -> our `RefundRequest` completed once or an `external_refund` anomaly with reversing postings through `refunds.request_refund` + `mark_processed`, reversed/dispute -> `chargeback_opened` / `chargeback_resolved` anomaly + DisputeCase and **no automatic money movement**. PayFast CANCELLED/FAILED fail only an INITIALIZED tx (after the server postback); unknown statuses are logged at WARNING. Mutation-checked (see the 10.4 note in `PRODUCTION_READINESS_PLAN.md`). | `RESOLVED` | Claude |
| `ERR-072` | 2026-10-03 | Task 10.4: `reconcile_pending_transactions_task` for PayPal Orders v2 | `High` | An approved-and-captured order whose webhook was lost was never settled: reconciliation asked PayPal for the capture by the INIT- reference (so it answered 'unresolved') and its completed branch would have booked a payment under the INIT- reference instead of the capture id; one transaction raising inside the loop aborted the whole hourly batch | Written for the pre-Orders flow (capture id known up front); no order lookup; no per-row isolation. | `query_gateway` looks the order up with `paypal.get_order` (`classify_capture`); a completed capture is custom_id- and amount-verified and settled through `settle_completed_capture`, a pending one through `record_pending_capture`; FAILED only on an authoritative signal (declined capture, VOIDED order, or an unpaid order past the booking hold / 24 h for credit packs); PayPal outage -> 'unresolved'. The task logs (with traceback) and counts a raising row as `errors` and carries on. Tests: `test_webhook_events.py::TestReconcilePayPalOrders`. | `RESOLVED` | Claude |
| `ERR-060` | 2026-10-03 | Task 10.2e grace bookings: `grace.on_failed` test | `Medium` | `InvalidTransition: illegal status change 'confirmed' -> 'cancelled'` when a grace booking's PENDING payment failed before the lesson | The state machine had no way to undo a confirmation: `confirmed` could only go to the outcome statuses (`cancelled_by_student` etc.), and those are refund statuses that would mislabel a payment failure as a student cancel; `cancelled` was reachable only from `pending_payment` | Added one documented edge `confirmed -> cancelled` (reason `grace_payment_failed`, used only by `payments/services/grace.py`), updated `docs/BOOKING_STATE_MACHINE.md`; `cancelled` stays re-confirmable only by a payment that has no funding yet (see ERR-061) | Resolved | Claude |
| `ERR-061` | 2026-10-03 | Task 10.2e, found while designing "a cancelled grace booking" (webhook handler) | `High` | Latent: a *different* payment landing on a `cancelled` booking that already had a `BookingFunding` (a failed grace payment, or a dispute decided as a full refund) was allowed to re-confirm it, and `ensure_gateway_funding` then re-used the stale funding row (pointing at the old transaction) so the settlement gate never lifted | `PAYABLE_BOOKING_STATES` includes `cancelled` (for late payments after a purged hold) but nothing checked that the booking was still unfunded | `process_payment_webhook` now treats a booking whose funding belongs to another transaction as not payable: the money is held as UNALLOCATED for a gateway refund (`booking_not_payable`). Test `test_a_different_payment_for_a_booking_whose_grace_payment_failed_cannot_resurrect_it` | Resolved | Claude |
| `ERR-062` | 2026-10-03 | Task 10.2e design: grace funding upgrade vs ledger immutability | `Medium` | `BookingFunding.save()` raises `LedgerImmutabilityError` on any update, so a pending funding could not become `gateway` (or `platform_absorbed`) once the payment resolved; the first design would have needed a delete + re-create of an immutable row | The funding row is deliberately immutable, but its provenance flag is the only field that legitimately changes when a pending payment resolves | Added `BookingFunding.resolve_pending()`: the only permitted write, restricted to `gateway_pending -> gateway / platform_absorbed` and to the `source_type` column (amount, currency, FX and the payment link stay frozen). Covered by the grace completion and failure tests | Resolved | Claude |
| `ERR-090` | 2026-10-04 | Task 10.7 R-B: any gateway exception ended a refund (`process_pending_refunds`) | `High` | Before this slice a PayPal timeout or a 5xx raised inside `gateway.refund()` was caught, the refund was marked `failed` with the exception text stored on the row, and nothing ever retried it | The sweep treated every exception as a permanent refusal, held no idempotency key and had no claim, so even a correct retry would have risked a second refund | Rewritten per the Architect-approved design (`TASK_10_7_REFUND_GATEWAYS_PLAN.md` 2b): claim by compare-and-swap, call outside any lock, token-fenced `apply_result`; an exception or `transient` result only schedules a backoff (15m, 1h, 4h, 12h, 24h) and `failed` needs `REFUND_MAX_ATTEMPTS` attempts AND `REFUND_TRANSIENT_WINDOW_HOURS`; only the exception type is logged. Tests: `test_refund_processing.py::TestTransient`, `TestCrashAndConcurrency`; legacy tests rewritten | Resolved | Claude |
| `ERR-091` | 2026-10-04 | Task 10.7 R-B tests: `tasks.py` import, `process_pending_refunds` counters | `Low` | Two slips caught by the new tests/imports: (1) `SyntaxError: unterminated f-string literal` in `apps/payments/tasks.py` because a scripted insert turned `
` escapes into real newlines (all 1558 tests failed at import); (2) a still-pending poll was counted as `submitted` in the sweep dict, contradicting the documented counters | (1) shell-quoted multi-line edit (same class as ERR-035 / ERR-050); (2) the outcome `submitted` was counted for polls as well as sends | (1) re-edited with the editor tool; (2) a pending poll is only `polled`, never `submitted` (`test_the_poll_keeps_waiting_while_the_provider_is_pending`). Full suite re-run green | Resolved | Claude |
| `ERR-092` | 2026-10-04 | Task 10.7 R-B: refund cash leg vs capture leg (`ledger_service`) | `Medium` | `_gateway_cash_account` chose 1010 (PayFast cash) for ANY ZAR payment, even one captured through PayPal, so the refund leg could land on a different cash account than the gateway that actually holds the money | The refund helper keyed on currency as well as gateway (Architect review finding) | `_gateway_cash_account` in `refunds.py` now keys on `tx.gateway` only (test `test_cash_account_follows_the_gateway_not_the_currency`). OPEN FOLLOW-UP: the capture-side postings in `ledger_service.py` (`record_escrow_capture_entry`, unallocated/quarantine entries, credit-pack capture) still use `gateway == PAYFAST or currency == 'ZAR'`; a PayPal payment in ZAR (not offered today: PayPal sells USD/EUR/JPY) would be captured to 1010 and refunded from 1020. Align them before PayPal ZAR is ever enabled | Refund side resolved, capture side open | Claude |
| `ERR-360` | 2026-10-05 | Backend (settings guard & PyJWT) | `Medium` | PyJWT `InsecureKeyLengthWarning: The HMAC key provided is shorter than 256 bits (32 bytes)...` and production guard lacked secret length check | Production settings guard did not enforce minimum character length for `ZOOM_VIDEO_SDK_SECRET`, and test sample secret was under 32 bytes | Added `len(video_sdk_secret) >= 32` check to `validate_production_settings` in `guard.py`, required key/secret presence symmetry, lengthened test secret to 36 bytes in `test_zoom_video_token_endpoint.py`, and added negative test cases in `test_settings_guard.py` | `RESOLVED` | Antigravity |
| `ERR-370` | 2026-10-05 | Frontend (hardware verification) | `Low` | `HardwareCheckModal` used `setPingMs(Math.round(28 + Math.random() * 20))` and hardcoded `38ms` fallback, violating the zero-fake-data policy | UI mock code left simulated random latency instead of measuring actual network roundtrip time | Replaced fake latency calculation with real `fetch` HEAD request roundtrip measurement against origin (`performance.now()`), handling `Measuring...`, real latency in ms, and `Unavailable` states | `RESOLVED` | Antigravity |
| `ERR-380` | 2026-10-05 | Frontend (classroom UI & tests) | `Medium` | `VideoSdkClassroom.tsx` lacked active AV device selection controls and had no unit/component tests running under Node test runner | Initial V3 implementation wired basic WebRTC streams but omitted device enumeration modal and device switching handlers; path alias `@/` imports broke under CommonJS Node test runner | Implemented AV Device Selection modal with camera/mic/speaker switching; sized controls and PiP preview for mobile viewports (320px+); decoupled `VideoSdkClassroom.tsx` by importing `fetchVideoSessionToken` from relative path `../../lib/videoSdk`; added 12 unit tests in `videoSdk.test.ts` and 7 tests in `videoSdkClassroom.test.ts` under Node test runner | `RESOLVED` | Antigravity |

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


---

### ERR-110: capture and refund of one PayPal ZAR payment hit different cash accounts (Task 10.7 QA H1)
- **Symptom:** after a PayPal payment taken in ZAR was captured and refunded, account 1010 (PayFast) stayed at -amount and 1020 (PayPal) at +amount; both reconciliations were wrong.
- **Root cause:** `ledger_service` picked the capture-side cash account with `gateway == payfast OR currency == 'ZAR'` (four places) while `refunds._gateway_cash_account` keyed on the gateway only.
- **Fix:** one helper `ledger_service.gateway_cash_account(tx)` (gateway only) used by every capture/quarantine/unallocated/credit-pack posting and by the refund side. Tests: `TestCaptureSideCashAccountFollowsTheGateway`.

### ERR-111: admin pages cannot render in tests (Task 10.7 QA M4)
- **Symptom:** `ValueError: Missing staticfiles manifest entry for 'admin/css/base.css'` when a test rendered the refund admin form.
- **Root cause:** settings use `CompressedManifestStaticFilesStorage`; tests never run collectstatic.
- **Fix:** the admin tests switch `STORAGES['staticfiles']` to the plain `StaticFilesStorage` (fixture `plain_static_files`); production settings untouched.

### ERR-120: mutation runs "killed" by a SyntaxError instead of a test (slice Q0)
- **Symptom:** two rows of the Q0 mutation table (`--replace 'return ""'`) reported KILLED, but the mutant on disk was `return "` (and `return None"`): the guard failed because the file no longer parsed, not because it detected the violation.
- **Root cause:** Windows PowerShell 5.1 drops embedded double quotes when it passes arguments to a native executable; `scripts/mutate.py` applied whatever text it received without checking it. The same quoting loss broke a `ruff --config 'lint.per-file-ignores = {...}'` probe from the shell.
- **Fix:** `mutate.py` now compiles a Python mutant before running tests and refuses one that does not compile (exit 2, "invalid mutant", test `test_a_mutant_that_does_not_compile_is_refused`); the docstring and `docs/QUALITY_GATES.md` say to escape quotes (`'return \"\"'`) in PowerShell. The two rows were rerun with escaped quotes and are genuine kills. The ruff baseline guard builds its `--config` overrides in Python (argv list), never through a shell.

### ERR-121: ruff JSON report unreadable through a PowerShell pipe (slice Q0)
- **Symptom:** `json.decoder.JSONDecodeError: Unexpected UTF-8 BOM` when the baseline generator read `ruff check --output-format json` from stdin.
- **Root cause:** PowerShell 5.1 re-encodes piped native output with a BOM.
- **Fix:** the (scratchpad) generator reads `--output-file` output with `utf-8-sig`; nothing in the repo depends on the pipe.

### ERR-122: teacher-status guard missed a write through a neutral variable name (slice Q0)
- **Symptom:** the first baseline run reported `teachers/strikes.py: allowlist says 2 but only 1 remain`, although `strikes.py` writes `is_active` twice.
- **Root cause:** the detector only flagged `x.is_active = ...` when the receiver's name looked like a tutor (`teacher`, `profile`); `strikes.add_strike` writes `locked.is_active = False`.
- **Fix:** `is_active` writes are flagged for every receiver except clearly different models (`user`, availability, packs, prices, bundles, slots); `is_verified` for every receiver; `status` still only for tutor-looking receivers (every model has a `status`; T1a adds its own stricter guard). Detector test covers `locked.is_active`.

### ERR-123: tutor-status guard false negatives found by QA review (slice Q0)
- **Symptom:** QA probes `request.user.teacher_profile.is_active = False`, `qs.update(is_verified=True)`, `.update(**{'is_active': False})`, `bulk_update(ps, ['is_active'])` and `self.status = ...` inside `class TeacherProfile` all passed the guard.
- **Root cause:** the `user` exclusion was checked before the tutor words; ORM writes were only checked on receivers containing `TeacherProfile` and only as plain kwargs; `self` had no class context.
- **Fix:** one documented receiver classifier (availability/strike/slot -> other, then teacher/profile/tutor -> tutor, then user/pack/price/bundle/booking/transaction/refund/purchase -> other, else unknown; `self` by enclosing class), applied to assignments, `setattr`, `update` (kwargs, `**{...}`), `bulk_update` field lists and TeacherProfile creates. Detector tests for every probe and for the look-alike models; baseline unchanged (8).

### ERR-124: blocked network attempts could be swallowed by application code (slice Q0)
- **Symptom:** QA review: `NetworkBlocked` raised inside `try: ... except Exception:` in app code disappeared and the test passed.
- **Root cause:** the guard only raised; nothing remembered the attempt. `gethostbyname(_ex)` were not guarded.
- **Fix:** `network_guard` records every blocked attempt; the autouse `no_network` fixture fails the test at teardown when any were recorded (`consume()` for tests that block on purpose); `gethostbyname` / `gethostbyname_ex` patched. Full suite still green (no hidden attempts existed).

### ERR-125: ruff per-file baseline hid new violations of an already-baselined code (slice Q0)
- **Symptom:** QA review: a second C901 function (or a second S/B finding) in a file already listed for that code passed `ruff check .`.
- **Root cause:** `extend-per-file-ignores` ignores a code for the whole file.
- **Fix:** `test_guard_ruff_baseline.py` pins the count per (file, code) for C901 and every S/B code (`RUFF_COUNTS`, 42 violations / 26 pairs) and fails when a count rises or falls without the baseline being lowered; F codes stay per-file.

### ERR-126: new lint violation in the booking-status guard extension (slice Q0)
- **Symptom:** `test_guard_ruff_baseline` failed with `B905` (`zip()` without `strict=`) in `tests/test_booking_state_machine.py` after the create/defaults extension.
- **Root cause:** `zip(dict.keys, dict.values)` written without `strict`.
- **Fix:** `strict=True` (keys and values of an AST dict always have the same length). The ruff guard working as intended.

### ERR-130: a rescheduled lesson had no Zoom room and its tutor was scored a no-show (Slice F0, defect A)
- **Symptom (code trace + red test):** after a reschedule the booking kept `zoom_meeting_id=''`; the T+10 job skipped the probe for an empty id and applied TEACHER_NO_SHOW (strike, refund, bonus credit).
- **Root cause:** `rescheduling.py` blanked the `zoom_*` fields, but the booking's `FulfillmentDispatch` still had `zoom/calendar/email_completed=True`, so `dispatch_booking_fulfillment` skipped every step; the no-show branch never checked that a room existed.
- **Fix:** `fulfillment.reset_for_reprovision` inside the reschedule transaction; a lesson without a meeting id goes to DISPUTED + open DisputeCase (`attendance_probe.dispute_without_verdict`), never a no-show. Tests: `TestRescheduleReprovisions`, `TestNoMeetingIsNeverANoShow`.

### ERR-131: a Zoom API error during the T+10 probe counted as "tutor absent" (Slice F0, defect B)
- **Symptom:** `get_meeting_status` returned `{'status': 'error'}` on any non-200 and the caller's blanket `except` only logged; `teacher_attended` stayed False and the tutor was scored a no-show. A status change during the probe also crashed the run (`InvalidTransition`).
- **Root cause:** a two-state reading of a three-state fact, and the HTTP call made under the booking row lock.
- **Fix:** `attendance_probe.probe_meeting` -> `started | not_started | unknown`; `unknown` defers to the next run and an unresolved lesson is DISPUTED at its end; probes run before any lock, then lock + re-check status/meeting id. Tests: `TestProbeMapping`, `TestProbeUnknownDefers`, `test_the_http_probe_runs_outside_any_transaction`.

### ERR-132: fulfilment could run twice, overwrite a cancellation, and never stop retrying (Slice F0, defect C)
- **Root cause:** `RUNNING` was set with a read-modify-save (no compare-and-swap), the booking was saved in full from a stale instance, its status never re-checked, "no Google token" counted as completed, and failures retried forever.
- **Fix:** `bookings/services/fulfillment.py` (CAS claim + lease, row-locked status re-check, `update_fields`, per-step states, terminal FAILED + alert, orphan deletion; migration `payments/0022`). Tests: `TestClaim`, `TestFulfilmentRun`, `TestEmailFailureContract`.

### ERR-133: transactional F0 tests failed only in the full suite (`PriceNotConfigured: No active lesson price for ZAR`)
- **Symptom:** `test_the_http_probe_runs_outside_any_transaction` passed alone and failed after another `transaction=True` test; switching to `serialized_rollback=True` then failed with `IntegrityError: UNIQUE constraint failed: django_content_type...` on SQLite.
- **Root cause:** a transactional test flushes the database afterwards, deleting the migration-seeded `LessonPrice` catalog for the next transactional test; serialized rollback re-inserts content types that the flush keeps.
- **Fix:** a `price_catalog` fixture that re-creates the four seeded prices with `get_or_create` for the transactional F0 tests.

### ERR-134: a Zoom OAuth failure was still scored as a teacher no-show (F0 review B1)
- **Symptom (red tests patching `requests`):** token endpoint 401/429/500 -> `get_access_token()` returned `""` -> `get_meeting_status` returned the simulated `waiting` -> `not_started` -> TEACHER_NO_SHOW; `create_meeting` fabricated a room (step `done`, dead link to the student); a 200 without `status` defaulted to `waiting`.
- **Root cause:** "no token" meant both "no credentials" and "OAuth failed", and the simulation was a global fallback.
- **Fix:** with credentials a token failure raises `ZoomError` (status code logged, never the body); simulation only without credentials and with `ZOOM_SIMULATE_WITHOUT_CREDENTIALS` (local settings only, base/production `False`); missing status -> `None` -> `unknown`; `waiting` additionally needs no past instance (`get_past_instances`). Tests: `test_f0_review.py::TestOAuthFailureIsUnknown`, `TestPastInstances`.

### ERR-135: the calendar step wrote the booking from an unlocked instance (F0 review M1)
- **Root cause:** `sync_booking_to_teacher_gcal` saved `teacher_gcal_event_id` itself, outside the fence the Zoom step had.
- **Fix:** the sync only returns the id; `fulfillment._store_event` stores it under the row lock (`update_fields`), and deletes the event (`cleanup_gcal_event`) when the lesson was cancelled/moved, the claim lost, or an event already stored. Tests: `TestCalendarFence`.

### ERR-136: fulfilment liveness gaps (F0 review M3, M4, m1)
- **Root cause:** a lost broker message left a QUEUED row forever; retries only every 5 minutes with no backoff; a replayed webhook re-queued a RETRYABLE row and bypassed a provider `retry_after`; the cap ended in FAILED even weeks before the lesson.
- **Fix:** sweep re-dispatches PENDING/QUEUED rows untouched for 120 s; jittered exponential backoff + `apply_async(countdown)`; RETRYABLE claimed/requeued only when due; terminal after the cap only once the lesson started (alert at the cap); Django-admin re-queue action. Tests: `TestStaleQueued`, `TestRetryCadence`, `TestAdminRequeue`, `TestRetryAfterFence`.

### ERR-138: a compose stack without Zoom credentials could still simulate rooms and score fake no-shows (F0 re-review C1)
- **Root cause:** simulation was gated only by `ZOOM_SIMULATE_WITHOUT_CREDENTIALS`, which `config/settings/local.py` sets, and docker compose runs those settings, so a shared/staging compose stack would get `waiting` + no past instance for every room; `check_deploy.py` did not check the Zoom credentials.
- **Fix:** simulation also requires `DEBUG`; tests opt in with the explicit `simulated_zoom` / `zoom_never_held` fixtures; `check_deploy.py::zoom_credentials_problems` fails a production check without `ZOOM_ACCOUNT_ID` / `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET`. Tests: `test_f0_review_c1.py`.

### ERR-137: probe-only tutor presence produced a student no-show; a resolved DisputeCase hid a new dispute (F0 review M2, m7)
- **Fix:** after a `started` probe without tutor attendance rows the T+10 job records presence only and leaves the verdict to the lesson-end check; `dispute_without_verdict` reopens a RESOLVED case (history kept in `admin_notes`). Tests: `test_probe_only_presence_never_scores_a_student_no_show`, `test_a_resolved_dispute_case_is_reopened_for_a_new_verdictless_dispute`.

### ERR-180: `render_html` test expected a plain `str` (slice N1c)
- **Symptom:** `tests/test_send_email.py::TestEscapingHelper::test_result_is_a_plain_string` failed: `assert <class 'SafeString'> is str` after `str(format_html(...))`.
- **Root cause:** `SafeString.__str__` returns the object itself, so `str()` cannot strip the safe marker; the test's expectation was the wrong contract, not a code bug.
- **Fix:** `render_html` returns the `SafeString` from `format_html` (it is a `str`, already escaped, so a Django template will not escape it twice); the test now asserts `isinstance(..., SafeString)`. Documented in `docs/NOTIFICATIONS.md`.

### ERR-181: provider id / error-name filters let a trailing newline through (slice N1c)
- **Symptom:** found while writing the mutation table: `re.compile(r'^[a-z_]+$').match('validation_error\n')` matches, so a provider error name (or message id) ending in a newline would reach `error_code` and the log line.
- **Root cause:** Python's `$` also matches just before a final `\n`.
- **Fix:** both filters in `apps/integrations/services/email.py` use `fullmatch` without anchors.

### ERR-182: permanent e-mail failures were retried like transient ones (slice N1c QA, MAJOR)
- **Symptom:** a 422 / 403 / not-configured send raised the same `EmailDeliveryError` as a 503, so every caller retried it (up to 5-8 times with backoff) and F0 could not tell "stop" from "later".
- **Root cause:** the raising wrapper collapsed the `EmailResult` into one exception type and dropped the result.
- **Fix:** `EmailDeliveryError(.result)` and the subclass `EmailPermanentError` for `failed`; autoretry tasks declare `dont_autoretry_for=(EmailPermanentError,)` (supported by the installed Celery 5.6.3, `celery/app/autoretry.py`), manual-retry tasks re-raise without `self.retry`; `log_permanent_failure` logs ids + error code. Tests: `tests/test_send_email_qa.py` (`TestPermanentVersusTransient`, `TestAutoretryBehaviour`, `TestManualRetryCallers`).

### ERR-183: student first name was raw HTML in the tutor's cancellation e-mail (slice N1c QA)
- **Symptom:** `send_cancellation_emails` built `f"<p>{line}</p>"` with the student's first name inside `line`; a name like `<script>...` went into the tutor's mail unescaped.
- **Root cause:** the body was assembled with an f-string instead of an escaping helper.
- **Fix:** `render_html('<p>{line}</p>', line=line)`. Test: `test_cancellation_mail_escapes_the_student_name`.

### ERR-184: console mail backend set in base settings (slice N1c QA)
- **Symptom:** `EMAIL_BACKEND` = console backend lived in `settings/base.py`, so any non-local, non-production settings module running in console mode would print password-reset / verification links to stdout.
- **Root cause:** the dev convenience was placed in the shared base module.
- **Fix:** moved to `settings/local.py` only (docker compose uses local settings); elsewhere Django's SMTP default makes console mode fail loudly. Test: `test_console_mail_backend_is_set_by_local_settings_only`. Tests: `test_a_provider_name_with_a_trailing_newline_is_dropped`, `test_an_odd_provider_id_is_not_kept` (mutants 16 and 17 in `docs/mutation/N1c.md`).

### ERR-190: layer-0 integration, Q0 guards failed after merging F0 (integrator block 190-199)
- **Symptom:** on `integration/layer-0` after merging F0: `test_guard_integrations_silent_failures` ("zoom.py: allowlist says 2 but only 1 remain"), `test_guard_ruff_baseline` (new S311 in `fulfillment.py`, unused imports in `test_f0_review*.py`; then "Fixed - delete ... bookings/tasks.py C901/F841"), `test_q0_fakes::test_fake_zoom_create_status_delete` (`ZoomError` on a fake 500).
- **Root cause:** F0 and Q0 were built in parallel. F0 removed one silent `return ""` and two old lint violations (shrink-only baselines must be lowered), added unused test imports and a `random.uniform` jitter, and made a non-200 Zoom status raise, which Q0's fake test still expected as a returned `error` status.
- **Fix:** lowered the zoom allowlist to 1 and the ruff baseline (`bookings/tasks.py` C901/F841 removed, `BASELINE_MAX_PAIRS` 67); removed the unused imports; the jitter keeps `random` with a line-level `noqa: S311` (retry timing, not a security value; a test patches it); the fake test now expects `ZoomError`. Also applied the F0 reviewers' recommendation: the fulfilment sweep runs every 60 s (`retry-fulfillment-dispatches-1min`).

### ERR-191: layer-0 integration, Q0 fakes and guards failed after merging N1c
- **Symptom:** after merging N1c: 6 errors in `test_q0_fakes.py` (`module 'apps.integrations.email' has no attribute 'requests'`), `test_guard_pii_logging` ("integrations/email.py: allowlist says 1 but only 0 remain"), ruff F811 x14 + F401 in `test_send_email_qa.py`.
- **Root cause:** Q0's `FakeResend` patched the old sender module and set `RESEND_API_KEY` in the environment, but N1c moved the only Resend call into `apps/integrations/services/email.py`, which reads settings (and tests pin `EMAIL_BACKEND_MODE='console'`); N1c removed the PII log line (shrink-only allowlist); N1c's QA file imported the `resend` fixture by name and reused it as a parameter (never linted on its branch, which predated Q0's ruff gate).
- **Fix:** `FakeResend.install` patches `services.email.requests` and sets `RESEND_API_KEY` / `EMAIL_BACKEND_MODE='resend'` through settings; the Q0 fake test expects the returned `EmailResult`; PII allowlist entry removed; the `resend` fixture moved to `conftest.py`. New `tests/test_layer0_contract.py` drives the fulfilment e-mail step through the real sender and real `EmailPermanentError` / Retry-After (F0 re-review m5).

### ERR-192: CI Postgres job red after the layer-0 push (develop 47b69c9)
- **Symptom:** `postgres-ledger` job: `test_migration_round_trip_on_postgres` failed with `psycopg2.errors.ObjectInUse: cannot CREATE INDEX "teachers_teacherprofile" because it has pending trigger events` while unapplying `teachers/0008`; the three other T1a Postgres tests then failed with `current transaction is aborted` (knock-on). Separately `test_postgres_new_row_locks_run` (F0) expected TEACHER_NO_SHOW and got `confirmed`.
- **Root cause:** (1) 0008's reverse `restore_booleans` ran three UPDATEs over the same rows; on PostgreSQL a second update of a row already modified in the same transaction queues deferred foreign-key trigger events, and Django creates the restored column's index at the END of the migration (deferred DDL), which PostgreSQL refuses while events are pending. SQLite has no deferred triggers, so every local run passed; the Architect review had judged the migrations safe by reading them. (2) The F0 Postgres smoke test predates review item m3 (`waiting` is `not_started` only if Zoom reports no past instance) and lacked the `zoom_never_held` fixture; being skipped on SQLite it never ran after that change.
- **Fix:** `restore_booleans` is one UPDATE with `Case/When`; every data step in 0007/0008 ends with `SET CONSTRAINTS ALL IMMEDIATE` on PostgreSQL so nothing is pending when the deferred DDL runs; the F0 test takes `zoom_never_held`. Lesson: a migration that mixes data steps and schema changes must be run on PostgreSQL before merge (Docker Postgres locally, or CI on a pull request), not only reasoned about.

### ERR-193: `test_average_and_count_come_from_the_database` failed only in the full suite (layer-1 integration)
- **Symptom:** `sqlite3.IntegrityError: UNIQUE constraint failed: bookings_booking.teacher_id, bookings_booking.start_time_utc` in `tests/test_review_endpoint.py::TestAggregates`; green alone, with its file and with its class.
- **Root cause:** the file's `lesson()` helper starts every lesson at `now() - 3h`. The test creates three lessons for one tutor in a loop; on Windows the system clock advances in ~15 ms steps, so under load two iterations can read the same instant, and `(teacher, start_time_utc)` is unique for live statuses. A pre-existing timing flake, not a product defect and not an interaction with T1b's lock-order change.
- **Fix:** each lesson in the loop gets a distinct `hours_ago` (`3 + n`).

### ERR-194: CI `backend` job red after the layer-1 push: `localtime` accepted as a timezone on Linux (develop d3c5a3f)
- **Symptom:** `tests/test_t2_availability_api.py::TestTimezoneValidation::test_the_profile_serializer_rejects_unknown_zones[localtime]` (`200 == 400`) and `tests/test_t2_slot_generator.py::TestUnknownTimezone::test_an_invalid_stored_timezone_yields_no_slots_and_an_error_log_with_ids[localtime]` (slots returned) failed on GitHub's Ubuntu runner: 2 failed, 3040 passed. Green locally on Windows (3042 passed). The `postgres-ledger` job and every other job were green, so the Postgres-marked tests and migration round trips of T1a/T1b/T1c/T2/N1a/Z1 passed on PostgreSQL 16 for the first time.
- **Root cause:** `apps/common/timezones.py` (T2) treated `zoneinfo.available_timezones()` as the list of real IANA zones. That function is platform dependent: Linux system tz directories also list non-zone entries such as `localtime` (= the server's own zone), `posixrules`, `Factory`, `posix/...` and `right/...`; the Windows `tzdata` package does not. So a user could save the timezone `localtime`, which then means "whatever the server is set to" (UTC in production) instead of a real zone. Same class of bug as ERR-192: a platform difference that local runs cannot show.
- **Fix:** `_known()` removes `localtime`, `posixrules`, `Factory` and the `posix/` / `right/` prefixes. New `tests/test_timezones_platform.py` mocks a Linux-style listing so the rule is tested on every platform (red on Windows before the fix: 5 failed, 4 passed). Lesson: validation that depends on a platform listing needs a platform-independent test.

### ERR-200: golden snapshots could not be printed by a scratch pytest file (slice N1a, tooling)
- **Symptom:** running a scratch test (outside the repo) to print the new golden snapshot text failed at collection:
  `OSError: [WinError 1920] The file cannot be accessed by the system: '...\AppData\Local\Temp\jb.station.ij.10096.sock'`,
  then `found no collectors`.
- **Root cause:** given a path in the 8.3 short-name temp directory, pytest walked up to `AppData\Local\Temp` as rootdir and
  tried to stat a JetBrains socket file there. No product code involved.
- **Fix:** no scratch collection: the golden guard (`tests/guards/test_guard_notification_kinds.py`) reports the full rendered
  text in its assertion diff (`pytest -vv`, without `-q`), which was copied into `tests/golden/notifications/*.txt` with the
  editor after review. Documented in the guard's docstring ("no auto-write switch").

### ERR-150: migration round-trip test failed with `NOT NULL constraint failed: users_user.email_verified` (slice T1a)
- **Symptom:** `tests/test_tutor_status_migrations.py::test_migration_round_trip` failed while building tutors on the 0006 schema.
- **Root cause:** the test migrated to `[('teachers', '0006_teacherstrike')]` only; `MigrationExecutor.loader.project_state(targets)` then builds the historical `users.User` from the users migrations that teachers 0006 depends on (before `email_verified` existed), while the real table (users left at its leaf) has the NOT NULL column.
- **Fix:** the test's targets keep every other app on its latest leaf and only move teachers (`_targets(...)`), so the historical User matches the table. No product change.

### ERR-151: Django admin change page 500 in a test (`Missing staticfiles manifest entry for 'admin/css/base.css'`) (slice T1a)
- **Symptom:** the new admin change-page test for `TeacherProfile` returned 500.
- **Root cause:** settings use whitenoise `CompressedManifestStaticFilesStorage`, which needs `collectstatic` output; tests never run it.
- **Fix:** the test overrides `STORAGES['staticfiles']` with `StaticFilesStorage` (the pattern `tests/test_refund_processing.py` already uses). No product change.

### ERR-152: committed OpenAPI stale after the read-only pin; a view docstring leaked into the schema (slice T1a)
- **Symptom:** `test_api_contract.py::test_committed_schema_is_current` failed; the regenerated schema also gained a `description` for `PATCH /admin/teachers/{id}/verify/`.
- **Root cause:** `TeacherListSerializer.is_verified` is now an explicit `BooleanField(read_only=True)` (readOnly + required in the response schema); drf-spectacular publishes a view's class docstring as the operation description.
- **Fix:** regenerated `docs/api/openapi.yaml` and `frontend/src/types/api.generated.ts` (`is_verified?: boolean` -> `readonly is_verified: boolean`, two schemas); the legacy-verify note became a comment so the contract diff is read-only only.

### ERR-153: ruff baseline entry went stale (`seed_data.py` F401) (slice T1a)
- **Symptom:** `test_guard_ruff_baseline` failed: "Fixed - delete these from [lint.extend-per-file-ignores]: seed_data.py F401".
- **Root cause:** the seed now uses the previously unused `timezone` import (`training_completed_at=timezone.now()`).
- **Fix:** removed the entry from `ruff.toml` and lowered `BASELINE_MAX_PAIRS` to 68 (the ratchet working as intended).

### ERR-154: `tsc` failed after the TS contract regeneration (`Property 'is_verified' is missing`) (slice T1a)
- **Symptom:** `npx tsc --noEmit` in `frontend/`: `src/lib/api.ts(492,7): error TS2322 ... Property 'is_verified' is missing`.
- **Root cause:** the read-only pin makes `is_verified` required in the response schema; the dev-mock booking fixture in `getBooking` (only reached with `NEXT_PUBLIC_USE_MOCKS=true`) builds a teacher object without it. `check:api-types` and `lint` do not type-check that file.
- **Fix:** the fixture sets `is_verified: true` (the API always returns the field). tsc, lint, `check:api-types` and `npm test` (152) green.

### ERR-155: `npm run build` cannot run in an agent worktree through a `node_modules` junction (slice T1a)
- **Symptom:** Turbopack: "Symlink [project]/node_modules is invalid, it points out of the filesystem root".
- **Root cause:** the worktree has no `node_modules`; agents may only junction the main checkout's, and Turbopack refuses a link that leaves the project root. Environment limitation, not a code defect.
- **Fix:** none in code; the build gate is verified after the merge on the integration checkout (or CI). Type-check (`tsc --noEmit`), lint and unit tests were run through the junction instead.

### ERR-156: a stale full-row save could silently undo a tutor suspension (slice T1a, Architect review M1)
- **Symptom:** a tutor whose profile was loaded while `approved` (e.g. `request.user.teacher_profile` in `TeacherPowerBackupView`), then suspended by a strike, PATCHed the power-backup settings: the DRF serializer's `instance.save()` wrote every column, so `status='approved'` (and the old `sla_strikes`) went back with no audit row. Red test: `test_tutor_status_signoff.py::test_power_backup_patch_after_a_strike_suspension_keeps_the_suspension`.
- **Root cause:** Django's default `save()` writes all concrete columns from the in-memory copy; the service-owned columns were not protected against stale copies, and instance assignment of the generated flags was accepted then ignored.
- **Fix:** `TeacherProfile.save()` on an existing row without `update_fields` now writes every concrete non-generated column except `status` and `sla_strikes` (written only with explicit `update_fields` by `vetting.py` / `strikes.py`); changing either on the instance before such a save raises `ValueError` (values remembered in `from_db` / `refresh_from_db` / `save`); `__setattr__` raises `AttributeError` for `is_verified` / `is_active` outside Django's own loading/saving (`_internal_write`, also used by `bulk_create`).

### ERR-157: legacy verify shim recorded a fake reinstatement when rejecting a suspended tutor (slice T1a, Architect review M2)
- **Symptom:** `PATCH /admin/teachers/<id>/verify/ {is_verified: false}` on a suspended tutor walked `suspended -> approved -> in_review -> rejected`: an "approved" audit row (and, once N1a lands, an "approved" notification) for a tutor nobody reinstated. The 409 path also used a pre-lock read of the status.
- **Root cause:** the shortest-path search used every staff edge, including the reinstatement edge, and the view read the profile before taking the row lock.
- **Fix:** a path to `rejected` may not pass through `approved` (suspended -> reject is now 409; no new edge, open question for Anesu in `TUTOR_STATUS_MACHINE.md`); the view reads the tutor once with `select_for_update()` and builds the 409 from that row.

### ERR-140: two older Zoom tests failed after Z1 (`match='bad start_time'`) and the OpenAPI contract test went stale (slice Z1)
- **Symptom:** `test_zoom_attendance*.py::test_a_zoom_rejection_is_an_error_not_a_none` failed (error text no longer contained Zoom's body); `test_committed_schema_is_current` failed after the host-link endpoint was added.
- **Root cause:** Z1 deliberately stopped putting provider bodies into `ZoomError` (ids-only rule); the two tests asserted the old text. The new endpoint changed the schema and `docs/api/openapi.yaml` was not regenerated yet.
- **Fix:** the tests now assert `HTTP 400`, the typed `status`, and that the body text is absent; `manage.py spectacular` + `npm run gen:api` regenerated the schema and TS types.

### ERR-141: new Z1 code and tests tripped ruff and the env guard (slice Z1)
- **Symptom:** ruff `S105` on `TOKEN_URL`, `F811` on a re-imported fixture; `test_env_example_lists_every_setting_read_from_the_environment` failed for the new `ZOOM_*` settings; one test compared two equal `RecordedRequest` objects by index and mis-ordered them.
- **Fix:** targeted `# noqa: S105` with a reason (the OAuth endpoint URL is not a secret), a local `price_catalog` fixture instead of an import, the new keys added to `.env.example`, and the ordering test compares by identity.

### ERR-142: Z1 QA round 1: the tutor's Start button would have opened the guest link, and four robustness gaps (slice Z1)
- **Symptom (review):** after Z1 `zoom_start_url` is always empty, so the teacher classroom opened `zoom_url` (the guest join link): with `join_before_host` off the room never opened, the tutor was not recognised as host and the lesson ended as a teacher no-show with a refund. Also: search-before-create skipped after a crashed worker (zoom step PENDING, not FAILED); a staff-issued host link credited the absent tutor with attendance; a Redis outage crashed Zoom auth; unvalidated ids reached URL paths.
- **Fix:** frontend `lib/hostLink.ts` + `ZoomLauncherButton` host mode fetch a fresh link on click (new tab, `noopener`), 409/502 states, no guest fallback; 15-minute window (`too_early`); `search_first` after any earlier attempt; `HostLinkIssue` audit + escrow hold + admin review action; every cache call in `zoom_auth.py` guarded, lock TTL above the worst-case fetch; unexpected errors in the host-link path map to 502; host/meeting ids validated, 201 without an id raises, marker search date-bounded.

### ERR-143: a Z1 QA test recursed forever and another passed a `Mock` request to Django admin (slice Z1)
- **Root cause:** a test patched `zoom_auth.cache.add` with a lambda that called `zoom_auth.cache.add` (the patched attribute); the admin-action test used a `Mock` where `get_actions` iterates `request.GET`.
- **Fix:** capture the real method before patching; use `RequestFactory` and a real superuser.

### ERR-144: the HostLinkIssue "Mark reviewed" action had no permission gate and could strand a payout (slice Z1, re-review)
- **Symptom (review):** any staff user with the model permission could clear a host-link hold (which releases payouts), including the person it was issued to; and a role-admin user without `is_staff` could obtain a staff host link (creating a hold) yet could not reach Django admin to clear it.
- **Root cause:** the action only used the model-level admin permission, and the link-issuing predicate (`role == admin or is_staff or is_superuser`) differed from who can review.
- **Fix:** `host_link.can_review` (active, `is_staff`, superuser or role admin) is now both the admin `has_review_permission` (action declared with `permissions=['review']`, `PermissionDenied` inside it) and the predicate for obtaining a staff host link; `review_host_link_issues` refuses a reviewer who issued an open selected row unless superuser. Tests: `tests/test_z1_rereview.py`.

### ERR-158: admin "add teacher profile" test posted an empty JSON list (slice T1a)
- **Symptom:** the new admin-add test got 200 with `{'specialties': ['This field is required.']}`.
- **Root cause:** Django's form `JSONField` treats `[]` as empty and the model field is not `blank=True`.
- **Fix:** the test posts `["FreeTalk"]` (the field's documented shape). No product change; whether `specialties` should be optional is a T1c question.

### ERR-210: slot generator built DST-day slots with pytz arithmetic (slice T2)
- **Symptom:** on a spring-forward day a window ending inside the gap (Europe/Berlin 2026-03-29, 00:00-02:30) produced an extra slot at 03:00 local, outside the tutor's window; on a fall-back day (2026-10-25, 00:00-04:00) the repeated 02:00-03:00 hour was listed as real slots; the same on Australia/Lord_Howe (30-minute shift). Reproduced with the old algorithm in a scratch script (`localize` + `cursor += timedelta` on the aware value) before the fix.
- **Root cause:** `pytz.localize` fixes the offset once and adding a timedelta never renormalises it, and an end time inside a gap was resolved as standard time.
- **Fix:** `slot_generator` and the new `teachers/services/schedule.py` use `zoneinfo`; every slot is converted from NAIVE local time on its own (nonexistent skipped, first fold for ambiguous), slot length is added in UTC. Decision: the repeated fall-back hour is NOT offered twice (plan rule); tests in `tests/test_t2_slot_generator.py::TestDaylightSaving`.

### ERR-211: unknown tutor timezone silently became Africa/Johannesburg (slice T2)
- **Symptom:** a tutor with an invalid stored `User.timezone` got slots computed in SAST: wrong times shown to students.
- **Root cause:** `except pytz.UnknownTimeZoneError: teacher_tz = Johannesburg` in the generator; validation existed only in the profile serializers and used `ZoneInfo()`, which accepts keys such as `localtime`; the admin form had none.
- **Fix:** `apps/common/timezones.py` (`available_timezones()` membership) used by `validate_iana_timezone` and `User.clean()`; the generator returns NO slots for an invalid stored zone and logs an error with teacher and user ids (never the value); availability writes answer 400 `timezone` until the tutor fixes the profile.

### ERR-212: the schedule page POSTed a day->boolean matrix to a single-row endpoint (slice T2)
- **Symptom:** "Save Availability" could never persist anything (400 on every save).
- **Root cause:** `api.saveTeacherAvailability` sent the whole grid to `POST /teachers/availability/manage/`, which creates one `TeacherAvailability` row.
- **Fix:** `PUT /teachers/availability/replace/` (atomic) and `lib/availability.ts` grid-to-windows conversion; the page shows the 409 conflict list.

### ERR-214: a tutor changing their timezone silently stranded confirmed lessons (slice T2 QA)
- **Symptom:** `PATCH /auth/me/ {timezone}` shifted every weekly window in UTC with no warning.
- **Root cause:** the timezone is a plain User field; only the availability endpoints computed lesson conflicts.
- **Fix:** `teachers/services/availability.py::guard_timezone_change` (same conflict computation with the new zone, tutor row locked) called from `UserSerializer.update`; 409 `availability_conflicts` unless `acknowledge_conflicts`; the admin form warns.

### ERR-215: two concurrent deletes (or PATCH racing DELETE) were 500s (slice T2 QA)
- **Root cause:** the lookup under the tutor lock (`.get`, `refresh_from_db`, the lock itself) raised `DoesNotExist` after the view's pre-check passed.
- **Fix:** `_or_404` / explicit catches raise `NotFound` (404).

### ERR-216: legacy rows with bad hours could not be deactivated (slice T2 QA)
- **Root cause:** `TeacherAvailabilitySerializer.validate` judged the merged hours on every PATCH.
- **Fix:** hours are validated only when the payload sets them (or re-activates the row).

### ERR-213: capture-time notice check broke an existing grace test (slice T2)
- **Symptom:** `tests/test_grace_bookings.py::test_a_lesson_that_already_started_gets_no_grace` failed (409 instead of the pending outcome) after the notice check was added to `_validate_still_payable`.
- **Root cause:** the first version also refused capture of a lesson that had already started, changing the deliberate Phase 10 behaviour (capture, then late-payment settlement).
- **Fix:** the capture-time check only applies while `now < start` (inside the notice window); started lessons keep the existing path. Recorded as a follow-up: refusing started lessons before capture would be safer but is a payments-policy change outside T2.

### ERR-158 follow-up (T1c)
- **Follow-up (T1c):** answered: `specialties` is now `blank=True` (migration `teachers/0010_specialties_optional`, no DB change); a tutor created at signup has no tags yet.

### ERR-170: OpenAPI test looked up a `Teacher` component that does not exist (slice T1c)
- **Symptom:** `test_openapi_marks_the_field_deprecated` failed with `KeyError: 'Teacher'` once the code was green.
- **Root cause:** the red test assumed the component name; drf-spectacular names it after the serializer (`TeacherList`, `TeacherDetail`). The TS alias `Teacher` in `frontend/src/types` is hand-written.
- **Fix:** the test checks both `TeacherList` and `TeacherDetail`. No product change.

### ERR-171: ruff baseline guard failed after T1c (`apps/teachers/serializers.py` F401 no longer present)
- **Symptom:** full suite: `tests/guards/test_guard_ruff_baseline.py::test_ruff_baseline_only_shrinks` failed (1 failed, 2417 passed).
- **Root cause:** T1c removed the unused `UserSerializer` import from `teachers/serializers.py`, so its `F401` per-file ignore in `ruff.toml` became stale; the ratchet fails until a fixed offender is removed from the baseline.
- **Fix:** deleted the `"apps/teachers/serializers.py" = ["F401"]` entry (baseline shrank by one file/code pair).

### ERR-173: the 0009 reverse could delete tutor-entered data (slice T1c, QA M1)
- **Symptom:** none yet (found in review): a backfilled profile with a `/teachers/me/` bio, a power-backup flag, a staff-set Eskom area or an uploaded photo, but no booking / availability / extra audit row, was still "untouched" and the reverse deleted it (cascading strikes, dossiers, disputes, memos; orphaning stored files).
- **Root cause:** "untouched" was inferred from three hand-picked traces; profile edits leave no trace of those kinds.
- **Fix:** the reverse requires every data column to still hold the backfill default (`BACKFILL_DEFAULTS` next to the backfill, with a test that fails when a model column is missing from it) and no row in any reverse relation (`_meta.related_objects`) besides the baseline audit row. Round-trip cases `edited_tutor`, `power_tutor`, `area_tutor`, `photo_tutor`, `tagged_tutor`, `struck_tutor`.

### ERR-172: four T1c mutants survived the first mutation run (slice T1c)
- **Symptom:** `scripts/mutate.py` round 1: 25/29 killed; survivors: `update_own_profile`'s own whitelist check, the post-save `refresh_from_db` field list in `TeacherOwnProfileView`, the blank-tag check, and two filters in the 0009 reverse.
- **Root cause:** the whitelist was only exercised through the serializer (which rejects first); the race test checked the DB but not the response body; the blank-tag check duplicated `_TagField(allow_blank=False)`; the reverse test had no pre-existing `applied` profile and no backfilled tutor with history while still `applied`.
- **Fix:** unit test calling the service directly, response assertion in the race test, redundant check removed, three more rows in the migration round trip. Round 2: 7/8 killed, 1 documented equivalent (`docs/mutation/T1c.md`).


### ERR-160: committed OpenAPI schema stale after adding the T1b endpoints (slice T1b)
- **Symptom:** the full suite failed `tests/test_api_contract.py::TestOpenApiSchema::test_committed_schema_is_current` ("API changed but docs/api/openapi.yaml was not regenerated").
- **Root cause:** the review / cancel / work-queue endpoints and the `PendingTeacherApplication.status` change altered the generated schema; the committed copy was not regenerated yet.
- **Fix:** `manage.py spectacular --file ../docs/api/openapi.yaml`, then `npm run gen:api` + `npm run check:api-types` (TS), widened `frontend/src/types/admin.ts` status and the dev-only mock fixtures.

### ERR-161: T1b red tests referenced names that do not exist (slice T1b)
- **Symptom:** while turning the red tests green two fixtures failed: `LedgerAccount.LIABILITY_DEF501_QUARANTINE` (AttributeError) and a grace transaction without `payer_id` (refused with `payer_unknown` before the new guard ran).
- **Root cause:** test authoring errors: the DEF-501 account is `LIABILITY_QUARANTINE_DEPOSIT` (2030), and `evaluate_grace` needs a payer id before it reaches the slot guard.
- **Fix:** the tests use the real constant and a payer id. No product change.

### ERR-162: ruff F811 / F401 on the T1b review-condition tests (slice T1b)
- **Symptom:** `tests/guards/test_guard_ruff_baseline.py` failed: new violations in `tests/test_t1b_conditions.py` (imported pytest fixtures from other test modules and used them as parameters).
- **Root cause:** a fixture imported by name is "unused" (F401) and a test parameter of the same name redefines it (F811); new files must be ruff-clean and the baseline may not grow.
- **Fix:** the fixtures are imported under their own aliases and each test def that takes them carries one targeted `# noqa: F811`; no baseline entry added.

### ERR-195: layer-1b integration, `reconcile_teacher_gcal_task` crashed for a tutor without a credential row (integrator block 190-199)
- **Symptom:** `tests/test_t1b_bookable.py::TestOperationalTutors::test_gcal_reconcile_follows_the_same_rule` failed with `AttributeError: 'NoneType' object has no attribute 'block_busy'` on the combined T3/G1/R1 + V1-V3 tree.
- **Root cause:** G1 changed the tutor query to a left join on `calendar_credential`, so tutors with only the legacy local-simulation token match with `credential = None`, and the new code read `credential.block_busy` unguarded.
- **Fix:** a missing credential row is treated as "nothing to fetch" (empty busy list cached, tutor counted), same as `block_busy=False`.

### ERR-196: video-token endpoint issued a classroom token for unpaid and settled lessons (integrator review of V2)
- **Symptom (found in review, red tests first):** `GET /bookings/<id>/video-token/` returned 200 for `pending_payment`, `completed`, `disputed` and no-show bookings (only cancelled statuses were refused), and returned 409 `booking_cancelled` to any authenticated stranger (booking-status oracle).
- **Root cause:** the V2 view blocklisted cancelled statuses instead of allow-listing live ones, and checked status before authorization. An unpaid booking could enter a free lesson.
- **Fix:** authorization first (403 for non-parties), then an allow-list of `confirmed`/`in_progress` (409 `classroom_unavailable` otherwise); tests added in `tests/test_zoom_video_token_endpoint.py`.

### ERR-197: `test_the_validator_uses_the_tzdata_list` failed intermittently (integrator block 190-199)
- **Symptom:** one full-suite run in about every twenty failed `tests/test_t2_availability_api.py::TestTimezoneValidation::test_the_validator_uses_the_tzdata_list`; it passed when re-run alone (the "single unidentified flaky failure" seen during the layer-1b integration).
- **Root cause:** the test checked the first 25 entries of `list(zoneinfo.available_timezones())`, a `set` with a per-process random order. On machines whose tzdata lists non-zone entries (here `Factory`) a sample sometimes included one, which `is_valid_timezone` correctly rejects (ERR-194).
- **Fix:** the test now takes a deterministic sample (first and last 25 of the sorted list) after excluding the validator's own `_NOT_ZONES`.
=======
### ERR-220: T3 R2 commit could leave storage state inconsistent after a database rollback (T3 review)
- **Symptom:** the asset was copied and the quarantine object was deleted before the surrounding `transaction.atomic` block committed; a later database error could leave a final object with no `TeacherAsset` row.
- **Root cause:** object storage has no transaction rollback and the old code performed both storage mutations inside the database transaction without compensating cleanup.
- **Fix:** track the copied final key, remove it on exception, and register quarantine deletion with `transaction.on_commit`; the rollback test proves the final object is removed and quarantine remains.

### ERR-230: Google OAuth callback exposed provider exception text (G1 review)
- **Symptom:** callback failures returned `str(exc)` to the browser, potentially exposing provider or configuration details.
- **Root cause:** the view used exception text as its public error payload.
- **Fix:** return a fixed user-facing message and log only the exception type; add typed callback serializers and regression tests.

### ERR-240: R1 review documentation and mutation coverage were missing (R1 review)
- **Symptom:** the implemented attendance-payload purge had no `docs/slices/R1.md` or `docs/mutation/R1.md`, so the retention review could not be resumed from the branch handoff.
- **Root cause:** the initial layer-1b integration landed code/tests without the required slice artifacts.
- **Fix:** added the R1 slice handoff and mutation table, preserving the existing Postgres-marked retention verification requirement.

### ERR-221: configured backend virtualenv could not start on the Codex host (verification environment)
- **Symptom:** the prescribed `backend/venv/Scripts/python.exe` failed before pytest with `Unable to create process ... Python312\\python.exe`.
- **Root cause:** `pyvenv.cfg` points to a Python 3.12 installation absent from this host.
- **Fix:** no repository workaround was applied; test evidence is explicitly pending a repaired runtime or CI.
=======
### ERR-250: N1b notification API was missing (slice N1b)
- **Symptom:** N1a exposed durable notification rows and preferences but no owner-scoped API, unread count, read transitions, or preference endpoint.
- **Root cause:** the N1a layer intentionally stopped before the API contract freeze.
- **Fix:** added paginated notification listing, owner-scoped read/read-all endpoints, unread count, typed preference serializers, mandatory-kind enforcement, and staff-only delivery error visibility. Root URL/settings/Celery registrations are handed to Claude in `docs/slices/N1b.md` and were not edited on this branch.

### ERR-198: layer-2a integration of Codex's N1b and T3/G1/R1 review branches (integrator block 190-199)
- **Symptom:** after merging `fix/t3-g1-r1-review` and `feature/n1b-notification-api` onto `develop`: `tests/test_t3_g1_r1.py::test_t3_commits_from_private_quarantine_to_final_bucket` failed; `spectacular --fail-on-warn` reported 2 errors + 1 warning (N1b `NotificationReadView` / `NotificationReadAllView` "unable to guess serializer", `get_email_last_error` without a type hint); ruff F401 in `notifications/views.py`; the notification URLs were not registered.
- **Root cause:** both branches were written on a host whose backend venv could not start (ERR-221), so nothing was executed: the T3 review fix defers the quarantine delete to `transaction.on_commit` (correct) but the older test still expected an immediate delete; N1b's POST views declared no request body and the SerializerMethodField no schema type; the shared `config/urls.py` is integrator-owned.
- **Fix:** the test runs the commit under `django_capture_on_commit_callbacks` and asserts the quarantine copy survives until commit; `request=None` on the two POST views and `extend_schema_field` on `email_last_error`; the unused import removed; `path('api/v1/notifications/', ...)` registered; OpenAPI + TS regenerated. Full gate on the merged tree: backend 3217, frontend 167, lint, build.

### ERR-199: `test_student_sees_the_tutors_real_grammar_notes_not_a_placeholder` failed intermittently (integrator block 190-199)
- **Symptom:** one full run in many failed with `UNIQUE constraint failed: bookings_booking.teacher_id, bookings_booking.start_time_utc`; it passed alone.
- **Root cause:** the helper `finished_lesson` started every lesson at `now - 2 h`; two calls in the same ~15 ms clock tick (ERR-193) gave one tutor two bookings with an identical start, which the slot constraint (correctly) refuses. The test then moved the second lesson with an UPDATE, too late.
- **Fix:** `finished_lesson(..., hours_ago=)`; the second lesson is created at 5 h ago directly.

### ERR-360: Production guard allowed short Zoom Video SDK secrets and tests emitted PyJWT warning (slice V1 review)
- **Symptom:** PyJWT emitted `InsecureKeyLengthWarning: The HMAC key provided is shorter than 256 bits (32 bytes)...` during token tests, and `config/settings/guard.py` only checked for non-empty string for `ZOOM_VIDEO_SDK_SECRET`.
- **Root cause:** Production guard lacked a minimum character length check (>= 32 chars) for symmetric HMAC-SHA256 secrets, and test fixtures used an 18-character mock secret.
- **Fix:** Enforced `len(video_sdk_secret) >= 32` in `validate_production_settings()` in `backend/config/settings/guard.py`, ensured symmetric key/secret presence check, lengthened test `SAMPLE_SECRET` to 36 bytes in `backend/tests/test_zoom_video_token_endpoint.py`, and added 4 negative test cases in `backend/tests/test_settings_guard.py`.

### ERR-370: HardwareCheckModal simulated ping with fake random numbers (slice V3 review)
- **Symptom:** `HardwareCheckModal.tsx` simulated ping with `Math.round(28 + Math.random() * 20)` and hardcoded fallback `38ms`, showing non-existent network telemetry to users.
- **Root cause:** Temporary UI mock code remained in component after initial frontend scaffolding.
- **Fix:** Replaced `Math.random()` simulation with real HTTP roundtrip measurement (`fetch` HEAD request to origin with `performance.now()` delta), adding clean status handling (`Measuring...`, real ms, or `Unavailable` on network error).

### ERR-380: VideoSdkClassroom missing device selection controls and unit test coverage (slice V3 review)
- **Symptom:** Classroom UI could not switch cameras, microphones, or output speakers during or before sessions, and classroom logic lacked unit and component tests in `frontend/src/lib/`.
- **Root cause:** Initial V3 implementation wired basic WebRTC streams but omitted device enumeration modal and device switching handlers (`switchCamera`, `switchMicrophone`, `switchSpeakerDevice`).
- **Fix:** Added AV Device Selection modal with device enumeration and device switching handlers; sized control bar and PiP preview for mobile viewports (320px+); decoupled `VideoSdkClassroom.tsx` from `@/` path alias imports by importing `fetchVideoSessionToken` from `../../lib/videoSdk`; added 12 tests in `videoSdk.test.ts` and 7 tests in `videoSdkClassroom.test.ts` under Node test runner.
