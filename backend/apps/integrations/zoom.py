"""
Zoom Server-to-Server OAuth client (Slice F0 + Z1; contract in docs/ZOOM_ATTENDANCE.md "Client contract").

* Credentials are Django settings (ZOOM_ACCOUNT_ID / ZOOM_CLIENT_ID / ZOOM_CLIENT_SECRET); production refuses to boot without
  them. Simulated rooms only without credentials AND ZOOM_SIMULATE_WITHOUT_CREDENTIALS AND DEBUG (local settings).
* Bearer tokens come from `zoom_auth.cached_token` (per account, single-flight). A 401 invalidates the token and the request
  is sent once more with a fresh one.
* Retries: only 429 (Retry-After honoured up to ZOOM_RETRY_AFTER_CAP_SECONDS; a longer one is handed to the caller as
  `ZoomError.retry_after_seconds`) and 5xx (full-jitter exponential back-off), at most ZOOM_HTTP_MAX_ATTEMPTS tries. Other
  4xx are final. A timeout / connection error is final for reads (`ZoomAmbiguous`; the caller retries later).
* `create_meeting` is not idempotent at Zoom, so an ambiguous outcome (timeout, connection error, 5xx) is never retried blind:
  the host's scheduled meetings are searched for the booking's agenda marker first (`find_meeting_for_booking`).
* The host start link (ZAK) expires: it is never returned by create and never stored; `get_start_url` fetches a fresh one.
* Errors and logs carry ids and HTTP statuses only, never a provider body, token or URL with a ZAK.
"""
import base64
import hashlib
import hmac
import logging
import random
import re
import time
import uuid
from collections.abc import Mapping
from email.utils import parsedate_to_datetime

import requests
from django.conf import settings

from apps.integrations import zoom_auth

logger = logging.getLogger(__name__)

API = 'https://api.zoom.us/v2'
TOKEN_URL = 'https://zoom.us/oauth/token'  # noqa: S105 - the OAuth endpoint URL, not a secret
BACKOFF_BASE_SECONDS = 0.5
SEARCH_PAGE_SIZE = 300
SEARCH_MAX_PAGES = 10
_HOST_ID = re.compile(r'[A-Za-z0-9_.@+-]{1,64}')


def _sleep(seconds):
    time.sleep(seconds)


class ZoomError(Exception):
    """Zoom refused or failed a request we made. `status` is the HTTP status (None for a transport failure);
    `retry_after_seconds` is set when Zoom asked us to wait longer than we may sleep inline."""

    def __init__(self, message, *, status=None, retry_after_seconds=None):
        super().__init__(message)
        self.status, self.retry_after_seconds = status, retry_after_seconds


class ZoomNotFound(ZoomError):
    """Zoom does not have that meeting (404)."""


class ZoomAmbiguous(ZoomError):
    """Timeout / connection failure: Zoom may or may not have processed the request."""


def booking_marker(booking_id) -> str:
    """Deterministic line in a lesson meeting's agenda: finds the meeting of an earlier, ambiguous create."""
    return f'sharon-booking:{booking_id}'


def backoff_seconds(attempt: int) -> float:
    """Full jitter: uniform in [0, base * 2^(attempt-1)], capped; never 0 so a retry is never a tight loop."""
    ceiling = min(BACKOFF_BASE_SECONDS * 2 ** max(attempt - 1, 0), settings.ZOOM_RETRY_AFTER_CAP_SECONDS)
    return max(random.uniform(0, ceiling), 0.05)  # noqa: S311 - spreads retry timing only, not a security value


def parse_retry_after(resp):
    """Retry-After in seconds (delta-seconds or an HTTP date), or None when absent / unreadable / negative."""
    headers = getattr(resp, 'headers', None)
    value = headers.get('Retry-After') if isinstance(headers, Mapping) else None
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    from apps.common import clock
    seconds = int((when - clock.now()).total_seconds()) if when.tzinfo else -1
    return seconds if seconds >= 0 else None


def _retry_wait(resp, attempt: int, retry_5xx: bool):
    """Seconds to wait before the next try, or None to stop and return this response."""
    if attempt >= settings.ZOOM_HTTP_MAX_ATTEMPTS:
        return None
    if resp.status_code == 429:
        after = parse_retry_after(resp)
        if after is None:
            return backoff_seconds(attempt)
        return after if after <= settings.ZOOM_RETRY_AFTER_CAP_SECONDS else None
    if resp.status_code >= 500 and retry_5xx:
        return backoff_seconds(attempt)
    return None


def _error(op: str, resp) -> ZoomError:
    status = resp.status_code
    cls = ZoomNotFound if status == 404 else ZoomError
    return cls(f'Zoom {op} failed (HTTP {status})', status=status,
               retry_after_seconds=parse_retry_after(resp) if status == 429 else None)


def _json(resp) -> dict:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _safe_host(host_user_id) -> str:
    """The host goes into a URL path: only a Zoom user id, an e-mail or 'me'."""
    host = str(host_user_id or '')
    if not _HOST_ID.fullmatch(host):
        raise ZoomError('Invalid Zoom host user id')
    return host


def _room(data: dict, host: str) -> dict:
    return {'meeting_id': str(data.get('id')), 'join_url': data.get('join_url') or '',
            'password': data.get('password', '') or '', 'host_user_id': host}


def _agenda_matches(meeting: dict, marker: str, topic, start_time) -> bool:
    """Marker line in the agenda AND (when known) the same start time: a rescheduled lesson's old room carries the same
    booking marker until the cleanup task deletes it, and must never be picked up for the new time."""
    if start_time and meeting.get('start_time') != start_time:
        return False
    agenda = meeting.get('agenda')
    if isinstance(agenda, str):
        return marker in (line.strip() for line in agenda.splitlines())
    # No agenda in the list payload (to verify in the sandbox): fall back to the exact topic + start time we sent.
    return bool(topic and start_time) and meeting.get('topic') == topic


class ZoomClient:
    @property
    def account_id(self) -> str:
        return settings.ZOOM_ACCOUNT_ID

    @property
    def client_id(self) -> str:
        return settings.ZOOM_CLIENT_ID

    @property
    def client_secret(self) -> str:
        return settings.ZOOM_CLIENT_SECRET

    def credentials_configured(self) -> bool:
        return bool(self.account_id and self.client_id and self.client_secret)

    # ------------------------------------------------------------------ transport
    def _http(self, method: str, url: str, headers: dict, **kw):
        verb = getattr(requests, method.lower())
        try:
            return verb(url, headers=headers, timeout=settings.ZOOM_HTTP_TIMEOUT_SECONDS, **kw)
        except requests.Timeout:
            raise ZoomAmbiguous(f'Zoom {method} timed out') from None
        except requests.RequestException:
            raise ZoomAmbiguous(f'Zoom {method} connection failed') from None

    def _with_retries(self, call, *, retry_5xx=True):
        attempt = 0
        while True:
            resp = call()
            attempt += 1
            wait = _retry_wait(resp, attempt, retry_5xx)
            if wait is None:
                return resp
            logger.info('Zoom HTTP %s, retrying in %.2fs (attempt %s)', resp.status_code, wait, attempt)
            _sleep(wait)

    def _authorized(self, method: str, url: str, **kw):
        """One request with the cached token; after a 401, invalidate it and send once more with a fresh token."""
        token = self.get_access_token()
        resp = self._http(method, url, {'Authorization': f'Bearer {token}'}, **kw)
        if resp.status_code != 401:
            return resp
        zoom_auth.invalidate_token(self.account_id, token)
        fresh = self.get_access_token(stale=token)
        return self._http(method, url, {'Authorization': f'Bearer {fresh}'}, **kw)

    def _send(self, method: str, url: str, *, retry_5xx=True, **kw):
        return self._with_retries(lambda: self._authorized(method, url, **kw), retry_5xx=retry_5xx)

    # ------------------------------------------------------------------ auth
    def _fetch_token(self):
        """(token, expires_in) from Zoom's account_credentials grant; any failure raises (never cached)."""
        basic = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode()).decode()
        url = f'{TOKEN_URL}?grant_type=account_credentials&account_id={self.account_id}'
        resp = self._with_retries(lambda: self._http('POST', url, {'Authorization': f'Basic {basic}'}))
        data = _json(resp) if resp.status_code == 200 else {}
        token = data.get('access_token')
        if isinstance(token, str) and token:
            return token, data.get('expires_in')
        logger.error('Zoom OAuth token request failed: HTTP %s', resp.status_code)    # never the provider body
        raise _error('OAuth token request', resp)

    def get_access_token(self, stale=None) -> str:
        """A bearer token (cached per account). Raises ZoomError without credentials or on any OAuth failure."""
        if not self.credentials_configured():
            raise ZoomError('Zoom credentials are not configured')
        return zoom_auth.cached_token(self.account_id, self._fetch_token, stale=stale)

    def _simulated(self) -> bool:
        """True only without credentials AND settings.ZOOM_SIMULATE_WITHOUT_CREDENTIALS (local settings) AND DEBUG, so a
        shared/staging stack with DEBUG off never fabricates rooms or a 'waiting' status. Without credentials otherwise: raise."""
        if self.credentials_configured():
            return False
        if settings.DEBUG and getattr(settings, 'ZOOM_SIMULATE_WITHOUT_CREDENTIALS', False):
            logger.warning('Zoom API credentials not configured. Using simulated rooms (local settings only).')
            return True
        raise ZoomError('Zoom credentials are not configured and simulation is disabled')

    # ------------------------------------------------------------------ meetings
    def create_meeting(self, topic: str, start_time_iso: str, duration_minutes: int = 25, *, booking_id=None,
                       host_user_id='me', search_first=False) -> dict:
        """{meeting_id, join_url, password, host_user_id} (no host start link). With `booking_id`, the agenda carries
        `booking_marker` and an ambiguous outcome is searched for before any retry; `search_first` searches before the
        first POST too (a retry of a fulfilment step that failed earlier)."""
        host = _safe_host(host_user_id)
        if self._simulated():
            meeting_num = f'{uuid.uuid4().int % 10000000000:010d}'
            return {'meeting_id': meeting_num, 'join_url': f'https://zoom.us/j/{meeting_num}',
                    'password': 'pass' + meeting_num[:4], 'host_user_id': host}
        if booking_id and search_first:
            found = self.find_meeting_for_booking(booking_id, host, topic=topic, start_time=start_time_iso)
            if found:
                return found
        body = self._meeting_body(topic, start_time_iso, duration_minutes, booking_id)
        for attempt in range(1, settings.ZOOM_HTTP_MAX_ATTEMPTS + 1):
            resp = self._try_create(host, body)
            if resp is not None:
                if resp.status_code == 201:
                    return _room(_json(resp), host)
                raise _error('create meeting', resp)
            if not booking_id or attempt >= settings.ZOOM_HTTP_MAX_ATTEMPTS:
                raise ZoomAmbiguous('Zoom create meeting outcome unknown')
            logger.warning('Zoom create outcome unknown, searching before a retry: booking=%s attempt=%s', booking_id, attempt)
            found = self.find_meeting_for_booking(booking_id, host, topic=topic, start_time=start_time_iso)
            if found:
                return found
            _sleep(backoff_seconds(attempt))
        raise ZoomAmbiguous('Zoom create meeting outcome unknown')    # unreachable with ZOOM_HTTP_MAX_ATTEMPTS >= 1

    @staticmethod
    def _meeting_body(topic, start_time_iso, duration_minutes, booking_id) -> dict:
        body = {'topic': topic, 'type': 2, 'start_time': start_time_iso, 'duration': duration_minutes, 'timezone': 'UTC',
                'settings': {'host_video': True, 'participant_video': True, 'join_before_host': False,
                             'mute_upon_entry': False, 'waiting_room': True,
                             'auto_recording': 'none'}}        # D-8: no recording in the MVP, whatever the account default
        if booking_id:
            body['agenda'] = f'Sharon ESL lesson\n{booking_marker(booking_id)}'
        return body

    def _try_create(self, host: str, body: dict):
        """The create response, or None when the outcome is ambiguous (timeout, connection failure, 5xx). 429 is retried
        here (Zoom did not process it); 5xx is not, because Zoom may have created the meeting."""
        try:
            resp = self._send('POST', f'{API}/users/{host}/meetings', retry_5xx=False, json=body)
        except ZoomAmbiguous:
            return None
        return None if resp.status_code >= 500 else resp

    def find_meeting_for_booking(self, booking_id, host_user_id='me', *, page_size=SEARCH_PAGE_SIZE, topic=None,
                                 start_time=None):
        """The host's scheduled meeting carrying the booking's marker, or None. Any failure (or more pages than
        SEARCH_MAX_PAGES) raises: an unanswered search must stop a retry, not allow a second room."""
        host, marker = _safe_host(host_user_id), booking_marker(booking_id)
        params = {'type': 'scheduled', 'page_size': page_size}
        for _ in range(SEARCH_MAX_PAGES):
            resp = self._send('GET', f'{API}/users/{host}/meetings', params=dict(params))
            if resp.status_code != 200:
                raise _error('list meetings', resp)
            data = _json(resp)
            for meeting in data.get('meetings') or []:
                if isinstance(meeting, dict) and _agenda_matches(meeting, marker, topic, start_time):
                    logger.info('Zoom meeting of an earlier attempt found: booking=%s meeting=%s', booking_id, meeting.get('id'))
                    return _room(self._get_meeting(meeting.get('id')), host)
            if not data.get('next_page_token'):
                return None
            params['next_page_token'] = data['next_page_token']
        raise ZoomError('Zoom meeting search did not finish')

    def _get_meeting(self, meeting_id) -> dict:
        resp = self._send('GET', f'{API}/meetings/{meeting_id}')
        if resp.status_code == 200:
            return _json(resp)
        logger.error('Zoom meeting request failed for %s: HTTP %s', meeting_id, resp.status_code)
        raise _error('meeting request', resp)

    def get_meeting_status(self, meeting_id: str) -> dict:
        """{'status': <Zoom's status or None>}. A non-200 raises ZoomError; a missing status is None (the caller's 'unknown')."""
        if self._simulated():
            return {'meeting_id': str(meeting_id), 'status': 'waiting', 'participant_count': 0}
        data = self._get_meeting(meeting_id)
        return {'meeting_id': str(data.get('id')),
                'status': data.get('status'),  # 'waiting' | 'started'; anything else / absent = unknown to the caller
                'participant_count': data.get('participant_count', 0)}

    def get_start_url(self, meeting_id: str) -> str:
        """A FRESH host start link (it embeds an expiring ZAK). Never store or log it. ZoomNotFound for a meeting Zoom
        no longer has; ZoomError otherwise."""
        if self._simulated():
            return f'https://zoom.us/s/{meeting_id}?zak=simulated'
        url = self._get_meeting(meeting_id).get('start_url')
        if not (isinstance(url, str) and url.startswith('https://')):
            raise ZoomError('Zoom returned no host start link')
        return url

    def get_past_instances(self, meeting_id: str) -> list:
        """Ended instances of a meeting (`GET /past_meetings/{id}/instances`). A scheduled meeting goes back to `waiting` after
        it ends, so `waiting` + a past instance means the lesson DID take place. Only a 200 with a list is an answer;
        anything else raises ZoomError (the probe then says 'unknown')."""
        if self._simulated():
            return []          # simulated rooms never ran
        resp = self._send('GET', f'{API}/past_meetings/{meeting_id}/instances')
        meetings = _json(resp).get('meetings') if resp.status_code == 200 else None
        if isinstance(meetings, list):
            return meetings
        logger.error('Zoom past-instances request inconclusive for %s: HTTP %s', meeting_id, resp.status_code)
        raise ZoomError(f'Zoom past-instances request inconclusive (HTTP {resp.status_code})', status=resp.status_code)

    def delete_meeting(self, meeting_id: str) -> bool:
        """Remove a meeting (cancelled or rescheduled lesson). A meeting Zoom no longer has counts as deleted."""
        if self._simulated():
            return True        # simulated rooms (no credentials, local settings) have nothing to delete
        resp = self._send('DELETE', f'{API}/meetings/{meeting_id}')
        if resp.status_code in (204, 404):
            return True
        raise _error(f'delete meeting {meeting_id}', resp)

    # ------------------------------------------------------------------ webhooks
    @staticmethod
    def get_webhook_secret() -> str:
        return getattr(settings, 'ZOOM_WEBHOOK_SECRET_TOKEN', '') or ''

    @classmethod
    def verify_webhook_signature(cls, headers: dict, raw_body: bytes) -> tuple[bool, str]:
        zm_signature = headers.get('x-zm-signature') or headers.get('HTTP_X_ZM_SIGNATURE', '')
        zm_timestamp = headers.get('x-zm-request-timestamp') or headers.get('HTTP_X_ZM_REQUEST_TIMESTAMP', '')

        if not zm_signature or not zm_timestamp:
            return False, "Missing Zoom webhook signature or timestamp headers"

        try:
            timestamp_int = int(zm_timestamp)
        except (ValueError, TypeError):
            return False, "Invalid timestamp format in Zoom webhook header"

        # Check replay attack drift (within 300 seconds / 5 minutes)
        if abs(int(time.time()) - timestamp_int) > 300:
            return False, "Request timestamp out of allowable window (replay guard)"

        secret = cls.get_webhook_secret()
        if not secret:
            logger.error("ZOOM_WEBHOOK_SECRET_TOKEN is not configured; rejecting webhook")
            return False, "Zoom webhook secret not configured"
        body_str = raw_body.decode('utf-8', errors='replace')
        message = f"v0:{zm_timestamp}:{body_str}"
        computed_hash = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
        expected_signature = f"v0={computed_hash}"

        if not hmac.compare_digest(expected_signature, zm_signature):
            return False, "Invalid HMAC signature"

        return True, "Valid"

    @classmethod
    def generate_url_validation_response(cls, plain_token: str) -> dict:
        secret = cls.get_webhook_secret()
        encrypted_token = hmac.new(secret.encode('utf-8'), plain_token.encode('utf-8'), hashlib.sha256).hexdigest()
        return {"plainToken": plain_token, "encryptedToken": encrypted_token}


zoom_client = ZoomClient()
