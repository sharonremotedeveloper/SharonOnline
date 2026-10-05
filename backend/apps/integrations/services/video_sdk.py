"""Zoom Video SDK Session & Authentication Service (Decision D-9, Sprint Slice V1).

Provides JWT token issuance for embedded in-browser lessons without requiring
Zoom accounts or individual host licenses.

JWT Specification conforming to Zoom Video SDK:
Header: {"alg": "HS256", "typ": "JWT"}
Payload:
- app_key: Zoom Video SDK Key
- version: 1
- user_identity: Unique user ID (string UUID)
- iat: Issued at (epoch seconds)
- exp: Expiration timestamp (epoch seconds, >= 1800s and <= 48h)
- tpc: Session topic/name ("lesson-<booking_id>")
- role_type: 1 for Host (Tutor), 0 for Participant (Student)
- cloud_recording_option: 0 (Disabled per Decision D-8)
"""
import logging
import time
from datetime import timedelta
from typing import Any, Dict, Optional

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.utils import timezone

logger = logging.getLogger(__name__)

# Roles in Zoom Video SDK
ROLE_PARTICIPANT = 0  # Student / attendee
ROLE_HOST = 1         # Tutor / moderator / staff co-host


class VideoSdkConfigError(ImproperlyConfigured):
    """Raised when Zoom Video SDK credentials are missing or invalid."""
    pass


class VideoSdkTimingError(ValueError):
    """Raised when attempting to access the classroom outside the valid time window."""
    pass


def is_video_sdk_configured() -> bool:
    """Return True if both ZOOM_VIDEO_SDK_KEY and ZOOM_VIDEO_SDK_SECRET are set."""
    key = getattr(settings, 'ZOOM_VIDEO_SDK_KEY', '') or ''
    secret = getattr(settings, 'ZOOM_VIDEO_SDK_SECRET', '') or ''
    return bool(key.strip() and secret.strip())


def get_video_session_name(booking) -> str:
    """Return deterministic, sanitized session topic name for a booking (max 200 chars)."""
    return f"lesson-{booking.id}"


def resolve_role_for_booking(booking, user) -> int:
    """Determine role_type (1 for Host, 0 for Participant) or raise PermissionDenied."""
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required to access video classroom.")

    # Tutor is Host
    if hasattr(booking, 'teacher') and booking.teacher.user_id == user.id:
        return ROLE_HOST

    # Student is Participant
    if booking.student_id == user.id:
        return ROLE_PARTICIPANT

    # Staff / Admins enter with host privileges for quality monitoring / troubleshooting
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return ROLE_HOST

    raise PermissionDenied("You are neither the assigned tutor nor student for this lesson.")


def validate_booking_time_window(booking, reference_time=None, minutes_before=None, minutes_after_end=30):
    """Verify that the lesson window is open.

    Window: [start_time - minutes_before, end_time + minutes_after_end].
    """
    now = reference_time or timezone.now()
    lead_minutes = (
        minutes_before
        if minutes_before is not None
        else getattr(settings, 'ZOOM_VIDEO_SDK_OPEN_MINUTES_BEFORE', 15)
    )

    open_time = booking.start_time_utc - timedelta(minutes=lead_minutes)
    close_time = booking.end_time_utc + timedelta(minutes=minutes_after_end)

    if now < open_time:
        minutes_until = max(1, int((open_time - now).total_seconds() // 60))
        raise VideoSdkTimingError(
            f"Classroom opens {lead_minutes} minutes before start time. "
            f"Please return in approximately {minutes_until} minute(s)."
        )

    if now > close_time:
        raise VideoSdkTimingError("This lesson's video session has ended.")


def generate_video_sdk_token(
    booking,
    user,
    role_type: Optional[int] = None,
    expiration_seconds: Optional[int] = None,
    enforce_window: bool = True,
    reference_time=None,
) -> Dict[str, Any]:
    """Generate a signed Video SDK JWT token for a specific user and booking.

    Returns dict containing token, session_name, role_type, user_identity, user_name, expires_at.
    """
    sdk_key = getattr(settings, 'ZOOM_VIDEO_SDK_KEY', '') or ''
    sdk_secret = getattr(settings, 'ZOOM_VIDEO_SDK_SECRET', '') or ''

    if not sdk_key.strip() or not sdk_secret.strip():
        raise VideoSdkConfigError("Zoom Video SDK credentials are not configured in Django settings.")

    # 1. Enforce time window if requested
    if enforce_window:
        validate_booking_time_window(booking, reference_time=reference_time)

    # 2. Resolve Role
    if role_type is None:
        role_type = resolve_role_for_booking(booking, user)

    # 3. Expiration calculation (default 2 hours, clamped between 1800s and 48h)
    default_ttl = getattr(settings, 'ZOOM_VIDEO_SDK_SESSION_VALID_SECONDS', 7200)
    ttl = expiration_seconds if expiration_seconds is not None else default_ttl
    ttl = max(1800, min(ttl, 48 * 3600))

    now = int(time.time())
    exp = now + ttl
    session_name = get_video_session_name(booking)
    user_identity = str(user.id)
    user_name = user.get_full_name() or user.username or str(user.email)

    payload = {
        'app_key': sdk_key,
        'version': 1,
        'user_identity': user_identity,
        'iat': now,
        'exp': exp,
        'tpc': session_name,
        'role_type': role_type,
        'cloud_recording_option': 0,
    }

    token = jwt.encode(
        payload,
        sdk_secret,
        algorithm='HS256',
        headers={'alg': 'HS256', 'typ': 'JWT'},
    )

    if isinstance(token, bytes):
        token = token.decode('utf-8')

    logger.info(
        "[VIDEO_SDK] Issued token for booking %s, user %s, role %s (session %s)",
        booking.id,
        user.id,
        role_type,
        session_name,
    )

    return {
        'token': token,
        'session_name': session_name,
        'role_type': role_type,
        'user_identity': user_identity,
        'user_name': user_name,
        'expires_at': exp,
    }


def decode_video_sdk_token(token: str, verify: bool = True) -> Dict[str, Any]:
    """Decode and validate a Video SDK token using the configured secret."""
    sdk_secret = getattr(settings, 'ZOOM_VIDEO_SDK_SECRET', '') or ''
    if verify and not sdk_secret:
        raise VideoSdkConfigError("Cannot verify Video SDK token without ZOOM_VIDEO_SDK_SECRET.")

    options = {'verify_signature': verify}
    return jwt.decode(
        token,
        sdk_secret if verify else '',
        algorithms=['HS256'],
        options=options,
    )
