"""A video-only trial never creates a Booking or any financial record."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, VideoTrial
from apps.payments.models import PaymentTransaction


@pytest.fixture
def trial(db, teacher_user, student_user, admin_user):
    now = timezone.now()
    return VideoTrial.objects.create(
        teacher=teacher_user.user, student=student_user, created_by=admin_user,
        opens_at=now - timedelta(minutes=1), closes_at=now + timedelta(minutes=45),
        enabled=True,
    )


def client_for(user):
    client = APIClient()
    if user:
        client.force_authenticate(user)
    return client


@pytest.mark.django_db
def test_only_named_participants_receive_distinct_tokens(trial, teacher_user, student_user, admin_user, settings):
    settings.DAILY_API_KEY = 'test-daily-key'
    with patch('apps.bookings.video_trial_views.DailyClient') as client_cls:
        client_cls.return_value.create_meeting_token.side_effect = ['teacher-token', 'student-token']
        tutor = client_for(teacher_user.user).get(f'/api/v1/bookings/video-trials/{trial.id}/token/')
        student = client_for(student_user).get(f'/api/v1/bookings/video-trials/{trial.id}/token/')
        assert tutor.status_code == student.status_code == 200
        assert tutor.data['is_owner'] is True
        assert student.data['is_owner'] is False
        assert tutor.data['session_name'] == student.data['session_name'] == f'trial-{trial.id}'
        assert tutor.data['token'] != student.data['token']
        assert tutor['Cache-Control'] == student['Cache-Control'] == 'no-store'
        assert client_for(admin_user).get(f'/api/v1/bookings/video-trials/{trial.id}/token/').status_code == 404
        assert client_for(None).get(f'/api/v1/bookings/video-trials/{trial.id}/token/').status_code == 401
    assert Booking.objects.count() == 0
    assert PaymentTransaction.objects.count() == 0


@pytest.mark.django_db
def test_trial_fails_closed_for_disabled_expired_or_unconfigured(trial, teacher_user, settings):
    url = f'/api/v1/bookings/video-trials/{trial.id}/token/'
    settings.DAILY_API_KEY = 'test-daily-key'
    trial.enabled = False
    trial.save(update_fields=['enabled'])
    assert client_for(teacher_user.user).get(url).status_code == 404
    trial.enabled = True
    trial.closes_at = timezone.now() - timedelta(seconds=1)
    trial.save(update_fields=['enabled', 'closes_at'])
    assert client_for(teacher_user.user).get(url).status_code == 409
    trial.closes_at = timezone.now() + timedelta(minutes=5)
    trial.save(update_fields=['closes_at'])
    settings.DAILY_API_KEY = ''
    settings.DAILY_SIMULATE_WITHOUT_CREDENTIALS = False
    assert client_for(teacher_user.user).get(url).status_code == 503


@pytest.mark.django_db
def test_trial_rejects_wrong_roles_and_oversized_window(teacher_user, student_user, admin_user):
    trial = VideoTrial(
        teacher=student_user, student=teacher_user.user, created_by=admin_user,
        opens_at=timezone.now(), closes_at=timezone.now() + timedelta(hours=3),
    )
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        trial.full_clean()


@pytest.mark.django_db
def test_token_endpoint_defends_against_invalid_rows(trial, teacher_user, settings):
    settings.DAILY_API_KEY = 'test-daily-key'
    trial.closes_at = trial.opens_at + timedelta(hours=3)
    trial.save(update_fields=['closes_at'])
    assert client_for(teacher_user.user).get(f'/api/v1/bookings/video-trials/{trial.id}/token/').status_code == 409
