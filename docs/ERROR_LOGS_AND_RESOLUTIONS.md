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
