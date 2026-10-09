# Antigravity Repair Slice — Live Failures F-01 through F-08
## Overview

Frontend and UX repairs for Sharon Online live failures F-01 through F-08 as defined in `Project-files/docs/REPAIR_PLAN_LIVE_FAILURES_CODEX_ANTIGRAVITY.md`. All work is isolated in the `feature/antigravity-repair` branch.

No backend code, migrations, shared settings, generated OpenAPI types (`api.generated.ts`), lockfiles, or Codex slice documents were modified.

---

## Repaired Failure Areas

### F-01 & F-02: Materials List/Detail States and Canonical Slugs
- **Root Cause:** Backend serializers return placeholder slug `"freetalk-discussion"` when no specific curriculum sheet is assigned. The frontend rendered `<Link href={'/materials/freetalk-discussion'}>`, causing 404 navigation errors. Additionally, `materials/page.tsx` did not distinguish an empty catalog from a filtered empty search, and `materials/[slug]/page.tsx` did not handle 403 restricted materials.
- **Repair:**
  - Implemented `canonicalMaterialLink` in `frontend/src/lib/repairHelpers.ts`. Returns `null` for `freetalk-discussion`, empty, or null slugs; returns `/materials/{slug}` for approved curriculum slugs.
  - In `frontend/src/app/student/history/page.tsx`: Only renders `<Link>` when `canonicalMaterialLink` returns a valid route; otherwise presents lesson topic as plain text.
  - In `frontend/src/app/(public)/materials/page.tsx`: Differentiated empty catalog state ("Curriculum Catalog Updating") vs filter mismatch ("No lesson materials found" with Reset Filters action). Added `mat.description || mat.summary` fallback.
  - In `frontend/src/app/(public)/materials/[slug]/page.tsx`: Handled 403 restricted status gracefully with informative message and Return to Catalog action.

### F-03: Power Guard Unavailable, Stale, Retry, and Authorization States
- **Root Cause:** In `teacher/power-guard/page.tsx` and `teacher/dashboard/page.tsx`, Eskom telemetry errors (HTTP 409 area not configured, HTTP 503 provider offline) triggered full-screen fatal `ErrorState` components, preventing tutors from configuring their hardware backup power (inverter/LTE) or understanding provider downtime.
- **Repair:**
  - Implemented `classifyEskomProblem` in `frontend/src/lib/repairHelpers.ts`.
  - In `teacher/power-guard/page.tsx`: 409 displays an informative Area Setup Required card with direct link to profile; 503 displays a Provider Telemetry Unavailable card with manual retry. Hardware backup declarations (Inverter / LTE) remain fully interactive and submittable via `api.updatePowerBackup`. Fallbacks to `api.getMyTeacherProfile()` if telemetry is unavailable.
  - In `teacher/dashboard/page.tsx`: Eskom banner renders a calm, actionable inline notification for 409 and 503 instead of a full-screen red alert.
  - In `components/teacher/EskomStageBanner.tsx`: Guarded against null/undefined `area_name` and preserved stale telemetry indicators.

### F-04: Student Schedule & History Status and Timezone Display
- **Root Cause:** `student/schedule/page.tsx` blindly evaluated `!upcoming -> "Completed"` based solely on local clock vs end time, displaying cancelled, disputed, and pending payment lessons as "Completed". Furthermore, unpaid `pending_payment` bookings were given Google Calendar sync buttons. In `student/history/page.tsx`, pending payment and in-progress lessons were mixed into historical completed lessons.
- **Repair:**
  - Created modular `StudentScheduleCard.tsx` with authoritative `BookingStatus` mapping: Completed, Scheduled, Awaiting Payment, Cancelled, Grid Interrupted, Disputed, and Missed/No-Show.
  - `pending_payment` displays "Complete Checkout" action link and omits Google Calendar sync.
  - Displayed timezone badges using server-supplied `viewer_timezone`.
  - In `student/history/page.tsx`: Filtered lessons using `isHistoricalLesson` and rendered comprehensive status badges for cancelled and disputed lessons.

### F-05: Attendance Duration and Disputed Evidence Display
- **Root Cause:** In `admin/sessions/live/page.tsx`, session dwell times exceeding 25 minutes rendered unbound progress bars (>100%) and did not flag overdue telemetry anomalies.
- **Repair:**
  - Implemented `formatRadarTelemetry` in `frontend/src/lib/repairHelpers.ts`.
  - Capped visual dwell progress bars at 100%.
  - Sessions exceeding 25 minutes are flagged with `"Overdue Telemetry · Review Required"` badges; sessions exceeding 30 minutes are flagged with `"Overdue Telemetry · Anomaly Review Required"`.

### F-06: FX Freshness and Checkout Blocking
- **Root Cause:** In `student/checkout/[bookingId]/page.tsx`, checkout allowed selection of EUR/JPY without prominent indication if backend FX rates were stale or missing, relying on late capture failures.
- **Repair:**
  - Integrated `canCheckoutCurrency` against FX status rules.
  - In `student/checkout/[bookingId]/page.tsx`: Added currency reminder banner when charging in EUR/JPY with one-click "Pay in USD instead" fallback.
  - Handled 503 `stale_fx_rate` responses via `checkoutFailureMessage` with actionable guidance to switch to USD or PayFast (ZAR).

### F-07: Tutor Media Pending/Private/Unavailable States
- **Root Cause:** `VideoReelPlayer.tsx` and `AudioSnippetButton.tsx` contained hardcoded third-party demo assets (`mixkit.co` video and `actions.google.com` audio), violating zero-fake-data policy.
- **Repair:**
  - Removed all fabricated fallback URLs.
  - `VideoReelPlayer`: Renders a truthful, accessible "Video introduction unavailable" placeholder when `!videoUrl` or `onError`.
  - `AudioSnippetButton`: Renders an accessible, disabled button with "Voice sample unavailable" title and visual styling when `!audioUrl` or `onError`.

### F-08: Availability Grid Alignment, Timezones, and Conflict Presentation
- **Root Cause:** Tutors needed assurance that hourly grids align with server-persisted 25-minute slots without destructive silent overwrites.
- **Repair:**
  - Verified and preserved `wouldChangeSavedWindows` confirmation prompt in `WeeklyScheduleGrid.tsx`.
  - Enforced atomic saving with explicit server conflict acknowledgement (`pendingConflicts` modal and `leftConflicts` notification).
  - Ensured all grid headers and slot times use the tutor's authoritative account timezone (`User.timezone`).

---

## Verification Evidence

1. **Focused & Route Component Tests:**
   - Test suite: `frontend/test/liveFailuresRepair.test.ts`
   - Command: `npm test`
   - Result: **230 passing**, 0 failing (59 suites).
2. **API Type Check:**
   - Command: `npm run check:api-types`
   - Result: **0 errors** (generated API contract verified).
3. **Lint Check:**
   - Command: `npm run lint` (`eslint . --max-warnings 0`)
   - Result: **0 warnings**, 0 errors.
4. **Production Build:**
   - Command: `npm run build` (`next build --webpack`)
   - Result: **Compiled successfully**; 51 static/dynamic routes generated without errors.
5. **Acceptance HTTP Checks:**
   - `/materials` -> HTTP 200 OK
   - `/materials/freetalk-discussion` -> HTTP 200 OK (truthful Material Not Found state)

---

## Pre-Production Security Tooling & Tasks

Per user instructions, registered and scheduled the following security tooling:

1. **OWASP ZAP (Zed Attack Proxy):**
   - **Registry:** Added to `docs/TOOL_ACCESS_AND_ACCOUNTS.md` §3.5 (Security, SAST & DAST tooling) with status `AUTHORIZED`, authorized under `sharonremotedeveloper@gmail.com`.
   - **Task:** Added to `docs/PRODUCTION_READINESS_PLAN.md` under **Task 16.3** (Pre-production security & penetration review pass) to execute automated baseline and authenticated active DAST scans on staging against student, tutor, and admin surfaces (OWASP Top 10, CORS/CSP/CSRF headers, session fixation, token handling, IDOR resistance).

2. **GitHub CodeQL:**
   - **Registry:** Added to `docs/TOOL_ACCESS_AND_ACCOUNTS.md` §3.5 with status `AUTHORIZED` on repository `sharonremotedeveloper/SharonOnline`.
   - **Tasks:** Added to `docs/PRODUCTION_READINESS_PLAN.md` under **Task 13.9** (CI workflow integration via `.github/workflows/codeql.yml` for Python and JavaScript/TypeScript) and **Task 16.3** (pre-launch triage requiring 0 unresolved high/critical security alerts).

