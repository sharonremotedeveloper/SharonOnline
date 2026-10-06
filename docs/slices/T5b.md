# Slice T5b — Tutor Application Funnel UI (`/teacher/apply`)

Branch: `feature/t5b-funnel-and-tutors-live` · ERR block: 430 · dependency: T5a · status: implemented.

## Overview
Builds the 5-step tutor application wizard on `frontend/src/app/teacher/apply/page.tsx` consuming the T5a API:
- `GET|PATCH /api/v1/teachers/me/application/`
- `POST /api/v1/teachers/me/application/submit/`
- `GET /api/v1/teachers/me/` (`review_feedback` for `changes_requested` tutors)
- `POST /api/v1/teachers/me/assets/commit/`

## Key Components
1. Step 1: Profile & Intro (bio, accent, specialties, timezone).
2. Step 2: Media & credential uploads using backend-provided required asset kinds, presigned quarantine upload, and commit.
3. Step 3: Eskom power backup declaration (inverter and LTE failover flags, plus application confirmation).
4. Step 4: Browser network speed test ($\ge 10$ Mbps down / $\ge 5$ Mbps up).
5. Step 5: Code of conduct & legal declaration + final submission.
6. Edge middleware redirect for `applied`/`changes_requested` tutors to `/teacher/apply`.
7. Full tests in `frontend/test/tutorApplication.test.ts`.

Implementation note: T5a deliberately makes `accent`, runtime, and primary backup type non-writable through the application/profile PATCH contracts. The UI collects the supported backup declarations without sending unsupported fields; vetted identity/accent changes remain in the asset/reviewer flow.

Verification: `npm test` (191/191), `npm run lint` (zero warnings), and `npm run build` passed on 2026-10-06.
