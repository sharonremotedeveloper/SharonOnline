"""Tests for Resend Svix webhook receiver (slice N3)."""
import base64
import hashlib
import hmac
import json
import time

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

import factories as f
from apps.notifications.models import Notification, NotificationPreference


TEST_SECRET = 'whsec_' + base64.b64encode(b'a' * 32).decode('utf-8')


def make_svix_headers(payload_bytes: bytes, secret: str, timestamp: int = None, msg_id: str = 'msg_test_123'):
    ts = str(timestamp or int(time.time()))
    clean_secret = secret[6:] if secret.startswith('whsec_') else secret
    key = base64.b64decode(clean_secret)
    to_sign = f'{msg_id}.{ts}.'.encode('utf-8') + payload_bytes
    mac = hmac.new(key, to_sign, hashlib.sha256).digest()
    sig = base64.b64encode(mac).decode('utf-8')
    return {
        'HTTP_SVIX_ID': msg_id,
        'HTTP_SVIX_TIMESTAMP': ts,
        'HTTP_SVIX_SIGNATURE': f'v1,{sig}',
    }


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=TEST_SECRET)
def test_resend_webhook_bounced_updates_notification_and_preference():
    client = APIClient()
    student = f.make_student(email='bounce_test@example.test')
    notif = Notification.objects.create(
        user=student,
        kind='reminder_24h',
        title='Lesson Reminder',
        body='Reminder',
        payload={},
        idempotency_key='test-key-bounce-1',
        provider_message_id='msg_resend_bounce_100',
        email_state=Notification.EmailState.SENT,
    )

    body = {
        'type': 'email.bounced',
        'data': {
            'email_id': 'msg_resend_bounce_100',
            'to': [student.email],
        },
    }
    raw = json.dumps(body).encode('utf-8')
    headers = make_svix_headers(raw, TEST_SECRET)

    response = client.post('/api/v1/notifications/webhooks/resend/', data=raw, content_type='application/json', **headers)
    assert response.status_code == 200
    assert response.data == {'received': True, 'action': 'suppressed'}

    notif.refresh_from_db()
    assert notif.email_state == Notification.EmailState.BOUNCED
    assert notif.email_last_error == 'bounced'

    pref = NotificationPreference.objects.filter(user=student).first()
    assert pref is not None
    # Optional category should be False
    assert pref.email_by_kind.get('reminder_24h') is False
    # Mandatory categories should not be marked False
    assert 'cancellation' not in pref.email_by_kind or pref.email_by_kind.get('cancellation') is not False


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=TEST_SECRET)
def test_resend_webhook_complaint_suppresses_preference():
    client = APIClient()
    student = f.make_student(email='complaint_test@example.test')
    body = {
        'type': 'email.complained',
        'data': {
            'email_id': 'msg_unknown_resend',
            'to': [student.email],
        },
    }
    raw = json.dumps(body).encode('utf-8')
    headers = make_svix_headers(raw, TEST_SECRET)

    response = client.post('/api/v1/notifications/webhooks/resend/', data=raw, content_type='application/json', **headers)
    assert response.status_code == 200
    assert response.data == {'received': True, 'action': 'suppressed'}

    pref = NotificationPreference.objects.filter(user=student).first()
    assert pref is not None
    assert pref.email_by_kind.get('reminder_24h') is False


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=TEST_SECRET)
def test_resend_webhook_invalid_signature_rejected():
    client = APIClient()
    raw = b'{"type": "email.bounced"}'
    headers = {
        'HTTP_SVIX_ID': 'bad_msg',
        'HTTP_SVIX_TIMESTAMP': str(int(time.time())),
        'HTTP_SVIX_SIGNATURE': 'v1,invalid_signature_here',
    }
    response = client.post('/api/v1/notifications/webhooks/resend/', data=raw, content_type='application/json', **headers)
    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=TEST_SECRET)
def test_resend_webhook_expired_timestamp_rejected():
    client = APIClient()
    raw = b'{"type": "email.bounced"}'
    expired_ts = int(time.time()) - 400
    headers = make_svix_headers(raw, TEST_SECRET, timestamp=expired_ts)
    response = client.post('/api/v1/notifications/webhooks/resend/', data=raw, content_type='application/json', **headers)
    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=TEST_SECRET)
def test_resend_webhook_ignored_event_type():
    client = APIClient()
    body = {'type': 'email.delivered', 'data': {'email_id': 'msg_123'}}
    raw = json.dumps(body).encode('utf-8')
    headers = make_svix_headers(raw, TEST_SECRET)
    response = client.post('/api/v1/notifications/webhooks/resend/', data=raw, content_type='application/json', **headers)
    assert response.status_code == 200
    assert response.data == {'received': True, 'action': 'ignored'}
