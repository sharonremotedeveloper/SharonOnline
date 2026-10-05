"""Integration tests for GET /api/v1/bookings/<id>/video-token/ (Sprint Slice V2).

Validates RBAC, token signature, role assignment, time window constraints,
and HTTP response headers (Cache-Control: no-store).
"""
from datetime import timedelta
import uuid
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking
from apps.integrations.services.video_sdk import decode_video_sdk_token

S = Booking.Status
ENDPOINT = '/api/v1/bookings/{}/video-token/'
SAMPLE_KEY = 'test_sdk_key_v2'
SAMPLE_SECRET = 'test_sdk_secret_v2_1234567890abcdef'


def client_for(user=None):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user)
    return c


@pytest.fixture
def video_sdk_env(settings):
    settings.ZOOM_VIDEO_SDK_KEY = SAMPLE_KEY
    settings.ZOOM_VIDEO_SDK_SECRET = SAMPLE_SECRET
    settings.ZOOM_VIDEO_SDK_SESSION_VALID_SECONDS = 7200
    settings.ZOOM_VIDEO_SDK_OPEN_MINUTES_BEFORE = 15
    return settings


@pytest.fixture
def active_booking():
    """A confirmed lesson starting in 5 minutes (classroom window is open)."""
    now = timezone.now()
    return f.make_booking(
        status=S.CONFIRMED,
        start=now + timedelta(minutes=5),
    )


@pytest.mark.django_db
class TestBookingVideoTokenEndpoint:
    def test_unauthenticated_request_is_denied(self, video_sdk_env, active_booking):
        c = client_for(None)
        res = c.get(ENDPOINT.format(active_booking.id))
        assert res.status_code == 401

    def test_tutor_gets_video_token_with_host_role(self, video_sdk_env, active_booking):
        c = client_for(active_booking.teacher.user)
        res = c.get(ENDPOINT.format(active_booking.id))
        assert res.status_code == 200
        assert res['Cache-Control'] == 'no-store'

        data = res.data
        assert data['role_type'] == 1
        assert data['session_name'] == f"lesson-{active_booking.id}"
        assert data['user_identity'] == str(active_booking.teacher.user.id)

        # Validate JWT token
        payload = decode_video_sdk_token(data['token'])
        assert payload['app_key'] == SAMPLE_KEY
        assert payload['role_type'] == 1
        assert payload['tpc'] == f"lesson-{active_booking.id}"
        assert payload['cloud_recording_option'] == 0

    def test_student_gets_video_token_with_participant_role(self, video_sdk_env, active_booking):
        c = client_for(active_booking.student)
        res = c.get(ENDPOINT.format(active_booking.id))
        assert res.status_code == 200

        data = res.data
        assert data['role_type'] == 0
        assert data['user_identity'] == str(active_booking.student.id)

        payload = decode_video_sdk_token(data['token'])
        assert payload['role_type'] == 0
        assert payload['tpc'] == f"lesson-{active_booking.id}"

    def test_unrelated_user_is_forbidden(self, video_sdk_env, active_booking):
        stranger = f.make_user(email='stranger@example.com')
        c = client_for(stranger)
        res = c.get(ENDPOINT.format(active_booking.id))
        assert res.status_code == 403
        assert res.data['code'] == 'forbidden'

    def test_admin_staff_can_obtain_token(self, video_sdk_env, active_booking):
        staff = f.make_user(email='staff@sharonesl.com', is_staff=True)
        c = client_for(staff)
        res = c.get(ENDPOINT.format(active_booking.id))
        assert res.status_code == 200
        assert res.data['role_type'] == 1

    def test_too_early_returns_409_outside_window(self, video_sdk_env):
        # Lesson starting in 60 minutes (classroom opens 15m before)
        now = timezone.now()
        future_booking = f.make_booking(
            status=S.CONFIRMED,
            start=now + timedelta(minutes=60),
        )
        c = client_for(future_booking.student)
        res = c.get(ENDPOINT.format(future_booking.id))
        assert res.status_code == 409
        assert res.data['code'] == 'outside_lesson_window'

    def test_cancelled_booking_returns_409(self, video_sdk_env):
        now = timezone.now()
        cancelled_booking = f.make_booking(
            status=S.CANCELLED_BY_STUDENT,
            start=now + timedelta(minutes=5),
        )
        c = client_for(cancelled_booking.student)
        res = c.get(ENDPOINT.format(cancelled_booking.id))
        assert res.status_code == 409
        assert res.data['code'] == 'booking_cancelled'

    @pytest.mark.parametrize('bad_status', [
        S.PENDING_PAYMENT, S.COMPLETED, S.COMPLETED_PENDING_MEMO, S.DISPUTED,
        S.STUDENT_NO_SHOW, S.TEACHER_NO_SHOW,
    ])
    def test_only_confirmed_or_in_progress_lessons_get_a_token(self, video_sdk_env, bad_status):
        """An unpaid (pending_payment) or already settled lesson must never open a classroom."""
        booking = f.make_booking(status=bad_status, start=timezone.now() + timedelta(minutes=5))
        for user in (booking.student, booking.teacher.user):
            res = client_for(user).get(ENDPOINT.format(booking.id))
            assert res.status_code == 409, bad_status
            assert res.data['code'] == 'classroom_unavailable'

    def test_in_progress_lesson_still_gets_a_token(self, video_sdk_env):
        booking = f.make_booking(status=S.IN_PROGRESS, start=timezone.now() - timedelta(minutes=5))
        assert client_for(booking.student).get(ENDPOINT.format(booking.id)).status_code == 200

    def test_stranger_learns_nothing_about_a_cancelled_booking(self, video_sdk_env):
        """Authorization comes before the status check: no booking-status oracle for non-parties."""
        booking = f.make_booking(status=S.CANCELLED_BY_STUDENT, start=timezone.now() + timedelta(minutes=5))
        res = client_for(f.make_user(email='nosy@example.com')).get(ENDPOINT.format(booking.id))
        assert res.status_code == 403
        assert res.data['code'] == 'forbidden'

    def test_nonexistent_booking_returns_404(self, video_sdk_env):
        user = f.make_user(email='any@example.com')
        c = client_for(user)
        res = c.get(ENDPOINT.format(uuid.uuid4()))
        assert res.status_code == 404
        assert res.data['code'] == 'not_found'

    def test_unconfigured_service_returns_503(self, settings, active_booking):
        settings.ZOOM_VIDEO_SDK_KEY = ''
        settings.ZOOM_VIDEO_SDK_SECRET = ''
        c = client_for(active_booking.student)
        res = c.get(ENDPOINT.format(active_booking.id))
        assert res.status_code == 503
        assert res.data['code'] == 'video_unconfigured'
