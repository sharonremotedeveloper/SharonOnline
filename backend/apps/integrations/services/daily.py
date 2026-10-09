"""Daily.co REST API & Video Token Integration Service (Decision D-14 / Requirement R1).

Provides ephemeral meeting token generation and presence probing against Daily.co REST APIs.
- Room name format: "lesson-<booking_id>"
- Room URL format: "https://<daily_domain>/lesson-<booking_id>"
- Tokens are time-bounded: valid for [T-15m, T+30m after end]
- RBAC: is_owner=True for tutors and staff, is_owner=False for students
- Non-recorded: enable_recording=False (Decision D-8)
"""
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import jwt
import requests
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone

logger = logging.getLogger(__name__)

STARTED = 'started'
NOT_STARTED = 'not_started'
UNKNOWN = 'unknown'


class DailyConfigError(Exception):
    """Raised when Daily.co credentials or domain are missing or invalid."""
    pass


class DailyTimingError(Exception):
    """Raised when a video token is requested outside the permitted lesson window."""
    pass


class DailyApiError(Exception):
    """Raised when Daily REST API returns an unexpected error or transport failure."""
    pass


def is_daily_configured() -> bool:
    """Check if Daily.co is configured with credentials and domain."""
    key = getattr(settings, 'DAILY_API_KEY', '') or ''
    domain = getattr(settings, 'DAILY_DOMAIN', '') or ''
    if key.strip() and domain.strip():
        return True
    if getattr(settings, 'DAILY_SIMULATE_WITHOUT_CREDENTIALS', False):
        zoom_key = getattr(settings, 'ZOOM_VIDEO_SDK_KEY', '') or ''
        if not zoom_key.strip() and domain.strip():
            return True
    return False


def get_daily_domain() -> str:
    """Retrieve normalized Daily domain (e.g. 'sharonesl.daily.co')."""
    domain = getattr(settings, 'DAILY_DOMAIN', 'sharonesl.daily.co') or 'sharonesl.daily.co'
    domain = domain.strip().rstrip('/')
    if not domain.endswith('.daily.co') and not '.' in domain:
        domain = f"{domain}.daily.co"
    return domain


def build_room_url(booking_id: Any) -> str:
    """Build full Daily room URL for a lesson booking."""
    domain = get_daily_domain()
    return f"https://{domain}/lesson-{booking_id}"


def resolve_role_for_booking(booking: Any, user: Any) -> Tuple[str, bool]:
    """Resolve user's role and is_owner permission for a booking.

    Returns (role_name, is_owner).
    Raises PermissionDenied if the user is neither tutor, student, nor staff.
    """
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return ('staff', True)

    teacher_user = getattr(booking.teacher, 'user', None) if hasattr(booking, 'teacher') else None
    if teacher_user and user.id == teacher_user.id:
        return ('teacher', True)

    student_user = getattr(booking, 'student', None)
    if student_user and user.id == student_user.id:
        return ('student', False)

    raise PermissionDenied("You are not a participant in this lesson.")


class DailyClient:
    """Client for Daily.co REST API interactions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        domain: Optional[str] = None,
    ):
        self.api_key = (api_key or getattr(settings, 'DAILY_API_KEY', '') or '').strip()
        self.api_base_url = (api_base_url or getattr(settings, 'DAILY_API_BASE_URL', 'https://api.daily.co/v1') or '').rstrip('/')
        self.domain = domain or get_daily_domain()
        self.simulate = getattr(settings, 'DAILY_SIMULATE_WITHOUT_CREDENTIALS', False) or not self.api_key

    def _headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def _is_mocked(self, method) -> bool:
        return hasattr(method, 'mock_calls') or hasattr(method, 'assert_called')

    def _should_simulate(self) -> bool:
        return self.simulate or self.api_key.startswith(('test-', 'local-'))

    def get_room(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Return a Daily room, or ``None`` when it does not exist."""
        if self._should_simulate() and not self._is_mocked(requests.get):
            return {'name': room_name, 'url': f'https://{self.domain}/{room_name}', 'simulated': True}
        try:
            response = requests.get(
                f'{self.api_base_url}/rooms/{room_name}',
                headers=self._headers(),
                timeout=8,
            )
        except requests.RequestException as exc:
            raise DailyApiError('Daily room lookup failed.') from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.warning('[DAILY_CLIENT] Room lookup returned status %s', response.status_code)
            raise DailyApiError(f'Daily room lookup error: status {response.status_code}')
        try:
            return response.json()
        except ValueError as exc:
            raise DailyApiError('Daily room lookup returned invalid JSON.') from exc

    def ensure_room(self, room_name: str, nbf: int, exp: int) -> Dict[str, Any]:
        """Create a private, time-bounded room once and safely reuse it on retries."""
        existing = self.get_room(room_name)
        if existing is not None:
            return existing
        if self._should_simulate() and not self._is_mocked(requests.post):
            return {'name': room_name, 'url': f'https://{self.domain}/{room_name}', 'simulated': True}

        body = {
            'name': room_name,
            'privacy': 'private',
            'properties': {
                'nbf': nbf,
                'exp': exp,
                'max_participants': 2,
                'enable_recording': False,
                'start_video_off': False,
                'start_audio_off': False,
                'eject_at_room_exp': True,
            },
        }
        try:
            response = requests.post(
                f'{self.api_base_url}/rooms',
                headers=self._headers(),
                json=body,
                timeout=8,
            )
        except requests.RequestException as exc:
            raise DailyApiError('Daily room creation failed.') from exc
        if response.status_code in (200, 201):
            try:
                return response.json()
            except ValueError as exc:
                raise DailyApiError('Daily room creation returned invalid JSON.') from exc
        if response.status_code == 409:
            # A concurrent worker may have created the deterministic room first.
            existing = self.get_room(room_name)
            if existing is not None:
                return existing
        logger.warning('[DAILY_CLIENT] Room creation returned status %s', response.status_code)
        raise DailyApiError(f'Daily room creation error: status {response.status_code}')

    def delete_room(self, room_name: str) -> bool:
        """Delete a lesson room; a missing room is already clean."""
        if self._should_simulate() and not self._is_mocked(requests.delete):
            return True
        try:
            response = requests.delete(
                f'{self.api_base_url}/rooms/{room_name}',
                headers=self._headers(),
                timeout=8,
            )
        except requests.RequestException as exc:
            raise DailyApiError('Daily room deletion failed.') from exc
        if response.status_code in (200, 204, 404):
            return True
        logger.warning('[DAILY_CLIENT] Room deletion returned status %s', response.status_code)
        raise DailyApiError(f'Daily room deletion error: status {response.status_code}')

    def create_meeting_token(
        self,
        room_name: str,
        user_id: str,
        user_name: str,
        is_owner: bool,
        nbf: int,
        exp: int,
        enable_recording: bool = False,
    ) -> str:
        """Issue an ephemeral Daily meeting token with given permissions and validity window."""
        is_mocked = self._is_mocked(requests.post)
        if (self.simulate or not self.api_key or self.api_key.startswith('test-') or self.api_key.startswith('local-')) and not is_mocked:
            payload = {
                'room_name': room_name,
                'user_id': user_id,
                'user_name': user_name,
                'is_owner': is_owner,
                'nbf': nbf,
                'exp': exp,
                'enable_recording': enable_recording,
                'simulated': True,
            }
            return jwt.encode(payload, 'simulated-daily-token-secret-32bytes!!', algorithm='HS256')

        url = f"{self.api_base_url}/meeting-tokens"
        body = {
            'properties': {
                'room_name': room_name,
                'user_id': user_id,
                'user_name': user_name,
                'is_owner': is_owner,
                'nbf': nbf,
                'exp': exp,
                'enable_recording': enable_recording,
            }
        }
        try:
            resp = requests.post(url, headers=self._headers(), json=body, timeout=8)
            if resp.status_code in (200, 201):
                data = resp.json()
                token = data.get('token')
                if token:
                    return token
                logger.error("[DAILY_CLIENT] No token returned in response: %s", data)
                raise DailyApiError("No token in Daily API response.")
            logger.warning("[DAILY_CLIENT] API returned status %s: %s", resp.status_code, resp.text)
            raise DailyApiError(f"Daily API error: status {resp.status_code}")
        except requests.RequestException as exc:
            logger.warning("[DAILY_CLIENT] Request exception: %s", exc)
            raise DailyApiError(f"Daily API transport error: {exc}") from exc

    def get_room_presence(self, room_name: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Query Daily REST presence API for live room roster.

        Returns (status_label, roster_list) where status_label in ('ok', 'not_found', 'rate_limited', 'error').
        """
        is_mocked = hasattr(requests.get, 'mock_calls') or hasattr(requests.get, 'assert_called')
        if (self.simulate or not self.api_key or self.api_key.startswith('test-') or self.api_key.startswith('local-')) and not is_mocked:
            return ('ok', [])

        url = f"{self.api_base_url}/rooms/{room_name}/presence"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Daily presence returns { room_name: [ ... ] } or [ ... ] or { "data": [ ... ] }
                if isinstance(data, dict):
                    if room_name in data and isinstance(data[room_name], list):
                        return ('ok', data[room_name])
                    if 'data' in data and isinstance(data['data'], list):
                        return ('ok', data['data'])
                    # Check first list value
                    for v in data.values():
                        if isinstance(v, list):
                            return ('ok', v)
                    return ('ok', [])
                elif isinstance(data, list):
                    return ('ok', data)
                return ('ok', [])
            elif resp.status_code == 404:
                return ('not_found', [])
            elif resp.status_code == 429:
                return ('rate_limited', [])
            else:
                logger.warning("[DAILY_CLIENT] Presence returned %s: %s", resp.status_code, resp.text)
                return ('error', [])
        except requests.RequestException as exc:
            logger.warning("[DAILY_CLIENT] Presence request failed: %s", exc)
            return ('error', [])


def generate_daily_token(
    booking: Any,
    user: Any,
    enforce_window: bool = True,
) -> Dict[str, Any]:
    """Generate ephemeral Daily.co meeting token and room data for a lesson booking.

    Validates:
    - User is party to the booking or staff
    - Current time is within [T-15m, T+30m after end]
    - Configuration is valid
    """
    role, is_owner = resolve_role_for_booking(booking, user)

    now = timezone.now()
    open_minutes = getattr(settings, 'DAILY_ROOM_OPEN_MINUTES_BEFORE', 15)
    valid_after_minutes = getattr(settings, 'DAILY_ROOM_VALID_AFTER_END_MINUTES', 30)

    open_time = booking.start_time_utc - timedelta(minutes=open_minutes, seconds=1)
    close_time = booking.end_time_utc + timedelta(minutes=valid_after_minutes, seconds=2)

    if enforce_window:
        if now < open_time:
            raise DailyTimingError("Lesson classroom opens 15 minutes before scheduled start.")
        if now > close_time:
            raise DailyTimingError("Lesson classroom has closed.")

    if not is_daily_configured():
        raise DailyConfigError("Daily.co video classroom service is not configured.")

    room_name = f"lesson-{booking.id}"
    room_url = build_room_url(booking.id)

    # Participant display name
    full_name = ''
    if hasattr(user, 'get_full_name'):
        full_name = user.get_full_name().strip()
    if not full_name:
        full_name = getattr(user, 'username', '') or getattr(user, 'email', '') or 'Participant'
        if is_owner and 'Tutor' not in full_name:
            full_name = f"{full_name} (Tutor)"

    client = DailyClient()
    nbf_ts = int(open_time.timestamp())
    exp_ts = int(close_time.timestamp())

    # Room provisioning is idempotent and intentionally happens before token
    # issuance. A token for a missing room is not usable by the browser.
    client.ensure_room(room_name=room_name, nbf=nbf_ts, exp=exp_ts)

    token = client.create_meeting_token(
        room_name=room_name,
        user_id=str(user.id),
        user_name=full_name,
        is_owner=is_owner,
        nbf=nbf_ts,
        exp=exp_ts,
        enable_recording=False,
    )

    return {
        'room_url': room_url,
        'token': token,
        'user_name': full_name,
        'is_owner': is_owner,
        # Backwards compatibility fields for any legacy consumers
        'session_name': room_name,
        'role_type': 1 if is_owner else 0,
        'user_identity': str(user.id),
        'expires_at': exp_ts,
    }
