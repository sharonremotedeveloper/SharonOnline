"""Unit tests for Zoom Video SDK token generation service (Sprint Slice V1).

Validates HMAC-SHA256 JWT claims, role mapping, time window enforcement,
and security guardrails.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock
import uuid
import pytest
from django.core.exceptions import PermissionDenied

from apps.integrations.services.video_sdk import (
    ROLE_HOST,
    ROLE_PARTICIPANT,
    VideoSdkConfigError,
    VideoSdkTimingError,
    decode_video_sdk_token,
    generate_video_sdk_token,
    is_video_sdk_configured,
    resolve_role_for_booking,
)

SAMPLE_KEY = 'test_sdk_key_1234567890abcdef'
SAMPLE_SECRET = 'test_sdk_secret_9876543210fedcba'


@pytest.fixture
def video_sdk_settings(settings):
    settings.ZOOM_VIDEO_SDK_KEY = SAMPLE_KEY
    settings.ZOOM_VIDEO_SDK_SECRET = SAMPLE_SECRET
    settings.ZOOM_VIDEO_SDK_SESSION_VALID_SECONDS = 7200
    settings.ZOOM_VIDEO_SDK_OPEN_MINUTES_BEFORE = 15
    return settings


@pytest.fixture
def mock_users():
    tutor_user = MagicMock()
    tutor_user.id = 101
    tutor_user.username = 'tutor_user'
    tutor_user.email = 'tutor@example.com'
    tutor_user.is_authenticated = True
    tutor_user.is_staff = False
    tutor_user.is_superuser = False
    tutor_user.get_full_name.return_value = 'Jane Tutor'

    student_user = MagicMock()
    student_user.id = 202
    student_user.username = 'student_user'
    student_user.email = 'student@example.com'
    student_user.is_authenticated = True
    student_user.is_staff = False
    student_user.is_superuser = False
    student_user.get_full_name.return_value = 'Sam Student'

    staff_user = MagicMock()
    staff_user.id = 303
    staff_user.username = 'staff_user'
    staff_user.email = 'staff@example.com'
    staff_user.is_authenticated = True
    staff_user.is_staff = True
    staff_user.is_superuser = False
    staff_user.get_full_name.return_value = 'Staff Admin'

    stranger_user = MagicMock()
    stranger_user.id = 404
    stranger_user.username = 'stranger'
    stranger_user.email = 'stranger@example.com'
    stranger_user.is_authenticated = True
    stranger_user.is_staff = False
    stranger_user.is_superuser = False
    stranger_user.get_full_name.return_value = 'Random Person'

    return {
        'tutor': tutor_user,
        'student': student_user,
        'staff': staff_user,
        'stranger': stranger_user,
    }


@pytest.fixture
def mock_booking(mock_users):
    booking = MagicMock()
    booking.id = uuid.UUID('12345678-1234-5678-1234-567812345678')
    booking.teacher.user_id = mock_users['tutor'].id
    booking.teacher.user = mock_users['tutor']
    booking.student_id = mock_users['student'].id
    booking.student = mock_users['student']

    # 25-minute lesson starting at 10:00 UTC
    now_utc = datetime(2026, 11, 1, 10, 0, 0, tzinfo=dt_timezone.utc)
    booking.start_time_utc = now_utc
    booking.end_time_utc = now_utc + timedelta(minutes=25)
    return booking


class TestVideoSdkConfiguration:
    def test_configured_returns_true_when_both_set(self, video_sdk_settings):
        assert is_video_sdk_configured() is True

    @pytest.mark.parametrize('key,secret', [
        ('', 'secret'),
        ('   ', 'secret'),
        ('key', ''),
        ('key', '   '),
        ('', ''),
    ])
    def test_configured_returns_false_when_missing(self, settings, key, secret):
        settings.ZOOM_VIDEO_SDK_KEY = key
        settings.ZOOM_VIDEO_SDK_SECRET = secret
        assert is_video_sdk_configured() is False


class TestRoleResolution:
    def test_tutor_resolves_to_host(self, mock_booking, mock_users):
        role = resolve_role_for_booking(mock_booking, mock_users['tutor'])
        assert role == ROLE_HOST

    def test_student_resolves_to_participant(self, mock_booking, mock_users):
        role = resolve_role_for_booking(mock_booking, mock_users['student'])
        assert role == ROLE_PARTICIPANT

    def test_staff_resolves_to_host(self, mock_booking, mock_users):
        role = resolve_role_for_booking(mock_booking, mock_users['staff'])
        assert role == ROLE_HOST

    def test_stranger_raises_permission_denied(self, mock_booking, mock_users):
        with pytest.raises(PermissionDenied, match="neither the assigned tutor nor student"):
            resolve_role_for_booking(mock_booking, mock_users['stranger'])


class TestTokenGeneration:
    def test_token_payload_for_tutor(self, video_sdk_settings, mock_booking, mock_users):
        ref_time = datetime(2026, 11, 1, 9, 50, 0, tzinfo=dt_timezone.utc)  # 10 min before start
        result = generate_video_sdk_token(
            mock_booking,
            mock_users['tutor'],
            enforce_window=True,
            reference_time=ref_time,
        )

        assert result['session_name'] == f"lesson-{mock_booking.id}"
        assert result['role_type'] == ROLE_HOST
        assert result['user_identity'] == str(mock_users['tutor'].id)
        assert result['user_name'] == 'Jane Tutor'

        # Decode token and verify claims
        decoded = decode_video_sdk_token(result['token'])
        assert decoded['app_key'] == SAMPLE_KEY
        assert decoded['version'] == 1
        assert decoded['role_type'] == ROLE_HOST
        assert decoded['tpc'] == f"lesson-{mock_booking.id}"
        assert decoded['user_identity'] == str(mock_users['tutor'].id)
        assert decoded['cloud_recording_option'] == 0
        assert decoded['exp'] - decoded['iat'] == 7200

    def test_token_payload_for_student(self, video_sdk_settings, mock_booking, mock_users):
        ref_time = datetime(2026, 11, 1, 9, 55, 0, tzinfo=dt_timezone.utc)
        result = generate_video_sdk_token(
            mock_booking,
            mock_users['student'],
            enforce_window=True,
            reference_time=ref_time,
        )

        assert result['role_type'] == ROLE_PARTICIPANT
        decoded = decode_video_sdk_token(result['token'])
        assert decoded['role_type'] == ROLE_PARTICIPANT
        assert decoded['user_identity'] == str(mock_users['student'].id)

    def test_token_fails_closed_without_credentials(self, settings, mock_booking, mock_users):
        settings.ZOOM_VIDEO_SDK_KEY = ''
        settings.ZOOM_VIDEO_SDK_SECRET = ''
        with pytest.raises(VideoSdkConfigError):
            generate_video_sdk_token(mock_booking, mock_users['tutor'], enforce_window=False)


class TestTimeWindowEnforcement:
    def test_too_early_raises_timing_error(self, video_sdk_settings, mock_booking, mock_users):
        # 16 minutes before start (cutoff is 15 min)
        too_early = datetime(2026, 11, 1, 9, 44, 0, tzinfo=dt_timezone.utc)
        with pytest.raises(VideoSdkTimingError, match="Classroom opens 15 minutes before"):
            generate_video_sdk_token(
                mock_booking,
                mock_users['student'],
                enforce_window=True,
                reference_time=too_early,
            )

    def test_window_open_at_15_minutes_before(self, video_sdk_settings, mock_booking, mock_users):
        exactly_15_before = datetime(2026, 11, 1, 9, 45, 0, tzinfo=dt_timezone.utc)
        result = generate_video_sdk_token(
            mock_booking,
            mock_users['student'],
            enforce_window=True,
            reference_time=exactly_15_before,
        )
        assert result['token']

    def test_active_during_lesson(self, video_sdk_settings, mock_booking, mock_users):
        during_lesson = datetime(2026, 11, 1, 10, 10, 0, tzinfo=dt_timezone.utc)
        result = generate_video_sdk_token(
            mock_booking,
            mock_users['tutor'],
            enforce_window=True,
            reference_time=during_lesson,
        )
        assert result['token']

    def test_too_late_after_session_ended(self, video_sdk_settings, mock_booking, mock_users):
        # Lesson ends at 10:25; 30 min buffer is 10:55. At 10:56 it's closed.
        too_late = datetime(2026, 11, 1, 10, 56, 0, tzinfo=dt_timezone.utc)
        with pytest.raises(VideoSdkTimingError, match="video session has ended"):
            generate_video_sdk_token(
                mock_booking,
                mock_users['tutor'],
                enforce_window=True,
                reference_time=too_late,
            )
