# Codex Implementation Plan: Slice T5b & Task 15.1

**Target Agent:** Codex  
**Assigned Tasks:**
1. **Slice T5b:** Tutor Application Funnel UI (`/teacher/apply` 5-step wizard)
2. **Task 15.1:** Wire Public Tutors Directory (`/tutors` & `/tutors/[id]`) to Live DRF API  
**Target Repository:** `Project-files/`  
**Base Branch:** `develop`  
**Suggested Feature Branch:** `feature/t5b-funnel-and-tutors-live`  
**Pre-allocated Error Blocks:** ERR-430 (for T5b), ERR-490 (for Task 15.1)

---

## 1. Collaboration & Quality Gate Rules (MANDATORY)
Before touching any code, review and uphold:
1. `docs/AI_AGENT_COLLABORATION_RULES.md`:
   - Never swallow exceptions; fix root causes.
   - Run `npm test` (`tsc + node --test`) and `npm run lint` (`eslint . --max-warnings 0`). Zero warnings allowed!
   - Log any unexpected errors in `docs/ERROR_LOGS_AND_RESOLUTIONS.md` using the pre-allocated ERR blocks.
   - Mark completed tasks in `docs/PROGRESS_AND_ROADMAP.md`.
2. Do not invent backend models or contracts; all shapes exist in:
   - `frontend/src/types/api.generated.ts`
   - `backend/apps/teachers/models.py`
   - `backend/apps/teachers/application.py`

---

## 2. Task 4: Slice T5b — Tutor Application Funnel UI (`/teacher/apply`)

### 2.1 Context & Backend Foundation (Slice T5a)
Slice T5a implemented the application backend and data model (`TeacherApplication`, `TeacherProfile.Status` machine).
The endpoints available on Django REST Framework are:
- `GET /api/v1/teachers/me/application/`: Returns the current application state, draft values, and step progress.
- `PATCH /api/v1/teachers/me/application/`: Autosaves application draft fields (bio, accent, specialties, speed test, power backup).
- `POST /api/v1/teachers/me/application/submit/`: Submits the completed application, transitioning tutor status from `applied` (or `changes_requested`) to `submitted`.
- `GET /api/v1/teachers/me/`: Returns tutor profile including `review_feedback` and `tutor_status`.
- `POST /api/v1/teachers/me/assets/commit/`: Commits uploaded assets from quarantine S3/R2 storage with ETag verification.

### 2.2 Requirements & UI Architecture
Build the complete 5-step application wizard on route `frontend/src/app/teacher/apply/page.tsx` (matching design specifications in `sharon-online-figma-v26` and `UI_VERTICAL_SLICE_MIGRATION_PLAN.md`):

1. **Step 1: Tutor Profile & Intro**:
   - Fields: Headline, bio, accent selector (e.g. Neutral, British, South African, American), specialties checkboxes (Business, IELTS, Conversational, Kids, etc.), primary teaching timezone.
   - Autosave via `PATCH /api/v1/teachers/me/application/`.

2. **Step 2: Media & Credential Uploads**:
   - 4 required asset kinds:
     - `avatar`: Profile picture (JPEG/PNG/WEBP).
     - `video_reel`: 60-second video introduction (MP4/WebM).
     - `audio_snippet`: 15-second clear audio sample (MP3/WebM/WAV).
     - `cv_tefl`: TEFL / TESOL / Degree certificate (PDF/PNG).
   - Use the presigned quarantine upload flow (`/api/v1/teachers/me/assets/presign/` or direct commit via `/api/v1/teachers/me/assets/commit/`).
   - If applicant has status `changes_requested`, highlight ONLY the upload kinds listed in `requested_changes` from `review_feedback`.

3. **Step 3: Eskom Power Backup Declaration**:
   - Hardware questions: Primary backup type (Inverter, Solar + Inverter, Portable Power Station / UPS, Generator).
   - Battery runtime hours during Stage 4 load shedding (minimum 4 hours required).
   - Secondary failover: Mobile LTE / 5G hotspot availability.
   - Checkbox: "I guarantee uninterrupted teaching during scheduled Eskom load shedding."

4. **Step 4: Live WebRTC Network Speed Test**:
   - Real browser-based speed test checking download and upload bandwidth against the Sharon Online media server / public test endpoint.
   - Requirement: $\ge 10$ Mbps download and $\ge 5$ Mbps upload.
   - Interactive gauge or progress indicator with "Run Speed Test" button.
   - Sends measured `speed_test_download_mbps` and `speed_test_upload_mbps` to `PATCH /api/v1/teachers/me/application/`.

5. **Step 5: Legal Declaration & Final Submission**:
   - Checkbox declarations: Accuracy of credentials, agreement to the Tutor Code of Conduct, agreement to 24-hour lesson memo SLA.
   - Final "Submit Application" button calling `POST /api/v1/teachers/me/application/submit/`.
   - On success: Show confirmation screen ("Application Under Review") and redirect to waiting state.

6. **Routing / Middleware Enforcement**:
   - Update `proxy.ts` (or `middleware.ts`) to ensure tutors with status `applied` or `changes_requested` trying to access `/teacher/dashboard` are smoothly redirected to `/teacher/apply`.

### 2.3 Verification & Tests
- Create `frontend/test/tutorApplication.test.ts` (using Node test runner `node --test`):
  - Test step validation (blocking progression if required fields are missing).
  - Test speed test threshold validation ($\ge 10/5$ Mbps).
  - Test draft autosave payload generation.
  - Test `changes_requested` feedback parsing.

---

## 3. Task 5: Task 15.1 — Wire Public Tutors Directory (`/tutors` & `/tutors/[id]`)

### 3.1 Context & Current State
- `frontend/src/app/(public)/tutors/page.tsx` and `frontend/src/app/(public)/tutors/[id]/page.tsx` currently render static mock tutor data (`MOCK_TUTORS`).
- The backend DRF endpoints already exist and are fully tested:
  - `GET /api/v1/teachers/`: Returns paginated list of active/approved teachers (`TeacherListView`). Supports search query, specialty filters, accent filter, page parameter.
  - `GET /api/v1/teachers/<uuid:id>/`: Returns single teacher detail (`TeacherDetailView`).
  - `GET /api/v1/bookings/slots/<uuid:teacher_id>/?start=<iso>&end=<iso>`: Returns projected open booking slots (`TeacherSlotsView`).
  - `POST /api/v1/bookings/reserve/`: Places 10-minute slot hold (`ReserveSlotView`).

### 3.2 Requirements & UI Updates
1. **Public Directory (`/tutors/page.tsx`)**:
   - Replace `MOCK_TUTORS` with real server/client data fetch using `api.getTeachers()` (or adding typed `fetchTutors()` in `lib/api.ts`).
   - Sync filter controls (`TutorFilters.tsx`) with DRF query parameters:
     - Search term (`search`)
     - Accent (`accent`)
     - Specialties (`specialties`)
     - Pagination (`page`, `page_size`)
   - Empty state: "No tutors found matching your criteria."
   - Keep fail-safe fallback: If API fails, handle gracefully without crashing the page.

2. **Tutor Showcase (`/tutors/[id]/page.tsx`)**:
   - Fetch single tutor details from `GET /api/v1/teachers/<id>/`.
   - Wire `VideoReelPlayer` and `AudioSnippetButton` to real media asset URLs.
   - Fetch real projected availability slots for the upcoming 7–14 days from `GET /api/v1/bookings/slots/<id>/`.
   - Wire `InlineSlotMatrix` to actual UTC slots projected into the user's localized browser timezone.
   - Connect slot selection to reservation modal calling `POST /api/v1/bookings/reserve/`.

3. **Verification & Tests**:
   - Create/update `frontend/test/tutorsDirectory.test.ts`:
     - Test search filter query param building.
     - Test localized slot formatting and slot selection.
     - Test fallback resilience.
   - Run `npm test`, `npm run lint`, `npm run build`.

---

## 4. Deliverables Checklist
- [ ] `/teacher/apply` 5-step wizard implemented with draft autosave and submission.
- [ ] Speed test and Eskom backup declarations wired to backend.
- [ ] Routing/middleware directs `applied`/`changes_requested` tutors to `/teacher/apply`.
- [ ] `/tutors` and `/tutors/[id]` wired to live Django REST API endpoints.
- [ ] Unit tests in `frontend/test/tutorApplication.test.ts` and `frontend/test/tutorsDirectory.test.ts` pass cleanly.
- [ ] `npm test` and `npm run lint` pass with 0 errors and 0 warnings.
- [ ] Documentation updated (`docs/slices/T5b.md`, `docs/PROGRESS_AND_ROADMAP.md`).
