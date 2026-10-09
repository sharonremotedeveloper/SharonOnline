import secrets
import hashlib
from datetime import date, time, timedelta, timezone as dt_timezone
from urllib.parse import urlencode
import requests
import logging
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from apps.bookings.services.classroom_links import classroom_url
from apps.common import clock
from apps.common.crypto import decrypt_integration_secret, encrypt_integration_secret
from apps.teachers.services.schedule import InvalidTeacherTimezone, boundary_utc, teacher_zone
from .models import CalendarCredential, CalendarOAuthState

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'  # noqa: S105 - endpoint, not a secret
GOOGLE_REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
GOOGLE_CALENDAR_URL = 'https://www.googleapis.com/calendar/v3'

UTC = dt_timezone.utc
# Private extended property stamped on every lesson event we create; the busy hint ignores events that carry it.
OWN_EVENT_MARKER = 'sharon_booking_id'
EVENTS_PAGE_SIZE, EVENTS_MAX_PAGES = 250, 8
BUSY_CACHE_TTL = 7200       # the 30-minute refresh keeps it warm; a dead sync lets it lapse after two hours


def oauth_authorization_url(user):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_OAUTH_REDIRECT_URI:
        raise RuntimeError('Google Calendar OAuth is not configured.')
    state = secrets.token_urlsafe(32)
    digest = hashlib.sha256(state.encode()).hexdigest()
    CalendarOAuthState.objects.create(
        state_hash=digest, user=user,
        expires_at=timezone.now() + timezone.timedelta(seconds=settings.GOOGLE_OAUTH_STATE_TTL),
    )
    # Cache is retained only as a short-lived lookup hint for older deployments.
    cache.set(f'gcal:oauth:{state}', str(user.pk), timeout=settings.GOOGLE_OAUTH_STATE_TTL)
    params = {'client_id': settings.GOOGLE_CLIENT_ID, 'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
              'response_type': 'code', 'access_type': 'offline', 'prompt': 'consent', 'state': state,
              'scope': ' '.join(settings.GOOGLE_CALENDAR_SCOPES)}
    return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'


def oauth_state_user(state):
    row = CalendarOAuthState.objects.filter(
        state_hash=hashlib.sha256(state.encode()).hexdigest(),
        expires_at__gt=timezone.now(), used_at__isnull=True,
    ).select_related('user').first()
    if row is None:
        raise ValueError('Invalid or expired Google OAuth state.')
    return row.user


def consume_oauth_state(user, state):
    """Consume a callback nonce exactly once, including declined/error callbacks."""
    digest = hashlib.sha256(state.encode()).hexdigest()
    cached_owner = cache.get(f'gcal:oauth:{state}')
    with transaction.atomic():
        updated = CalendarOAuthState.objects.filter(
            state_hash=digest, user=user, expires_at__gt=timezone.now(), used_at__isnull=True,
        ).update(used_at=timezone.now())
    cache.delete(f'gcal:oauth:{state}')
    if updated != 1:
        # Compatibility for pre-migration local fixtures only; production state is DB-backed.
        local_mode = settings.DEBUG or getattr(settings, 'SIMULATE_WITHOUT_CREDENTIALS', False)
        cached_owner = cached_owner if local_mode else None
        if str(cached_owner) != str(user.pk):
            raise ValueError('Invalid or expired Google OAuth state.')


def exchange_oauth_code(user, code, state):
    if not code:
        raise ValueError('Missing Google OAuth code.')
    consume_oauth_state(user, state)
    response = requests.post(GOOGLE_TOKEN_URL, data={'code': code, 'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET, 'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'grant_type': 'authorization_code'}, timeout=10)
    if response.status_code not in (200, 201):
        raise ValueError('Google declined the OAuth exchange.')
    payload = response.json()
    refresh = payload.get('refresh_token')
    if not refresh:
        raise ValueError('Google did not return a refresh token; reconnect with consent.')
    CalendarCredential.objects.update_or_create(user=user, defaults={
        'refresh_token_enc': encrypt_integration_secret(refresh),
        'scopes': payload.get('scope', '').split() or list(settings.GOOGLE_CALENDAR_SCOPES),
        'revoked_at': None, 'last_error': '',
    })
    # The legacy JSON field must never retain OAuth tokens after G1.
    if getattr(user, 'google_calendar_token', None):
        user.google_calendar_token = None
        user.save(update_fields=['google_calendar_token'])
    return True


class CalendarUnavailable(RuntimeError):
    """Google could not be asked (not connected, token refused, throttled, 5xx). Callers degrade to "no hiding"."""


def busy_cache_key(teacher_id) -> str:
    return f'gcal:busy:{teacher_id}'


def _event_makes_tutor_busy(event: dict) -> bool:
    """Opaque, live events the tutor is attending, and not one of our own lesson events (private marker)."""
    if event.get('status') == 'cancelled' or event.get('transparency') == 'transparent':
        return False
    if event.get('eventType') == 'workingLocation':
        return False
    if (event.get('extendedProperties') or {}).get('private', {}).get(OWN_EVENT_MARKER):
        return False
    return not any(a.get('self') and a.get('responseStatus') == 'declined' for a in event.get('attendees') or [])


def _event_interval(event: dict, zone):
    """(start_utc, end_utc) of an event; an all-day event spans the tutor's local days. None when it cannot be read."""
    start, end = event.get('start') or {}, event.get('end') or {}
    if 'dateTime' in start and 'dateTime' in end:
        first, last = parse_datetime(start['dateTime']), parse_datetime(end['dateTime'])
    elif 'date' in start and 'date' in end:
        first, last = (boundary_utc(date.fromisoformat(side['date']), time.min, zone) for side in (start, end))
    else:
        return None
    if first is None or last is None or first >= last:
        return None
    return first.astimezone(UTC), last.astimezone(UTC)


def fetch_external_busy(user, time_min, time_max, zone):
    """
    The tutor's own busy intervals on their primary calendar in [time_min, time_max): events.list, not freeBusy.query,
    because freeBusy cannot tell our lesson events from the tutor's own. Raises CalendarUnavailable on any provider problem.
    """
    access_token = _access_token(user)
    if not access_token:
        raise CalendarUnavailable('Google Calendar is not connected or refused the stored grant.')
    params = {'timeMin': time_min.isoformat(), 'timeMax': time_max.isoformat(), 'singleEvents': 'true',
              'showDeleted': 'false', 'maxResults': EVENTS_PAGE_SIZE,
              'fields': 'nextPageToken,items(id,status,transparency,eventType,start,end,attendees(self,responseStatus),'
                        'extendedProperties/private)'}
    intervals = []
    for _page in range(EVENTS_MAX_PAGES):
        try:
            response = requests.get(f'{GOOGLE_CALENDAR_URL}/calendars/primary/events', params=params,
                                    headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
        except requests.RequestException as exc:
            raise CalendarUnavailable(f'Google Calendar request failed: {type(exc).__name__}') from exc
        if response.status_code != 200:
            raise CalendarUnavailable(f'Google Calendar events.list failed: HTTP {response.status_code}')
        body = response.json()
        for event in body.get('items') or []:
            interval = _event_interval(event, zone) if _event_makes_tutor_busy(event) else None
            if interval:
                intervals.append(interval)
        if not body.get('nextPageToken'):
            return intervals
        params['pageToken'] = body['nextPageToken']
    logger.warning('Google Calendar events.list for user %s exceeded %s pages; the busy hint is partial',
                   user.pk, EVENTS_MAX_PAGES)
    return intervals


def external_busy_intervals(teacher):
    """
    The cached busy hint for the PUBLIC slot listing as (start_utc, end_utc) pairs. Empty unless the tutor has an active
    connection and left "block my busy times" on (read live, so turning it off takes effect at once). A cache that cannot be
    read hides nothing.
    """
    if not CalendarCredential.objects.filter(user_id=teacher.user_id, revoked_at__isnull=True, block_busy=True).exists():
        return []
    try:
        cached = cache.get(busy_cache_key(teacher.id)) or []
    except Exception:       # a cache outage must not take the listing down: the hint is optional by design
        logger.warning('Busy-hint cache unreadable for teacher %s; listing without it', teacher.id)
        return []
    intervals = []
    for start, end in cached:
        first, last = parse_datetime(str(start)), parse_datetime(str(end))
        if first and last and first < last:
            intervals.append((first, last))
    return intervals


def refresh_busy_hint(teacher) -> str:
    """Re-read one tutor's busy times into the cache. Returns what happened; never raises for a Google problem."""
    credential = CalendarCredential.objects.filter(user_id=teacher.user_id, revoked_at__isnull=True).first()
    if credential is None:
        cache.delete(busy_cache_key(teacher.id))
        return 'not_connected'
    if not credential.block_busy:
        cache.set(busy_cache_key(teacher.id), [], timeout=BUSY_CACHE_TTL)
        return 'opted_out'
    now = clock.now()
    try:
        intervals = fetch_external_busy(teacher.user, now, now + timedelta(days=settings.BOOKING_HORIZON_DAYS + 1),
                                        teacher_zone(teacher))
    except (CalendarUnavailable, InvalidTeacherTimezone) as exc:
        # Keep the last good hint (it expires by itself): a throttled hour must not flip every slot back and forth.
        logger.warning('Google Calendar busy hint not refreshed for teacher %s: %s', teacher.id, exc)
        return 'unavailable'
    cache.set(busy_cache_key(teacher.id), [(a.isoformat(), b.isoformat()) for a, b in intervals], timeout=BUSY_CACHE_TTL)
    return 'ok'


def disconnect_calendar(user):
    credential = CalendarCredential.objects.filter(user=user, revoked_at__isnull=True).first()
    if credential:
        try:
            requests.post(GOOGLE_REVOKE_URL, params={'token': decrypt_integration_secret(credential.refresh_token_enc)}, timeout=10)
        except Exception:
            logger.warning('Google revoke request failed for user %s', user.pk)
        credential.revoked_at = timezone.now()
        credential.save(update_fields=['revoked_at'])
    return True


def _access_token(user):
    credential = CalendarCredential.objects.filter(user=user, revoked_at__isnull=True).first()
    if credential:
        try:
            refresh = decrypt_integration_secret(credential.refresh_token_enc)
            response = requests.post(GOOGLE_TOKEN_URL, data={'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET, 'refresh_token': refresh,
                'grant_type': 'refresh_token'}, timeout=10)
            if response.status_code == 200:
                return response.json().get('access_token')
            if response.status_code in (400, 401):
                credential.revoked_at = timezone.now()
                credential.last_error = 'invalid_grant'
                credential.save(update_fields=['revoked_at', 'last_error'])
        except Exception:
            logger.exception('Google Calendar token refresh failed for user %s', user.pk)
        return None
    # Local/test fixtures may still use the pre-G1 field; production never reads it.
    local_mode = settings.DEBUG or getattr(settings, 'SIMULATE_WITHOUT_CREDENTIALS', False)
    legacy = getattr(user, 'google_calendar_token', None) or {}
    return legacy.get('access_token') if local_mode and isinstance(legacy, dict) else None

def _lesson_event_body(booking) -> dict:
    return {
        "summary": f"Sharon ESL: Lesson with {booking.student.first_name or booking.student.username}",
        "description": f"25-minute lesson.\n\nOpen your classroom: {classroom_url(booking, 'teacher')}",
        "start": {"dateTime": booking.start_time_utc.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": booking.end_time_utc.isoformat(), "timeZone": "UTC"},
        "extendedProperties": {"private": {OWN_EVENT_MARKER: str(booking.id)}},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 10}, {"method": "email", "minutes": 30}],
        },
    }


def sync_booking_to_teacher_gcal(booking) -> str:
    """
    Puts a confirmed booking on the teacher's Google Calendar and returns the event id ('' on failure). It does NOT save the
    booking: the caller stores the id under the booking's row lock (bookings/services/fulfillment.py), so a stale instance can
    never overwrite a cancel or a reschedule.

    A booking that already has an event (a rescheduled lesson) UPDATES it, so the id survives the move and the tutor's invitation
    list and notes stay; if the tutor deleted it (404/410) a new event is created and its new id is returned.
    """
    access_token = _access_token(booking.teacher.user)
    if not access_token:
        logger.info("Teacher %s does not have Google Calendar connected. Skipping sync.", booking.teacher.user_id)
        return ""

    base = f"{GOOGLE_CALENDAR_URL}/calendars/primary/events"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    body = _lesson_event_body(booking)
    event_id = None
    try:
        updated_in_place = False
        if booking.teacher_gcal_event_id:
            resp = requests.patch(f"{base}/{booking.teacher_gcal_event_id}", headers=headers, json=body, timeout=10)
            if resp.status_code == 200:
                event_id, updated_in_place = resp.json().get('id', booking.teacher_gcal_event_id), True
            elif resp.status_code in (404, 410):
                logger.info("Google Calendar event for booking %s was deleted by the tutor; creating a new one", booking.id)
            else:
                logger.warning("Google Calendar update error: HTTP %s", resp.status_code)
                updated_in_place = True          # a real error, not "gone": do not create a duplicate
        if not updated_in_place:
            resp = requests.post(base, headers=headers, json=body, timeout=10)
            if resp.status_code in [200, 201]:
                event_id = resp.json().get('id', '')
                logger.info("Successfully synced to Google Calendar event_id=%s", event_id)
            else:
                logger.warning("Google Calendar sync error: HTTP %s", resp.status_code)
    except Exception as e:
        logger.error("Failed to communicate with Google Calendar API: %s", type(e).__name__)

    return event_id or ""


def delete_teacher_gcal_event(user, event_id: str) -> bool:
    """Remove a lesson from the tutor's Google Calendar (lesson cancelled or moved). Returns False when there was nothing to do."""
    access_token = _access_token(user)
    if not (event_id and access_token):
        return False
    resp = requests.delete(f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                           headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    if resp.status_code in (200, 204, 404, 410):       # already gone counts as done
        return True
    raise RuntimeError(f"Google Calendar refused to delete event {event_id}: HTTP {resp.status_code}")
