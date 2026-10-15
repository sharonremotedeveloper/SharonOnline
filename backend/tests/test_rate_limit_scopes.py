"""Focused coverage for the targeted high-risk throttle policies."""

import logging

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from rest_framework import status
from rest_framework.test import APIClient

from apps.admin_api.refund_views import AdminRefundListView
from apps.bookings.views import BookingListCreateView, ReportOutageView, SubmitMemoView, TeacherSlotsView
from apps.common import throttles as throttle_module
from apps.common.throttles import ObservedScopedRateThrottle
from apps.integrations.views import GoogleCalendarCallbackView, GoogleCalendarConnectView
from apps.materials.views import MaterialDetailView, MaterialListView
from apps.payments.refund_views import RefundListView
from apps.payments.views import CreditBalanceView, CreditPackListView, CreditPurchaseStatusView, ReceiptPdfView, TutorStatementView, TutorWalletView
from apps.srs.views import StudentProfileView, UpdateFlashcardMasteryView
from apps.teachers.views import TeacherDetailView, TeacherListView, TeacherPowerBackupView, TeacherPrivateAssetDownloadView


def _assert_scope(view, scope):
    assert view.throttle_scope == scope
    assert any(throttle is ObservedScopedRateThrottle for throttle in view.throttle_classes)


@pytest.mark.parametrize(
    ('view', 'scope'),
    [
        (TeacherListView, 'public_teacher_directory'),
        (TeacherDetailView, 'public_teacher_detail'),
        (TeacherSlotsView, 'public_slots'),
        (MaterialListView, 'public_materials_directory'),
        (MaterialDetailView, 'public_materials_detail'),
        (CreditPackListView, 'credit_pack_list'),
        (RefundListView, 'student_refund_read'),
        (AdminRefundListView, 'admin_refund_read'),
        (SubmitMemoView, 'lesson_write'),
        (ReportOutageView, 'lesson_write'),
        (CreditBalanceView, 'financial_read'),
        (CreditPurchaseStatusView, 'purchase_status'),
        (TutorWalletView, 'financial_read'),
        (TutorStatementView, 'financial_export'),
        (ReceiptPdfView, 'financial_document'),
        (TeacherPowerBackupView, 'teacher_settings'),
        (TeacherPrivateAssetDownloadView, 'private_asset'),
        (GoogleCalendarConnectView, 'integration_write'),
        (GoogleCalendarCallbackView, 'integration_callback'),
        (UpdateFlashcardMasteryView, 'student_write'),
    ],
)
def test_high_risk_views_have_explicit_scopes(view, scope):
    _assert_scope(view, scope)


def test_booking_create_uses_a_write_scope_without_tightening_reads():
    assert BookingListCreateView.throttle_scope == 'booking_write'
    assert 'get_throttles' in BookingListCreateView.__dict__


def test_student_profile_only_throttles_patch():
    assert StudentProfileView.throttle_scope == 'student_write'
    assert 'get_throttles' in StudentProfileView.__dict__


def test_only_bounded_catalog_reads_fail_open():
    assert {
        'public_teacher_directory',
        'public_teacher_detail',
        'public_materials_directory',
        'public_materials_detail',
        'credit_pack_list',
    }.issubset(throttle_module.THROTTLE_FAIL_OPEN_SCOPES)
    assert 'public_default_read' in throttle_module.THROTTLE_FAIL_OPEN_SCOPES
    assert 'public_slots' not in throttle_module.THROTTLE_FAIL_OPEN_SCOPES
    assert 'public_teacher_availability' not in throttle_module.THROTTLE_FAIL_OPEN_SCOPES
    assert 'public_teacher_availability' in throttle_module.THROTTLE_FAIL_CLOSED_SCOPES


def test_default_throttles_use_the_resilient_classes(settings):
    assert settings.REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] == (
        'apps.common.throttles.ResilientAnonRateThrottle',
        'apps.common.throttles.ResilientUserRateThrottle',
    )


@pytest.mark.django_db
@pytest.mark.parametrize('failure', [RedisConnectionError, RedisTimeoutError], ids=['redis-connection', 'redis-timeout'])
def test_cheap_public_reads_fail_open_with_safe_warning(teacher_user, monkeypatch, caplog, failure):
    def unavailable(*args, **kwargs):
        raise failure('redis unavailable')

    monkeypatch.setattr(throttle_module.cache, 'add', unavailable)
    caplog.set_level(logging.WARNING, logger='security.rate_limit')

    response = APIClient().get('/api/v1/teachers/')

    assert response.status_code == status.HTTP_200_OK
    events = [record.getMessage() for record in caplog.records if record.name == 'security.rate_limit']
    assert any('rate_limit.cache_unavailable' in event and 'policy=fail_open' in event for event in events)
    assert 'redis unavailable' not in '\n'.join(events)


@pytest.mark.django_db
@pytest.mark.parametrize('failure', [RedisConnectionError, RedisTimeoutError], ids=['redis-connection', 'redis-timeout'])
def test_sensitive_reads_fail_closed_with_controlled_response(student_user, monkeypatch, caplog, failure):
    def unavailable(*args, **kwargs):
        raise failure('redis unavailable')

    monkeypatch.setattr(throttle_module.cache, 'add', unavailable)
    caplog.set_level(logging.WARNING, logger='security.rate_limit')
    client = APIClient()
    client.force_authenticate(student_user)

    response = client.get('/api/v1/payments/credits/')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data['detail'] == 'Rate limiting is temporarily unavailable. Please retry shortly.'
    events = '\n'.join(record.getMessage() for record in caplog.records if record.name == 'security.rate_limit')
    assert 'policy=fail_closed' in events
    assert 'redis unavailable' not in events


@pytest.mark.django_db
@pytest.mark.parametrize('failure', [RedisConnectionError, RedisTimeoutError], ids=['redis-connection', 'redis-timeout'])
def test_existing_login_throttle_fails_closed_without_exposing_redis_error(monkeypatch, caplog, failure):
    def unavailable(*args, **kwargs):
        raise failure('redis unavailable')

    monkeypatch.setattr(throttle_module.cache, 'get', unavailable)
    caplog.set_level(logging.WARNING, logger='security.rate_limit')

    response = APIClient().post('/api/v1/auth/token/', {'username': 'a', 'password': 'b'}, format='json')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data['detail'] == 'Rate limiting is temporarily unavailable. Please retry shortly.'
    events = '\n'.join(record.getMessage() for record in caplog.records if record.name == 'security.rate_limit')
    assert 'scope=login' in events
    assert 'redis unavailable' not in events


@pytest.mark.django_db
def test_public_slots_scope_returns_429_and_emits_privacy_safe_event(teacher_user, monkeypatch, caplog):
    monkeypatch.setitem(ObservedScopedRateThrottle.THROTTLE_RATES, 'public_slots', '1/min')
    caplog.set_level(logging.WARNING, logger='security.rate_limit')

    client = APIClient()
    url = f'/api/v1/bookings/slots/{teacher_user.id}/?days=1&tz=UTC'
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 429
    events = '\n'.join(record.getMessage() for record in caplog.records if record.name == 'security.rate_limit')
    assert events == ''  # single 429s are counted, not logged individually
    assert str(teacher_user.id) not in events


@pytest.mark.django_db
def test_booking_create_scope_is_applied_before_validation(student_user, monkeypatch):
    monkeypatch.setitem(ObservedScopedRateThrottle.THROTTLE_RATES, 'booking_write', '2/min')
    client = APIClient()
    client.force_authenticate(student_user)

    responses = [client.post('/api/v1/bookings/', {}, format='json') for _ in range(3)]
    assert [response.status_code for response in responses] == [400, 400, 429]


@pytest.mark.django_db
def test_authenticated_scope_requires_both_user_and_ip_buckets(student_user, monkeypatch):
    monkeypatch.setitem(ObservedScopedRateThrottle.THROTTLE_RATES, 'booking_write', '1/min')
    client = APIClient()
    client.force_authenticate(student_user)
    body = {}

    first = client.post('/api/v1/bookings/', body, format='json', REMOTE_ADDR='198.51.100.10')
    second_ip = client.post('/api/v1/bookings/', body, format='json', REMOTE_ADDR='198.51.100.11')
    assert [first.status_code, second_ip.status_code] == [400, 429]


@pytest.mark.django_db
def test_repeated_denials_escalate_once_with_hashed_identities(teacher_user, monkeypatch, caplog):
    monkeypatch.setitem(ObservedScopedRateThrottle.THROTTLE_RATES, 'public_slots', '1/min')
    monkeypatch.setattr(throttle_module, 'ABUSE_ESCALATION_THRESHOLD', 2)
    caplog.set_level('ERROR', logger='security.rate_limit')

    client = APIClient()
    url = f'/api/v1/bookings/slots/{teacher_user.id}/?days=1&tz=UTC'
    assert client.get(url, REMOTE_ADDR='198.51.100.20').status_code == 200
    assert client.get(url, REMOTE_ADDR='198.51.100.20').status_code == 429
    assert client.get(url, REMOTE_ADDR='198.51.100.20').status_code == 429
    assert client.get(url, REMOTE_ADDR='198.51.100.20').status_code == 429

    events = [record.getMessage() for record in caplog.records if record.name == 'security.rate_limit']
    escalations = [event for event in events if 'rate_limit.abuse_escalated' in event]
    assert len(escalations) == 1
    assert '198.51.100.20' not in escalations[0]
    assert str(teacher_user.id) not in escalations[0]
