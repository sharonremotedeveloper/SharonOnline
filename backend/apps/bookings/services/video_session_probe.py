"""Live-session probe for Video SDK lessons (Decision D-9, Slice V4).

Queries Zoom's Video SDK REST API to check the live state of session `lesson-<booking_id>`:
- STARTED: The session is live AND the tutor's user_identity is in it.
- NOT_STARTED: Zoom positively reports that no tutor ever joined a session for this topic
  (e.g., no sessions exist for the topic, or sessions exist but tutor's user_identity is absent).
- UNKNOWN: Transport errors, timeouts, HTTP 429/5xx, auth failures, missing credentials,
  or unparseable response. Defers adjudication; never counts as absence.
"""
import logging
import random
import time
from typing import Any, Dict, Optional

import jwt
import requests
from django.conf import settings

from apps.integrations.services.video_sdk import is_video_sdk_configured

logger = logging.getLogger(__name__)

STARTED = 'started'
NOT_STARTED = 'not_started'
UNKNOWN = 'unknown'

VIDEOSDK_API_BASE = 'https://api.zoom.us/v2/videosdk'
BACKOFF_BASE_SECONDS = 0.5


def _backoff_sleep(attempt: int) -> None:
    ceiling = min(BACKOFF_BASE_SECONDS * (2 ** max(attempt - 1, 0)), 10.0)
    time.sleep(max(random.uniform(0.05, ceiling), 0.05))  # noqa: S311


def _generate_api_jwt() -> Optional[str]:
    """Generate ephemeral Video SDK API JWT for server-to-server REST calls."""
    sdk_key = getattr(settings, 'ZOOM_VIDEO_SDK_KEY', '') or ''
    sdk_secret = getattr(settings, 'ZOOM_VIDEO_SDK_SECRET', '') or ''
    if not sdk_key.strip() or not sdk_secret.strip():
        return None

    now = int(time.time())
    payload = {
        'app_key': sdk_key.strip(),
        'version': 1,
        'iat': now,
        'exp': now + 3600,
    }
    return jwt.encode(payload, sdk_secret.strip(), algorithm='HS256')


def _make_api_request(
    url: str,
    token: str,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[requests.Response]:
    """Execute authenticated GET request to Zoom Video SDK REST API with retries."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    }
    timeout = getattr(settings, 'ZOOM_HTTP_TIMEOUT_SECONDS', 10)
    max_attempts = getattr(settings, 'ZOOM_HTTP_MAX_ATTEMPTS', 3)

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                logger.warning(
                    "[VIDEO_SDK_PROBE] Zoom API returned %s (attempt %s/%s)",
                    resp.status_code,
                    attempt,
                    max_attempts,
                )
                _backoff_sleep(attempt)
                continue
            return resp
        except requests.RequestException as exc:
            logger.warning(
                "[VIDEO_SDK_PROBE] Request exception: %s (attempt %s/%s)",
                type(exc).__name__,
                attempt,
                max_attempts,
            )
            if attempt < max_attempts:
                _backoff_sleep(attempt)
                continue
            return None
    return None


def _user_list_contains_tutor(users: list, tutor_identity: str) -> bool:
    for u in users:
        if isinstance(u, dict) and str(u.get('user_identity') or '') == tutor_identity:
            return True
    return False


def _session_contains_tutor(session: dict, tutor_identity: str, token: str) -> tuple[bool, Optional[str]]:
    inline_users = session.get('users')
    if isinstance(inline_users, list):
        return _user_list_contains_tutor(inline_users, tutor_identity), None

    session_id = session.get('id') or session.get('session_id')
    if not session_id:
        return False, None

    users_url = f"{VIDEOSDK_API_BASE}/sessions/{session_id}/users"
    users_resp = _make_api_request(users_url, token)
    if users_resp is None or users_resp.status_code != 200:
        logger.warning(
            "[VIDEO_SDK_PROBE] Failed to query users for session %s: %s",
            session_id,
            getattr(users_resp, 'status_code', 'no_response'),
        )
        return False, UNKNOWN

    try:
        users_data = users_resp.json()
    except Exception:
        return False, UNKNOWN

    users_list = users_data.get('users') if isinstance(users_data, dict) else None
    if isinstance(users_list, list):
        return _user_list_contains_tutor(users_list, tutor_identity), None

    return False, None


def _parse_sessions_data(data: Any, topic: str) -> tuple[Optional[list[dict]], Optional[str]]:
    if not isinstance(data, dict):
        return None, UNKNOWN

    sessions = data.get('sessions')
    if sessions is None and 'id' in data:
        sessions = [data]
    elif not isinstance(sessions, list):
        return None, UNKNOWN

    if not sessions:
        return None, NOT_STARTED

    matching = [
        s for s in sessions
        if isinstance(s, dict) and (s.get('topic') == topic or s.get('session_name') == topic or not s.get('topic'))
    ]
    if not matching:
        return None, NOT_STARTED

    return matching, None


def _get_matching_sessions(token: str, topic: str) -> tuple[Optional[list[dict]], Optional[str]]:
    sessions_url = f"{VIDEOSDK_API_BASE}/sessions"
    resp = _make_api_request(sessions_url, token, params={'topic': topic})

    if resp is None:
        return None, UNKNOWN

    if resp.status_code == 404:
        return None, NOT_STARTED

    if resp.status_code != 200:
        logger.warning("[VIDEO_SDK_PROBE] Non-200 from sessions endpoint: %s", resp.status_code)
        return None, UNKNOWN

    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("[VIDEO_SDK_PROBE] JSON decode error: %s", type(exc).__name__)
        return None, UNKNOWN

    return _parse_sessions_data(data, topic)


def probe_session(booking) -> str:
    """Query Zoom Video SDK REST API for the booking's session.

    Returns STARTED, NOT_STARTED, or UNKNOWN.
    """
    if not is_video_sdk_configured():
        return UNKNOWN

    teacher_user = getattr(booking.teacher, 'user', None) if hasattr(booking, 'teacher') else None
    if not teacher_user:
        return UNKNOWN

    tutor_identity = str(teacher_user.id)
    topic = f"lesson-{booking.id}"

    token = _generate_api_jwt()
    if not token:
        return UNKNOWN

    matching, status = _get_matching_sessions(token, topic)
    if status is not None:
        return status
    if not matching:
        return NOT_STARTED

    for session in matching:
        found, err_status = _session_contains_tutor(session, tutor_identity, token)
        if found:
            return STARTED
        if err_status is not None:
            return err_status

    return NOT_STARTED
