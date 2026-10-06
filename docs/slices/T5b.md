# Slice T5b — Tutor Application Funnel UI (`/teacher/apply`)

Branch: `feature/t5b-funnel-and-tutors-live` · ERR block: 430 · dependency: T5a.

## Overview
Builds the 5-step tutor application wizard on `frontend/src/app/teacher/apply/page.tsx` consuming the T5a API:
- `GET|PATCH /api/v1/teachers/me/application/`
- `POST /api/v1/teachers/me/application/submit/`
- `GET /api/v1/teachers/me/` (`review_feedback` for `changes_requested` tutors)
- `POST /api/v1/teachers/me/assets/commit/`

## Key Components
1. Step 1: Profile & Intro (bio, accent, specialties, timezone).
2. Step 2: Media & Credential uploads (`avatar`, `video_reel`, `audio_snippet`, `cv_tefl`).
3. Step 3: Eskom power backup declaration (inverter, runtime, LTE failover).
4. Step 4: WebRTC network speed test ($\ge 10$ Mbps down / $\ge 5$ Mbps up).
5. Step 5: Code of conduct & legal declaration + final submission.
6. Edge middleware redirect for `applied`/`changes_requested` tutors to `/teacher/apply`.
7. Full tests in `frontend/test/tutorApplication.test.ts`.
