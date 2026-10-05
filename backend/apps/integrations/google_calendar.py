import secrets
import hashlib
from urllib.parse import urlencode
import requests
import logging
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction
from apps.common.crypto import decrypt_integration_secret, encrypt_integration_secret
from .models import CalendarCredential, CalendarOAuthState

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'  # noqa: S105 - endpoint, not a secret
GOOGLE_REVOKE_URL = 'https://oauth2.googleapis.com/revoke'


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
        local_mode = settings.DEBUG or getattr(settings, 'ZOOM_SIMULATE_WITHOUT_CREDENTIALS', False)
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


def fetch_freebusy(user, time_min, time_max):
    """Return Google primary-calendar busy intervals for the requested UTC window."""
    access_token = _access_token(user)
    if not access_token:
        raise RuntimeError('Google Calendar is not connected.')
    response = requests.post(
        'https://www.googleapis.com/calendar/v3/freeBusy',
        headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
        json={'timeMin': time_min.isoformat(), 'timeMax': time_max.isoformat(),
              'items': [{'id': 'primary'}]}, timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError(f'Google Calendar free/busy failed: HTTP {response.status_code}')
    calendars = response.json().get('calendars') or {}
    return calendars.get('primary', {}).get('busy') or []


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
    local_mode = settings.DEBUG or getattr(settings, 'ZOOM_SIMULATE_WITHOUT_CREDENTIALS', False)
    legacy = getattr(user, 'google_calendar_token', None) or {}
    return legacy.get('access_token') if local_mode and isinstance(legacy, dict) else None

def sync_booking_to_teacher_gcal(booking) -> str:
    """
    Inserts a confirmed booking onto the teacher's connected Google Calendar via Google Calendar API v3.
    Returns the Google Calendar event ID if successful. It does NOT save the booking: the caller stores the id under the
    booking's row lock (bookings/services/fulfillment.py), so a stale instance can never overwrite a cancel or a reschedule.
    """
    access_token = _access_token(booking.teacher.user)
    if not access_token:
        logger.info(f"Teacher {booking.teacher.user.username} does not have Google Calendar connected. Skipping sync.")
        return ""

    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    event_body = {
        "summary": f"Sharon ESL: Lesson with {booking.student.first_name or booking.student.username}",
        # Join link only (Slice Z1): the host link expires; the tutor opens the classroom page for a fresh one.
        "description": f"25-minute lesson.\n\nZoom join link: {booking.zoom_join_url}\n"
                       f"Start the lesson as host from your Sharon ESL classroom page.",
        "start": {
            "dateTime": booking.start_time_utc.isoformat(),
            "timeZone": "UTC"
        },
        "end": {
            "dateTime": booking.end_time_utc.isoformat(),
            "timeZone": "UTC"
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 10},
                {"method": "email", "minutes": 30}
            ]
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=event_body, timeout=10)
        if resp.status_code in [200, 201]:
            event_id = resp.json().get('id', '')
            logger.info(f"Successfully synced to Google Calendar event_id={event_id}")
            return event_id
        else:
            logger.warning(f"Google Calendar sync error: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to communicate with Google Calendar API: {e}")

    return ""


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
