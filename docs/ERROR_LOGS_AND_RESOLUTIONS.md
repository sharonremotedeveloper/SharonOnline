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
