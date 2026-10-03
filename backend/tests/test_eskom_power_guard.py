from datetime import timedelta
from decimal import Decimal

import pytest
import requests
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.bookings.models import Booking
from apps.integrations.models import EskomAreaStatus, EskomNotificationAttempt
from apps.integrations.services.eskom import EskomProviderError, EskomQuotaError, EskomSePushClient
from apps.integrations.tasks import send_eskom_notification_task, sync_eskom_statuses
from apps.payments.models import PaymentTransaction
from apps.payments.services.funding import ensure_gateway_funding


STATUS_URL = '/api/v1/integrations/eskom/status/'
BACKUP_URL = '/api/v1/teachers/profile/power-backup/'


def client(user):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return api


def area_status(area_id, *, stage=0, start=None, end=None, retrieved_at=None):
    retrieved_at = retrieved_at or timezone.now()
    outages = [] if start is None else [{'start': start.isoformat(), 'end': end.isoformat(), 'note': 'planned'}]
    return {
        'area_id': area_id, 'area_name': 'Provider Area', 'stage': stage,
        'outages': outages, 'retrieved_at': retrieved_at,
    }


class FakeProvider:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def fetch_area_status(self, area_id):
        if self.error:
            raise self.error
        return {**self.payload, 'area_id': area_id}


def booking(teacher, student, *, minutes=30):
    start = timezone.now() + timedelta(minutes=minutes)
    return Booking.objects.create(
        teacher=teacher, student=student, status=Booking.Status.CONFIRMED,
        start_time_utc=start, end_time_utc=start + timedelta(minutes=25),
    )


def fund(item):
    tx = PaymentTransaction.objects.create(
        booking=item, gateway=PaymentTransaction.Gateway.PAYPAL,
        gateway_reference=f'eskom-{item.id}', amount=Decimal('9.00'), currency='USD',
        status=PaymentTransaction.Status.SUCCESS, fx_rate_to_zar=Decimal('18'), fx_source='test',
    )
    ensure_gateway_funding(tx, item)


@pytest.mark.django_db
class TestEskomSync:
    def test_real_stage_zero_is_cached_without_fabrication(self, teacher_user):
        teacher_user.eskom_area_id = 'area-zero'
        teacher_user.save(update_fields=['eskom_area_id'])
        result = sync_eskom_statuses(FakeProvider(area_status('area-zero', stage=0)))
        row = EskomAreaStatus.objects.get(area_id='area-zero')
        assert result['synced_areas'] == 1 and row.stage == 0
        assert row.provider_status == EskomAreaStatus.ProviderStatus.OK

    def test_overlap_creates_durable_idempotent_attempts_and_backup_exempts(self, teacher_user, student_user, monkeypatch):
        teacher_user.eskom_area_id = 'area-risk'
        teacher_user.save(update_fields=['eskom_area_id'])
        lesson = booking(teacher_user, student_user)
        start = lesson.start_time_utc - timedelta(minutes=5)
        end = lesson.end_time_utc + timedelta(minutes=5)
        monkeypatch.setattr(send_eskom_notification_task, 'delay', lambda *_: None)

        first = sync_eskom_statuses(FakeProvider(area_status('area-risk', stage=3, start=start, end=end)))
        second = sync_eskom_statuses(FakeProvider(area_status('area-risk', stage=3, start=start, end=end)))
        assert first['notifications_created'] == 2 and second['notifications_created'] == 0
        assert EskomNotificationAttempt.objects.filter(booking=lesson).count() == 2

        EskomNotificationAttempt.objects.all().delete()
        teacher_user.has_inverter_backup = teacher_user.has_lte_failover = True
        teacher_user.save(update_fields=['has_inverter_backup', 'has_lte_failover'])
        exempt = sync_eskom_statuses(FakeProvider(area_status('area-risk', stage=3, start=start, end=end)))
        assert exempt['vulnerable_bookings_flagged'] == 0

    def test_quota_keeps_last_known_data_and_labels_it(self, teacher_user):
        teacher_user.eskom_area_id = 'area-quota'
        teacher_user.save(update_fields=['eskom_area_id'])
        sync_eskom_statuses(FakeProvider(area_status('area-quota', stage=4)))
        result = sync_eskom_statuses(FakeProvider(error=EskomQuotaError('quota', 'limit')))
        row = EskomAreaStatus.objects.get(area_id='area-quota')
        assert result['failed_areas'] == 1 and row.stage == 4
        assert row.provider_status == EskomAreaStatus.ProviderStatus.QUOTA


@pytest.mark.django_db
class TestEskomApi:
    def test_fresh_and_stale_status_are_explicit(self, teacher_user):
        teacher_user.eskom_area_id = 'api-area'
        teacher_user.save(update_fields=['eskom_area_id'])
        now = timezone.now()
        row = EskomAreaStatus.objects.create(
            area_id='api-area', area_name='API Area', stage=0, outages=[],
            provider_retrieved_at=now, fresh_until=now + timedelta(minutes=5),
        )
        response = client(teacher_user.user).get(STATUS_URL)
        assert response.status_code == 200
        assert response.json()['stage'] == 0 and response.json()['stale'] is False

        row.fresh_until = now - timedelta(seconds=1)
        row.save(update_fields=['fresh_until'])
        stale = client(teacher_user.user).get(STATUS_URL).json()
        assert stale['stale'] is True and stale['provider_status'] == 'stale'

    def test_missing_cached_status_fails_without_inventing_stage(self, teacher_user):
        teacher_user.eskom_area_id = 'missing-area'
        teacher_user.save(update_fields=['eskom_area_id'])
        response = client(teacher_user.user).get(STATUS_URL)
        assert response.status_code == 503 and 'stage' not in response.json()

    def test_tutor_can_only_patch_own_backup_flags(self, teacher_user, student_user):
        response = client(teacher_user.user).patch(
            BACKUP_URL, {'has_inverter_backup': True, 'has_lte_failover': True}, format='json',
        )
        assert response.status_code == 200
        teacher_user.refresh_from_db()
        assert teacher_user.has_inverter_backup and teacher_user.has_lte_failover
        assert client(student_user).patch(BACKUP_URL, {'has_inverter_backup': False}, format='json').status_code == 403


@pytest.mark.django_db
class TestOutageCorroboration:
    def test_student_report_requires_fresh_active_provider_outage(self, teacher_user, student_user):
        teacher_user.eskom_area_id = 'report-area'
        teacher_user.save(update_fields=['eskom_area_id'])
        item = booking(teacher_user, student_user, minutes=5)
        fund(item)
        url = f'/api/v1/bookings/{item.id}/report-outage/'
        assert client(student_user).post(url).status_code == 409

        now = timezone.now()
        EskomAreaStatus.objects.create(
            area_id='report-area', area_name='Report Area', stage=2,
            outages=[{'start': (now - timedelta(minutes=5)).isoformat(),
                      'end': (now + timedelta(minutes=30)).isoformat(), 'note': 'active'}],
            provider_retrieved_at=now, fresh_until=now + timedelta(minutes=20),
        )
        accepted = client(student_user).post(url)
        assert accepted.status_code == 200 and accepted.json()['refunded'] is True


class TestProviderClient:
    def test_timeout_and_quota_are_structured(self):
        class TimeoutSession:
            def get(self, *args, **kwargs):
                raise requests.Timeout('slow')
        with pytest.raises(EskomProviderError) as timeout:
            EskomSePushClient(api_key='x', session=TimeoutSession()).fetch_area_status('a')
        assert timeout.value.code == 'timeout'

        class QuotaResponse:
            status_code = 429
        class QuotaSession:
            def get(self, *args, **kwargs):
                return QuotaResponse()
        with pytest.raises(EskomQuotaError) as quota:
            EskomSePushClient(api_key='x', session=QuotaSession()).fetch_area_status('a')
        assert quota.value.code == 'quota'


@pytest.mark.django_db
def test_notification_delivery_is_durable(teacher_user, student_user, monkeypatch):
    teacher_user.eskom_area_id = 'mail-area'
    teacher_user.save(update_fields=['eskom_area_id'])
    item = booking(teacher_user, student_user)
    now = timezone.now()
    status = EskomAreaStatus.objects.create(
        area_id='mail-area', area_name='Mail Area', stage=2, outages=[],
        provider_retrieved_at=now, fresh_until=now + timedelta(minutes=5),
    )
    attempt = EskomNotificationAttempt.objects.create(
        idempotency_key='mail-attempt', booking=item, recipient=student_user, area_status=status,
    )
    sent = []
    monkeypatch.setattr('apps.integrations.email.send_email', lambda *args: sent.append(args))
    send_eskom_notification_task.run(str(attempt.id))
    attempt.refresh_from_db()
    assert attempt.state == EskomNotificationAttempt.State.SENT and attempt.attempts == 1
    assert sent and sent[0][0] == student_user.email
