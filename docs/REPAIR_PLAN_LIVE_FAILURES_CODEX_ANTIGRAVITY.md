# Sharon Online live-failure repair plan

**Date:** 2026-10-07  
**Status:** Verified for implementation after final three-agent review  
**Implementation owners:** Codex (Task A: backend/domain) and Antigravity (Task B: frontend/UX)  
**Scope:** Repair and verify the failures found during the local student, tutor, administrator, API, and prototype browser pass.

## 1. Purpose and completion definition

This document is the shared execution plan for the two implementation tasks. It is intentionally written before code changes so that the work can be performed in isolated worktrees, tests can expose the existing failures first, and no repair can silently weaken booking, payment, attendance, privacy, or provider boundaries.

The project is not considered complete when a page renders or a focused test passes. Completion requires:

- the eight observed failures have a reproducible test or documented evidence;
- the canonical backend contract and state-machine rules are preserved;
- frontend behavior is truthful for loading, empty, unauthorized, conflict, unavailable, and success states;
- focused tests are green, then the full backend/frontend gates are green;
- Django checks, migration-drift checks, lint/type checks, and build pass;
- the authenticated student, tutor, and administrator browser acceptance flows pass locally;
- external-provider and production-account boundaries are reported separately and are not claimed without authorized verification;
- every failure and resolution is recorded in `docs/ERROR_LOGS_AND_RESOLUTIONS.md`, and the roadmap/slice handoff is updated.

## 2. Evidence from the local end-to-end pass

The local application was exercised using the seeded admin, student, and tutor accounts at `http://localhost:3000`; the backend health/API endpoints were also checked at `http://localhost:8000`. No booking, payment, payout, refund, availability save, bank-detail save, support message, or external-provider action was submitted.

| ID | Observed failure | Initial classification | Severity |
|---|---|---|---|
| F-01 | `/materials` renders `No lesson materials found` while `GET /api/v1/materials/` returns four records. | API/frontend contract or catalog mapping drift; also verify approved seed state. | High |
| F-02 | History links such as `/materials/freetalk-discussion` render `Curriculum Material Not Found`. | Canonical slug/detail contract, approved seed, or proxy mismatch. | High |
| F-03 | Tutor dashboard and `/teacher/power-guard` show a server problem. | Expected backend 409/503 integration-unavailable response is not being represented intentionally, or fresh status evidence is absent. | High |
| F-04 | Student schedule/history contains future lessons labelled completed and `pending_payment` rows in the wrong context; dates and memos are misleading. | Booking status/time authority and frontend filtering/display mismatch. | High |
| F-05 | Admin live-attendance radar shows an active class around 1,136 minutes for a 25-minute lesson. | Attendance duration normalization, reconnect/double-count, or stale provider evidence problem. | Critical |
| F-06 | EUR/ZAR and JPY/ZAR are missing; the dashboard says EUR/JPY checkout is blocked. | Missing/stale approved FX data or unsafe checkout fallback. | High |
| F-07 | Tutor public profile reports media playback failure. | Media state/storage/provider failure is not being surfaced as a typed truthful state. | High |
| F-08 | Tutor availability warns that saved windows do not align with the hourly grid or overlap. | Conditional defect: verify whether current rows violate the canonical grid contract; the warning may be intentional for legacy off-grid/overlapping rows. | High if invalid current data; otherwise informational |

The live pass also confirmed that the home page, public routes, login, role protection, core dashboards, health endpoint, teachers API, materials API, and Figma prototype launch. Those passes are route/render evidence only; they do not prove provider, payment, data-integrity, or production readiness.

## 3. Non-negotiable safety rules

Both tasks must follow `docs/AI_AGENT_COLLABORATION_RULES.md`, `docs/QUALITY_GATES.md`, `docs/PROJECT_CONTEXT.md`, `docs/PROGRESS_AND_ROADMAP.md`, and the applicable domain documents before editing.

- Work only in isolated worktrees: `codex-repair` for Task A and `antigravity-repair` for Task B. Do not edit the shared checkout while implementation is in progress.
- Use tests-first RED -> smallest GREEN fix -> regression/boundary tests. Preserve the reproducer and evidence.
- Do not guess fields, routes, statuses, slugs, schemas, timestamps, prices, FX rates, media URLs, or provider behavior.
- Do not fabricate fallback data, silently swallow exceptions, turn authorization/contract failures into empty states, or delete/disable tests.
- All booking status writes must use the canonical transition service. No direct status assignment is permitted.
- Use aware UTC datetimes at the API/domain boundary and explicit IANA time zones for display and availability calculations.
- External calls require configured timeouts, bounded retry policy, idempotency, safe logging, and provider fakes. No live Eskom, Google, R2, Zoom, PayPal/PayFast, Resend, or OAuth action is allowed as part of this repair without the project tool-access protocol and explicit owner authorization.
- Do not edit deployed migrations. If a schema/data change is actually required, add a new reversible migration, a safe backfill/forward-fix plan, drift/conflict tests, and rollback considerations.
- Keep private tutor assets private; never make a private object public to make playback “work.”
- Record every failure and resolution with an ERR identifier; update slice notes and the roadmap only after verification.
- Integrator-only files are protected from both implementation agents: OpenAPI output, generated TypeScript/API types, shared settings/URLs/Celery registration, lockfiles, roadmap, and final error-ledger consolidation.

## 4. Work split and dependency order

### Task A — Codex: backend/domain and authoritative contract repair

Codex owns the backend behavior and the authoritative API/domain tests. Suggested worktree: `Project-files/.claude/worktrees/codex-repair`.

Primary ownership:

- `backend/apps/materials/**`
- `backend/apps/bookings/**`
- `backend/apps/integrations/services/eskom.py`
- `backend/apps/integrations/services/attendance.py`
- `backend/apps/integrations/services/video_attendance.py`
- `backend/apps/integrations/views.py`, `backend/apps/integrations/serializers.py`, and `backend/apps/integrations/models.py`
- `backend/apps/admin_api/serializers.py` and `backend/apps/admin_api/views.py`
- `backend/apps/srs/views.py` and `backend/apps/srs/serializers.py`
- `backend/apps/payments/services/fx.py` and FX-specific payment code
- `backend/apps/teachers/services/availability.py`
- `backend/apps/teachers/services/schedule.py`
- `backend/apps/teachers/assets.py`
- related backend tests and `docs/slices/codex-repair.md`

Codex must not edit frontend components/routes, migrations unless justified by a failing contract, shared registration files, generated OpenAPI/TypeScript, or Antigravity’s slice document.

#### Codex slices

1. **Materials and detail contract**
   - Reproduce the list response shape/approved-record behavior as one contract test, then take a slug returned by that list and test list-slug-to-detail resolution separately.
   - Define the approved-only canonical slug contract and typed 404 behavior.
   - Align serializer/detail fields with the frontend contract (`summary`, `estimated_minutes`, `vocabulary`, `discussion_questions`, and other documented fields) without inventing content.
   - Repair seed/fixture data only if the authoritative contract proves it is missing or invalid; make it deterministic and idempotent.
   - Do not rewrite slugs without a documented migration/compatibility decision.

2. **Power Guard evidence**
   - Preserve authentication and authorization.
   - Distinguish area-not-configured, stale/missing cached provider evidence, provider failure, and a fresh valid status.
   - Return documented typed semantic responses; do not pretend a missing status is “normal” power availability.
   - Test fresh, stale, missing, malformed, timeout, and forbidden cases with provider fakes only.

3. **Booking/history authority**
   - Use the booking state machine as the only source of truth.
   - Return server status and UTC timestamps; do not infer completion from the selected UI date or first list row.
   - Separate future, completed, cancelled, pending-payment, disputed, and unavailable states according to the domain docs.
   - Ensure lesson memo availability is explicit rather than presented as an accidental blank.

4. **Attendance duration integrity**
   - Normalize provider timestamps to UTC, including raw join/leave delta handling in `video_attendance.py`.
   - Deduplicate reconnect/overlap intervals and prevent double-counting.
   - Treat unknown or contradictory evidence as disputed/indeterminate; only positive authoritative attendance may satisfy the 20-minute completion rule.
   - Add tests for clock skew, reconnects, overlapping intervals, stale records, and a 25-minute lesson; prove credited minutes cannot exceed the lesson window and that `session.ended`/leave timestamps are normalized before settlement.

5. **FX safety**
   - Use an approved stored rate with source and freshness metadata.
   - Reject missing or stale rates (the current documented freshness boundary is 24 hours) rather than inventing a rate or silently converting.
   - Preserve an immutable rate snapshot for a checkout/payment decision.
   - Add tests for missing, stale, valid, malformed, and concurrent reads. Do not add a live feed during this repair.

6. **Tutor media/storage states**
   - Model pending, public/available, private, missing, and retryable-failure states explicitly.
   - Preserve private access controls and signed/access-controlled delivery.
   - Ensure upload failure cleanup compensates object storage correctly and quarantine deletion uses `transaction.on_commit` where required.
   - Add fake-storage tests for no orphaned objects and no accidental public URLs.

7. **Availability and schedule normalization**
   - Use `zoneinfo`, explicit IANA zones, aware UTC persistence, and deterministic local display.
   - Normalize windows to the 25-minute grid and reject invalid zones/overlaps with typed errors. Treat the current warning as a defect only when current seeded rows violate the canonical contract; preserve an intentional warning for legacy off-grid/overlapping data.
   - Cover DST transitions, adjacent windows, overlap, round trips, and invalid input.
   - Replacement must be atomic and must preserve confirmed lessons unless an explicit documented acknowledgement is required.

### Task B — Antigravity: frontend, UX, and contract-consumer repair

Antigravity owns the frontend states and browser-visible behavior after Task A’s contract is frozen. Suggested worktree: `Project-files/.claude/worktrees/antigravity-repair`.

Primary ownership:

- `frontend/src/app/(public)/materials/**`
- `frontend/src/components/materials/**`
- `frontend/src/app/student/history/**`
- `frontend/src/app/student/schedule/**`
- `frontend/src/app/student/checkout/**`
- `frontend/src/app/teacher/power-guard/**`
- `frontend/src/app/teacher/dashboard/**`
- `frontend/src/app/teacher/schedule/**`
- `frontend/src/components/teacher/**`
- `frontend/src/app/teacher/profile/**`
- `frontend/src/app/(public)/tutors/[id]/**`
- `frontend/src/components/tutors/VideoReelPlayer.tsx`
- `frontend/src/components/tutors/AudioSnippetButton.tsx`
- affected portions of `frontend/src/lib/api.ts`
- `frontend/src/app/admin/sessions/live/page.tsx`
- `frontend/src/app/admin/finance/fx-rates/**`
- frontend API adapters and tests, excluding generated types
- `docs/slices/antigravity-repair.md`

Antigravity must not edit backend code, migrations, shared settings, OpenAPI/generated types, or Codex’s slice document.

#### Antigravity slices

1. **Materials** — consume the canonical list/detail contract; show truthful loading, approved-empty, 404, 403, and server-failure states; use canonical slugs and no placeholder lesson content.
2. **Power Guard** — represent area-not-configured, stale/unavailable, retryable failure, and valid status states; avoid fabricated stages; prevent repeated unauthorized polling/noise; keep retry bounded and accessible.
3. **Student booking/history** — render server status and timezone-aware timestamps; keep future lessons out of completed history; label pending payment and unresolved states correctly; do not infer state from page selection.
4. **Attendance/lesson display** — show backend-authoritative duration and unresolved/disputed evidence explicitly; never turn unknown attendance into a completed lesson.
5. **FX and checkout** — show rate freshness/source in the admin surface; disable/block unsupported currency checkout with a clear reason and no guessed conversion; preserve safe retry behavior.
6. **Tutor media** — show pending/private/unavailable/retryable states; never substitute demo media or expose private URLs; provide accessible failure messaging.
7. **Availability** — display normalized grid windows, timezone/DST-aware labels, conflicts, and atomic-save outcomes; do not imply a save succeeded if the server rejected it.

## 5. Required sequence

1. Read the authoritative docs and current error ledger; inspect current branch/worktree state.
2. Create the two isolated worktrees and record their base commit.
3. Codex writes failing backend/API tests for each reproducible issue.
4. Codex implements the backend/domain fixes and focused tests, including the SRS surfaces, integration endpoint surfaces, admin live-attendance serializer/view, and video-attendance path.
5. An integrator reviews the backend contract and regenerates OpenAPI/TypeScript types in the controlled shared step. No implementation agent edits generated output manually.
6. Antigravity rebases/starts from the frozen contract and writes frontend RED tests for each visible failure.
7. Antigravity implements truthful loading/empty/error/conflict/success states and focused component/integration tests.
8. Each agent runs its focused gates, records failures, and updates its slice document.
9. Run the complete backend and frontend gates, Q0 guards, migration checks, and changed-file review.
10. Perform authenticated browser acceptance for student, tutor, and administrator roles using read-only fixtures/accounts; verify availability save outcomes through isolated disposable fixtures or API-level tests rather than mutating the shared seeded account.
11. Re-check provider/account boundaries. Report any unperformed live-provider or production verification separately.
12. Integrate only after both task reports and the three independent review lanes sign off.

## 6. Verification gates

### Codex gates

- focused RED/GREEN tests for all eight failure areas;
- `python manage.py check`;
- `python manage.py makemigrations --check` and migration-leaf/conflict checks;
- full backend pytest suite and configured coverage/mutation/slice checks;
- Ruff/type checks and changed-file review;
- Q0 guards for direct booking writes, row-lock safety, HTTP timeouts, PII logging, silent integration failures, view permissions, migration leaves, and `.env.example` completeness;
- no external provider calls unless separately authorized.

### Antigravity gates

- focused route/component/integration tests for all visible states;
- frontend type/API-contract check;
- `npm test`;
- `npm run lint` with zero warnings;
- `npm run build`;
- accessibility checks for keyboard/focus/error announcements and mobile/desktop layout;
- browser pass for student, tutor, and admin flows;
- no fabricated persistence or placeholder provider data.

### Final gates

- full backend and frontend suites are green;
- generated OpenAPI/TypeScript matches the implemented contract;
- no migration drift or multiple leaves;
- no unreviewed shared-file edits;
- all ERR entries, slice docs, roadmap status, and handoff notes are updated;
- independent failure-verifier, plan-architect, and ECC-reviewer sign-offs are recorded below;
- completion report clearly separates focused tests, full-suite tests, browser UAT, provider checks, staging checks, commits, and pushes.

## 7. Browser acceptance matrix

### Student

- log in and confirm dashboard only presents genuinely upcoming lessons;
- confirm completed history contains only completed/eligible lessons and correct local-time labels;
- open each material from a live API slug and verify detail content or a truthful typed unavailable state;
- attempt an unsupported/stale-FX checkout and confirm it is blocked with an actionable reason;
- confirm no page presents a guessed price, status, duration, or memo.

### Tutor

- log in and verify Power Guard states are intentional for unavailable/stale/configuration conditions;
- verify schedule/availability grid, timezone labels, DST-sensitive windows, overlap errors, and non-destructive save behavior;
- verify profile media pending/private/unavailable states without exposing private URLs;
- confirm no repeated unauthorized polling or false success toast appears.

### Administrator

- verify live-attendance duration is bounded and evidence-backed;
- verify FX table shows source/freshness and missing/stale rates block checkout;
- verify error states distinguish unavailable data from an empty dataset;
- confirm no action changes finance, attendance, payout, dispute, or seed data during read-only acceptance.

## 8. Rollback and data-safety plan

- Keep both worktrees and their commits separate until final review.
- Revert by commit/worktree selection, not by resetting the shared checkout or deleting user changes.
- Prefer forward-fix and additive nullable changes over destructive migration edits.
- Take no production-data action. Local fixture/seed changes must be idempotent, reviewable, and explicitly labelled.
- If a contract change causes a frontend regression, stop integration, restore the last known contract, and resolve the contract in OpenAPI/types/tests before proceeding.
- If a provider response is unavailable, preserve that fact in the API/UI rather than adding fake data.

## 9. External gates and decisions required from the owner

The following are not silently assumed to be complete:

- live Eskom/provider status verification;
- real Google Calendar OAuth callback/free-busy verification;
- Cloudflare R2/private media verification;
- Zoom attendance verification;
- PayPal/PayFast checkout/refund verification;
- Resend/email delivery and domain/DNS verification;
- production database, secrets, and deployment verification.

Before those checks, use `docs/TOOL_ACCESS_AND_ACCOUNTS.md` and the project account-identity protocol. Do not create accounts, credentials, domains, DNS records, or production data as part of this repair without explicit approval.

The owner may also need to decide any unresolved product policy exposed by tests, including the authoritative booking/status truth table, acceptable FX freshness/source, attendance treatment for indeterminate provider evidence, and whether any existing seed data should be corrected or preserved as historical test data.

## 10. ECC review applied

The documented ECC path in the collaboration rules is stale. The actual local library used for review is:

`C:\Dev\Active Projects\Sharon Online\ECC-main\skills`

Relevant ECC guidance for this plan:

- `django-patterns`, `backend-patterns`, `api-design`, and `contract-first` for service boundaries, HTTP semantics, ownership, and schema consistency;
- `django-tdd`, `python-testing`, and `react-testing` for RED/GREEN evidence, deterministic fixtures, boundary tests, and truthful UI-state coverage;
- `django-security` and `security-review` for authorization, CSRF/webhook controls, private media, secrets, safe logs, and rate limits;
- `database-migrations` and `postgres-patterns` for immutable migrations, safe backfills, indexes, locks, and concurrency;
- `python-patterns` and `error-handling` for typed behavior, exception chaining, provider error classification, and no swallowed failures;
- `react-patterns`, `frontend-patterns`, and `nextjs-turbopack` for hooks, cleanup, server/client boundaries, routing, accessibility, and build correctness;
- `verification-loop` and `production-audit` for full-gate evidence, retries/idempotency, rollback/runbooks, and honest completion reporting.

ECC does not replace the project’s domain authority. Booking transitions, retention, availability, and attendance acceptance criteria remain governed by the project documents, especially `docs/BOOKING_STATE_MACHINE.md`, `docs/BOOKING_HOLDS.md`, `docs/QUALITY_GATES.md`, and the Phase 11/12 plan.

## 11. Agent prompts

### Prompt A — Codex backend/domain repair agent

> You are Codex, the backend/domain owner for Sharon Online’s live-failure repair. Work only in the assigned isolated worktree `codex-repair`; do not edit the shared checkout, frontend routes/components, generated OpenAPI/TypeScript, shared registration/settings files, lockfiles, or Antigravity’s slice document.
>
> Before editing, read `docs/README.md`, `docs/PROJECT_CONTEXT.md`, `docs/PROGRESS_AND_ROADMAP.md`, `docs/AI_AGENT_COLLABORATION_RULES.md`, `docs/QUALITY_GATES.md`, `docs/TOOL_ACCESS_AND_ACCOUNTS.md`, the current error ledger, and the authoritative booking, attendance, payments, availability, and media documents. Also inspect the applicable ECC guidance under `C:\Dev\Active Projects\Sharon Online\ECC-main\skills`, especially django-patterns, backend-patterns, api-design, contract-first, django-tdd, django-security, database-migrations, error-handling, verification-loop, and production-audit.
>
> Verify and repair the backend causes of F-01 through F-08: materials/detail contract and canonical slugs; Power Guard fresh/stale/configuration/unavailable evidence; booking status and UTC timestamps in the SRS views/serializers; attendance interval normalization and duplicate prevention in both attendance services; approved FX freshness and immutable snapshots; typed tutor media/storage states and cleanup; and availability timezone/DST/grid normalization. Trace each issue to code, tests, and API behavior before changing it. Do not guess a field, route, status, price, slug, timestamp, provider result, or seed value.
>
> Work tests-first: create a failing reproducer, capture RED evidence, implement the smallest safe fix, then add boundary/regression tests for permissions, invalid input, missing/stale/provider failures, retries, idempotency, concurrency, DST, and overlap. All booking writes must use the canonical transition service. Use provider fakes and local data only; do not call Eskom, Google, R2, Zoom, PayPal/PayFast, Resend, OAuth, or production services.
>
> Run focused tests, Django check, migration drift/conflict checks, `makemigrations --check`, full backend pytest, Ruff/type checks, Q0 guards, and changed-file review. Log every failure with an ERR identifier, update `docs/slices/codex-repair.md`, and report exact evidence. Clearly separate focused/full-suite results from browser, provider, staging, commit, and push status. Stop and report if the contract requires an owner decision or an external account action.

### Prompt B — Antigravity frontend/UX repair agent

> You are Antigravity, the frontend/UX owner for Sharon Online’s live-failure repair. Work only in the assigned isolated worktree `antigravity-repair`; do not edit backend code, migrations, shared settings, OpenAPI/generated types, lockfiles, or Codex’s slice document.
>
> Before editing, read the project docs and current error ledger, then inspect the backend contract after Codex’s contract-freeze handoff. Read the relevant ECC guidance under `C:\Dev\Active Projects\Sharon Online\ECC-main\skills`, especially contract-first, api-design, react-patterns, frontend-patterns, react-testing, nextjs-turbopack, security-review, error-handling, verification-loop, and production-audit.
>
> Repair the visible behavior for F-01 through F-08: materials list/detail states and canonical slugs; Power Guard unavailable/stale/retry/authorization states without fabricated stages or polling noise; student schedule/history status and timezone display; attendance duration/disputed evidence; FX freshness and checkout blocking; tutor media pending/private/unavailable states; and normalized availability/DST/conflict presentation. Consume the frozen API contract; do not invent client-side persistence, prices, statuses, durations, media URLs, or provider data.
>
> Work tests-first with route/component/integration RED tests, then the smallest GREEN implementation. Cover loading, approved-empty, 401/403, 404, 409, 5xx, retry, cancellation/unmount, focus/error announcements, mobile/desktop behavior, and accessible labels. Do not convert an authorization or contract error into an empty catalog. Do not show a success state until the server confirms it.
>
> Run frontend tests, API/type checks, lint with zero warnings, build, accessibility checks, and authenticated browser acceptance for student, tutor, and admin. Update `docs/slices/antigravity-repair.md` and report exact evidence, unresolved backend/provider dependencies, and any required owner decision. Clearly separate focused/full-suite/browser/provider/staging/commit/push status.

### Prompt C — independent failure-verifier agent

> Read this exact plan and verify it against the current Sharon Online codebase and the original local browser evidence. Work read-only: no file edits, database mutations, bookings, payments, payouts, refunds, availability saves, provider calls, or credential/account actions. Read the authoritative project docs and relevant ECC skills. For every F-01 through F-08, confirm the evidence, affected route/code, classification, severity, smallest safe reproducer, and whether the proposed Codex/Antigravity ownership is correct. Flag missing failure modes, unsafe assumptions, missing tests, or overlaps. Return PASS/FAIL per section and concrete corrections only.

### Prompt D — plan/ECC reviewer agent

> Read this exact plan, the authoritative Sharon Online docs, and the relevant local ECC skills. Review the plan as an architecture, security, testing, migration, contract, and release-safety document. Confirm that it has two non-overlapping implementation tasks, explicit dependency order, tests-first evidence, safe rollback, provider/account boundaries, exact file ownership, Q0/full-suite/browser gates, and truthful reporting. Check for booking-state bypasses, timezone/DST errors, unsafe FX/media fallbacks, silent exception swallowing, migration drift, PII leakage, generated-contract drift, and false completion claims. Work read-only and return PASS/FAIL with required corrections.

## 12. Multi-agent sign-off

This section is completed only after every reviewer has read this exact file and returned a final report.

| Reviewer | Role | Status | Evidence/notes |
|---|---|---|---|
| Failure verifier | Re-trace F-01 through F-08 against code, tests, and local behavior. | PASS | Final review confirmed eight failures, concrete ownership, separate materials contracts, attendance bounds, and conditional F-08 handling. |
| Plan architect | Verify ownership, sequencing, prompts, gates, and integration boundaries. | PASS | Final review confirmed the Codex -> contract regeneration -> Antigravity sequence and no remaining correction. |
| ECC reviewer | Verify local ECC skills, security/testing/migration/contract guidance, and missing risks. | PASS | Final review confirmed coherent RED/GREEN, contract, security, migration, rollback, and isolated browser/API gates. |

**Implementation status:** No product code has been changed by this plan. Work begins only after the final sign-off row is complete and the two isolated worktrees are created.
