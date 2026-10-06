# Antigravity Implementation Plan: Slice F2 & Slice T4b

**Author:** Antigravity (Gemini)  
**Assigned Slices:**
1. **Slice F2:** In-App Notification Centre UI
2. **Slice T4b:** Admin Tutor Vetting Studio UI (4-Criterion Rubric & Review Packet)  
**Target Repository:** `Project-files/`  
**Base Branch:** `develop` (commit `e2da5bf`)

---

## Part 1: Slice F2 — In-App Notification Centre UI

### 1. Objective & Scope
Provide a real-time, accessible notification centre in Sharon Online's Next.js 16 App Router frontend. Users (students, teachers, admins) need immediate awareness of booking confirmations, reminders (T-24h, T-1h, T-10m), reschedule/cancellation events, and administrative alerts.

### 2. Backend Contract (Slice N1b)
The backend DRF API is live at:
- `GET /api/v1/notifications/`: Paginated notifications for authenticated user (`in_app=True`, ordered `-created_at`).
- `GET /api/v1/notifications/unread-count/`: Returns `{ "count": number }`.
- `POST /api/v1/notifications/<uuid:pk>/read/`: Marks single notification as read; returns updated Notification object.
- `POST /api/v1/notifications/read-all/`: Marks all unread in-app notifications as read; returns `{ "updated": number }`.
- `GET|PATCH /api/v1/notifications/preferences/`: Reads and updates user notification preferences.

### 3. Frontend Architecture & Components
1. **API Client Additions (`frontend/src/lib/api.ts`)**:
   - `getNotifications(page?: number, pageSize?: number)`
   - `getUnreadNotificationCount()`
   - `markNotificationRead(id: string)`
   - `markAllNotificationsRead()`
   - `getNotificationPreferences()`
   - `updateNotificationPreferences(data: PatchedNotificationPreferenceRequest)`
   - Strong typing imported directly from `@/types/api.generated`.

2. **State Management & Hook (`frontend/src/hooks/useNotifications.ts`)**:
   - Manages notifications list, unread count, loading, and error states.
   - **Visibility-Aware Jittered Polling**:
     - Polls `unread-count/` every 45s ± 10s jitter when tab is focused (`document.visibilityState === 'visible'`).
     - Immediately pauses polling when tab is blurred or hidden.
     - Refreshes on tab re-focus.
   - Optimistic state updates on mark-as-read and mark-all-read.

3. **UI Components (`frontend/src/components/notifications/`)**:
   - `NotificationBell.tsx`:
     - Renders in `Navbar.tsx` beside the user avatar.
     - Animated badge indicator showing unread count ($>99$ capped at `99+`).
     - Accessible button (`aria-label`, `aria-expanded`, keyboard trigger).
     - Toggles `NotificationDrawer.tsx`.
   - `NotificationDrawer.tsx`:
     - Flyout or dropdown panel with backdrop dismissal.
     - Header with "Mark all as read" button and link/icon to open preferences.
     - List of notification items:
       - Category badge/icon (booking, reminder, payment, alert).
       - Title, body, timestamp (relative format: "5m ago", "2h ago").
       - Deep-link action button if `action_url` or booking link is present.
       - Unread visual pip/highlight.
       - Click to mark read and navigate.
     - Empty state ("All caught up! No new notifications.").
     - Pagination / "Load more" trigger.
   - `NotificationPreferencesModal.tsx`:
     - Modal allowing toggle of email vs in-app notifications per category.
     - Displays mandatory lock on required categories (e.g., booking confirmations).

4. **Navbar Integration (`frontend/src/components/Navbar.tsx`)**:
   - Mount `NotificationBell` for authenticated users across student, teacher, and admin sessions.
   - Responsive design: compact display on mobile drawer menu.

### 4. Verification & Testing
- Node test runner suite `frontend/test/notifications.test.ts`:
  - Unit tests for notification formatting, relative time calculation, unread count capping.
  - Test mark-read and mark-all-read API calling logic and payload validation.
  - Test visibility polling pause/resume behavior.
- Lint and typecheck: `npm run lint` (zero warnings), `npm test` passing, `npm run build` compiling cleanly.

---

## Part 2: Slice T4b — Admin Tutor Vetting Studio UI

### 1. Objective & Scope
Upgrade `/admin/teachers/vetting` to consume the 4-criterion 1–5 rubric scoring engine, asset integrity checks (ETags), and review packet endpoint created in Slice T4a.

### 2. Backend Contract (Slice T4a & T1b)
- `GET /api/v1/admin/teachers/<uuid:pk>/review-packet/`:
  - Returns applicant profile, bio, accent, specialties, speed test results, power backup declaration.
  - Returns uploaded assets: `[{ kind, etag, content_type, size_bytes, uploaded_at }]`.
  - Returns rubric metadata: `criteria: ["english_proficiency", "teaching_methodology", "tech_environment", "curriculum_alignment"]`, `min_score: 3` (minimum 12/20 total).
  - Returns application status history.
- `POST /api/v1/admin/teachers/<uuid:pk>/start-review/`: Moves applicant from `submitted` to `in_review`.
- `POST /api/v1/admin/teachers/<uuid:pk>/approve/`:
  - Payload: `{ rubric: { [criterion]: score }, reviewed_assets: { [kind]: etag }, reason?: string }`.
  - Enforces all criteria $\ge 3$, total $\ge 12$, and asset ETags match live assets.
- `POST /api/v1/admin/teachers/<uuid:pk>/request-changes/`:
  - Payload: `{ reason: string, requested_changes: string[] }`.
  - Requires non-blank reason and array of asset kinds to redo (e.g. `["video_reel", "audio_snippet"]`).
- `POST /api/v1/admin/teachers/<uuid:pk>/reject/`:
  - Payload: `{ reason: string }`. Requires non-blank formal reason.

### 3. Frontend Architecture & Page Overhaul
1. **API Client Additions (`frontend/src/lib/api.ts`)**:
   - `getTeacherReviewPacket(id: string): Promise<ReviewPacket>`
   - `startTeacherReview(id: string)`
   - `approveTeacherWithRubric(id: string, payload: ApproveTeacherPayload)`
   - `requestTeacherChanges(id: string, reason: string, requestedChanges: string[])`
   - `rejectTeacherApplication(id: string, reason: string)`

2. **Vetting Studio View (`frontend/src/app/admin/teachers/vetting/page.tsx`)**:
   - Split-screen layout:
     - Left pane: Queue of pending tutors (with status badges: `submitted`, `in_review`).
     - Right pane: Active Review Packet Inspector & Rubric Studio.
   - **Review Packet Inspector**:
     - Candidate identity, bio, accent, specialties.
     - Media player for video reel and audio snippet.
     - Document preview/download links for TEFL/credentials.
     - Hardware & readiness badge: WebRTC download/upload Mbps and Eskom power backup status.
     - Application audit history log.
   - **Interactive Rubric Scoring Form**:
     - 4 sliders or 1–5 star/radio selectors for each rubric criterion.
     - Live total score counter with visual passing indicator ($\ge 12/20$ green, $<12$ red).
     - Invalidation alert if any individual score is $<3$.
     - Live reviewed asset ETag mapping automatically pinned from current packet.
   - **Action Modals**:
     - **Approve Modal**: Confirmation summary showing final score and reviewed asset fingerprints.
     - **Request Changes Modal**: Checkboxes for upload kinds (`avatar`, `video_reel`, `audio_snippet`, `cv_tefl`), required feedback textarea explaining what the tutor needs to correct.
     - **Reject Modal**: Formal rejection reason textarea.

### 4. Verification & Testing
- Node test runner suite `frontend/test/vettingStudio.test.ts`:
  - Unit tests asserting rubric calculation: total score, passing threshold validation ($\ge 12$ and each $\ge 3$).
  - Request payload structure test: ensures `reviewed_assets` ETag dictionary matches required schema.
  - Error state handling for 400 Bad Request (missing reasons or low rubric score).
- Full gate: `npm run lint` (zero warnings), `npm test` passing, `npm run build` compiling cleanly.
