"""Unit and integration tests for Zoom Video SDK live-session probe (Slice V4).

Validates probe_session() tri-state semantics (STARTED, NOT_STARTED, UNKNOWN)
under various Zoom REST API response scenarios with strictly mocked HTTP.
"""
from datetime import timedelta
import logging
from unittest import mock
import pytest
import requests
from django.utils import timezone

import factories as f
from apps.bookings.models import Booking
from apps.bookings.services.video_session_probe import (
    NOT_STARTED,
    STARTED,
    UNKNOWN,
    probe_session,
)

SAMPLE_KEY = 'test_video_sdk_key_32chars_long!'
SAMPLE_SECRET = 'test_video_sdk_secret_36chars_abcdef1234'


@pytest.fixture
def video_sdk_settings(settings):
    settings.ZOOM_VIDEO_SDK_KEY = SAMPLE_KEY
    settings.ZOOM_VIDEO_SDK_SECRET = SAMPLE_SECRET
    settings.ZOOM_VIDEO_SDK_API_KEY = 'api_key_for_rest_probe'
    settings.ZOOM_VIDEO_SDK_API_SECRET = 'api_secret_for_rest_probe_36chars_abcd'
    settings.ZOOM_HTTP_MAX_ATTEMPTS = 2
    settings.ZOOM_HTTP_TIMEOUT_SECONDS = 2
    return settings


@pytest.fixture
def confirmed_booking():
    return f.make_booking(
        status=Booking.Status.CONFIRMED,
        start=timezone.now() - timedelta(minutes=10),
    )


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


@pytest.mark.django_db
class TestVideoSessionProbe:
    def test_unconfigured_video_sdk_returns_unknown(self, settings, confirmed_booking):
        settings.ZOOM_VIDEO_SDK_KEY = ''
        settings.ZOOM_VIDEO_SDK_SECRET = ''
        assert probe_session(confirmed_booking) == UNKNOWN

    def test_missing_rest_api_credentials_return_unknown_without_calling_zoom(self, video_sdk_settings, confirmed_booking):
        video_sdk_settings.ZOOM_VIDEO_SDK_API_KEY = ''
        with mock.patch('apps.bookings.services.video_session_probe.requests.get') as get:
            assert probe_session(confirmed_booking) == UNKNOWN
        get.assert_not_called()

    def test_rest_jwt_is_signed_with_the_api_credentials_and_carries_iss(self, video_sdk_settings):
        import jwt as pyjwt
        from apps.bookings.services.video_session_probe import _generate_api_jwt
        decoded = pyjwt.decode(_generate_api_jwt(), 'api_secret_for_rest_probe_36chars_abcd', algorithms=['HS256'])
        assert decoded['iss'] == 'api_key_for_rest_probe'
        assert 'app_key' not in decoded

    def test_booking_without_teacher_user_returns_unknown(self, video_sdk_settings):
        booking = mock.Mock(teacher=None)
        assert probe_session(booking) == UNKNOWN

    def test_live_session_with_tutor_identity_returns_started(self, video_sdk_settings, confirmed_booking):
        topic = f"lesson-{confirmed_booking.id}"
        tutor_id = str(confirmed_booking.teacher.user_id)

        def mock_get(url, *args, **kwargs):
            if url.endswith('/sessions'):
                return MockResponse({"sessions": [{"id": "sess_101", "topic": topic}]})
            if url.endswith('/sessions/sess_101/users'):
                return MockResponse({"users": [{"id": "u1", "user_identity": tutor_id}]})
            return MockResponse({}, status_code=404)

        with mock.patch('requests.get', side_effect=mock_get):
            assert probe_session(confirmed_booking) == STARTED

    def test_live_session_with_inline_tutor_users_returns_started(self, video_sdk_settings, confirmed_booking):
        topic = f"lesson-{confirmed_booking.id}"
        tutor_id = str(confirmed_booking.teacher.user_id)

        response_data = {
            "sessions": [
                {
                    "id": "sess_102",
                    "topic": topic,
                    "users": [{"user_identity": tutor_id, "user_name": "Tutor"}],
                }
            ]
        }

        with mock.patch('requests.get', return_value=MockResponse(response_data)):
            assert probe_session(confirmed_booking) == STARTED

    def test_empty_sessions_list_returns_not_started(self, video_sdk_settings, confirmed_booking):
        with mock.patch('requests.get', return_value=MockResponse({"sessions": []})):
            assert probe_session(confirmed_booking) == NOT_STARTED

    def test_session_exists_with_student_only_returns_not_started(self, video_sdk_settings, confirmed_booking):
        topic = f"lesson-{confirmed_booking.id}"
        student_id = str(confirmed_booking.student_id)

        def mock_get(url, *args, **kwargs):
            if url.endswith('/sessions'):
                return MockResponse({"sessions": [{"id": "sess_202", "topic": topic}]})
            if url.endswith('/sessions/sess_202/users'):
                return MockResponse({"users": [{"id": "u2", "user_identity": student_id}]})
            return MockResponse({}, status_code=404)

        with mock.patch('requests.get', side_effect=mock_get):
            assert probe_session(confirmed_booking) == NOT_STARTED

    def test_no_matching_topic_sessions_returns_not_started(self, video_sdk_settings, confirmed_booking):
        response_data = {
            "sessions": [
                {"id": "sess_other", "topic": "lesson-other-uuid"}
            ]
        }
        with mock.patch('requests.get', return_value=MockResponse(response_data)):
            assert probe_session(confirmed_booking) == NOT_STARTED

    def test_404_not_found_from_zoom_returns_not_started(self, video_sdk_settings, confirmed_booking):
        with mock.patch('requests.get', return_value=MockResponse({}, status_code=404)):
            assert probe_session(confirmed_booking) == NOT_STARTED

    def test_500_server_error_returns_unknown(self, video_sdk_settings, confirmed_booking):
        with mock.patch('requests.get', return_value=MockResponse({}, status_code=500)):
            assert probe_session(confirmed_booking) == UNKNOWN

    def test_timeout_returns_unknown(self, video_sdk_settings, confirmed_booking):
        with mock.patch('requests.get', side_effect=requests.Timeout('Connection timed out')):
            assert probe_session(confirmed_booking) == UNKNOWN

    def test_connection_error_returns_unknown(self, video_sdk_settings, confirmed_booking):
        with mock.patch('requests.get', side_effect=requests.ConnectionError('Refused')):
            assert probe_session(confirmed_booking) == UNKNOWN

    def test_malformed_json_response_returns_unknown(self, video_sdk_settings, confirmed_booking):
        with mock.patch('requests.get', return_value=MockResponse(ValueError("Invalid JSON"))):
            assert probe_session(confirmed_booking) == UNKNOWN

    def test_unexpected_payload_structure_returns_unknown(self, video_sdk_settings, confirmed_booking):
        with mock.patch('requests.get', return_value=MockResponse({"unrecognized_root": True})):
            assert probe_session(confirmed_booking) == UNKNOWN

    def test_users_subresource_failure_returns_unknown(self, video_sdk_settings, confirmed_booking):
        topic = f"lesson-{confirmed_booking.id}"

        def mock_get(url, *args, **kwargs):
            if url.endswith('/sessions'):
                return MockResponse({"sessions": [{"id": "sess_err", "topic": topic}]})
            if url.endswith('/sessions/sess_err/users'):
                return MockResponse({}, status_code=500)
            return MockResponse({}, status_code=404)

        with mock.patch('requests.get', side_effect=mock_get):
            assert probe_session(confirmed_booking) == UNKNOWN

    def test_secret_is_never_logged(self, video_sdk_settings, confirmed_booking, caplog):
        with caplog.at_level(logging.DEBUG):
            with mock.patch('requests.get', side_effect=requests.RequestException("Network fail")):
                probe_session(confirmed_booking)

        for record in caplog.records:
            assert SAMPLE_SECRET not in record.message
