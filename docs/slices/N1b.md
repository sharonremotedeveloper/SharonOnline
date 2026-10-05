# Slice N1b — notification API and preferences

Branch: `feature/n1b-notification-api` · ERR block: 250 · dependency: N1a.

## Delivered

- Owner-scoped, paginated `GET /api/v1/notifications/` (in-app rows only).
- `GET /api/v1/notifications/unread-count/`.
- `POST /api/v1/notifications/<uuid>/read/` and `POST /api/v1/notifications/read-all/`.
- `GET|PATCH /api/v1/notifications/preferences/` with typed serializers.
- Mandatory notification categories are enforced in the serializer; optional categories may be disabled per channel.
- `email_last_error` is omitted for non-staff and visible only to staff.
- Foreign notification ids return 404, avoiding an ownership oracle.

## Integrator snippets (Claude owns shared files)

### `backend/config/urls.py`

```python
path('api/v1/notifications/', include('apps.notifications.urls')),
```

The branch intentionally does not edit the shared root URL configuration.

### `backend/config/settings/base.py`

No new setting is required by the API implementation. N1a already provides the notifications app, pagination default, and notification delivery settings. Keep the existing `apps.notifications` entry in `INSTALLED_APPS`.

### `backend/config/celery_schedule.py`

No new task is introduced by N1b. Keep N1a's existing notification routes and beat entries unchanged:

```python
'apps.notifications.tasks.deliver_notification_task': {'queue': 'notifications'},
'apps.notifications.tasks.sweep_notifications_task': {'queue': 'notifications'},
'apps.notifications.tasks.purge_notifications_task': {'queue': 'notifications'},
```

## Tests and verification

Red-first API tests are in `backend/tests/test_notifications_api.py`. They cover pagination, owner-only 404s, read transitions, unread counts, preference enforcement, and staff-only delivery error visibility. The configured repository venv could not launch on this host because its embedded Python 3.12 executable is missing; run the focused and full gates in CI or after repairing that runtime.

No Resend or other external service was called.

## N2a-c seam

N2a-c must call `apps.bookings.services.classroom_links.classroom_url(booking, role)` for every reminder, confirmation, cancellation, reschedule, and calendar join link. It must not read or emit `booking.zoom_join_url` or any legacy Zoom meeting URL.
