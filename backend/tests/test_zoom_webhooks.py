import json
import time
import hmac
import hashlib
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone
from django.conf import settings
from rest_framework.test import APIClient

from apps.bookings.models import Booking, AttendanceAudit
from apps.admin_api.models import DisputeCase
from apps.bookings.tasks import audit_attendance_and_noshows_task
from apps.integrations.zoom import zoom_client


def generate_zoom_headers(raw_body_bytes: bytes, secret: str = None, timestamp: int = None):
    if secret is None:
        secret = zoom_client.get_webhook_secret()
    if timestamp is None:
        timestamp = int(time.time())

    body_str = raw_body_bytes.decode('utf-8')
    message = f"v0:{timestamp}:{body_str}"
    sig_hash = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
    signature = f"v0={sig_hash}"

    return {
        'HTTP_X_ZM_SIGNATURE': signature,
        'HTTP_X_ZM_REQUEST_TIMESTAMP': str(timestamp),
        'CONTENT_TYPE': 'application/json'
    }


@pytest.fixture
def zoom_booking(teacher_user, student_user):
    from apps.teachers.models import TeacherProfile
    teacher_profile = teacher_user if isinstance(teacher_user, TeacherProfile) else TeacherProfile.objects.get(user=teacher_user)
    start_utc = timezone.now() + timedelta(hours=1)
    return Booking.objects.create(
        teacher=teacher_profile,
        student=student_user,
        start_time_utc=start_utc,
        end_time_utc=start_utc + timedelta(minutes=25),
        status=Booking.Status.CONFIRMED,
        zoom_meeting_id="98765432101",
        zoom_join_url="https://zoom.us/j/98765432101",
        zoom_start_url="https://zoom.us/s/98765432101"
    )


@pytest.mark.django_db
def test_zoom_url_validation_handshake():
    client = APIClient()
    payload = {
        "event": "endpoint.url_validation",
        "payload": {
            "plainToken": "challenge_token_abc123"
        },
        "event_ts": int(time.time() * 1000)
    }
    raw_body = json.dumps(payload).encode('utf-8')

    response = client.post(
        '/api/v1/integrations/zoom/webhook/',
        data=raw_body,
        content_type='application/json'
    )

    assert response.status_code == 200
    data = response.json()
    assert data["plainToken"] == "challenge_token_abc123"

    secret = zoom_client.get_webhook_secret()
    expected_encrypted = hmac.new(
        secret.encode('utf-8'),
        "challenge_token_abc123".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    assert data["encryptedToken"] == expected_encrypted


@pytest.mark.django_db
def test_zoom_hmac_signature_verification_success(zoom_booking):
    client = APIClient()
    payload = {
        "event": "meeting.participant_joined",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id,
                "host_id": "host_user_123",
                "participant": {
                    "user_id": "zoom_user_teacher_1",
                    "user_name": "Teacher Tester",
                    "email": zoom_booking.teacher.user.email,
                    "join_time": "2026-10-01T10:00:00Z"
                }
            }
        }
    }
    raw_body = json.dumps(payload).encode('utf-8')
    headers = generate_zoom_headers(raw_body)

    response = client.post('/api/v1/integrations/zoom/webhook/', data=raw_body, content_type='application/json', **headers)
    assert response.status_code == 200

    zoom_booking.refresh_from_db()
    assert zoom_booking.status == Booking.Status.IN_PROGRESS

    audit = AttendanceAudit.objects.filter(booking=zoom_booking, participant_email=zoom_booking.teacher.user.email).first()
    assert audit is not None
    assert audit.zoom_user_id == "zoom_user_teacher_1"


@pytest.mark.django_db
def test_zoom_hmac_tampered_payload_rejected(zoom_booking):
    client = APIClient()
    payload = {
        "event": "meeting.participant_joined",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id,
                "participant": {
                    "email": zoom_booking.teacher.user.email
                }
            }
        }
    }
    raw_body = json.dumps(payload).encode('utf-8')
    headers = generate_zoom_headers(raw_body)

    # Tamper payload
    tampered_body = json.dumps({"tampered": True}).encode('utf-8')

    response = client.post('/api/v1/integrations/zoom/webhook/', data=tampered_body, content_type='application/json', **headers)
    assert response.status_code == 401
    assert "Invalid HMAC signature" in response.json()["error"]


@pytest.mark.django_db
def test_zoom_replay_attack_rejected(zoom_booking):
    client = APIClient()
    payload = {
        "event": "meeting.participant_joined",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id,
                "participant": {
                    "email": zoom_booking.teacher.user.email
                }
            }
        }
    }
    raw_body = json.dumps(payload).encode('utf-8')
    # Timestamp older than 300 seconds
    stale_timestamp = int(time.time()) - 350
    headers = generate_zoom_headers(raw_body, timestamp=stale_timestamp)

    response = client.post('/api/v1/integrations/zoom/webhook/', data=raw_body, content_type='application/json', **headers)
    assert response.status_code == 401
    assert "replay guard" in response.json()["error"]


@pytest.mark.django_db
def test_out_of_order_participant_left_then_joined(zoom_booking):
    client = APIClient()
    teacher_email = zoom_booking.teacher.user.email

    # 1. Packet 1 arrives: participant_left at 10:25:00
    left_payload = {
        "event": "meeting.participant_left",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id,
                "participant": {
                    "user_id": "usr_ooo_1",
                    "email": teacher_email,
                    "leave_time": "2026-10-01T10:25:00Z"
                }
            }
        }
    }
    body1 = json.dumps(left_payload).encode('utf-8')
    res1 = client.post('/api/v1/integrations/zoom/webhook/', data=body1, content_type='application/json', **generate_zoom_headers(body1))
    assert res1.status_code == 200

    audit1 = AttendanceAudit.objects.get(booking=zoom_booking, participant_email=teacher_email)
    assert audit1.leave_time_utc is not None
    assert audit1.join_time_utc is None
    assert audit1.total_minutes == 0

    # 2. Packet 2 arrives: participant_joined at 10:00:00 (25m earlier)
    joined_payload = {
        "event": "meeting.participant_joined",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id,
                "participant": {
                    "user_id": "usr_ooo_1",
                    "email": teacher_email,
                    "join_time": "2026-10-01T10:00:00Z"
                }
            }
        }
    }
    body2 = json.dumps(joined_payload).encode('utf-8')
    res2 = client.post('/api/v1/integrations/zoom/webhook/', data=body2, content_type='application/json', **generate_zoom_headers(body2))
    assert res2.status_code == 200

    audit1.refresh_from_db()
    assert audit1.join_time_utc is not None
    # 25 minutes duration correctly calculated!
    assert audit1.total_minutes == 25


@pytest.mark.django_db
def test_meeting_ended_finalizes_open_records(zoom_booking):
    client = APIClient()
    teacher_email = zoom_booking.teacher.user.email

    # Participant joined without leave event
    join_payload = {
        "event": "meeting.participant_joined",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id,
                "participant": {
                    "user_id": "usr_open_1",
                    "email": teacher_email,
                    "join_time": (timezone.now() - timedelta(minutes=24)).isoformat()
                }
            }
        }
    }
    b1 = json.dumps(join_payload).encode('utf-8')
    client.post('/api/v1/integrations/zoom/webhook/', data=b1, content_type='application/json', **generate_zoom_headers(b1))

    # meeting.ended received
    ended_payload = {
        "event": "meeting.ended",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id
            }
        }
    }
    b2 = json.dumps(ended_payload).encode('utf-8')
    res2 = client.post('/api/v1/integrations/zoom/webhook/', data=b2, content_type='application/json', **generate_zoom_headers(b2))
    assert res2.status_code == 200

    audit = AttendanceAudit.objects.get(booking=zoom_booking, participant_email=teacher_email)
    assert audit.leave_time_utc is not None
    assert audit.total_minutes >= 23


@pytest.mark.django_db
def test_active_zoom_probe_prevents_false_teacher_no_show(zoom_booking):
    """
    Task 6.2 (Pillar 1 Active Probe Guard):
    At T+10m, AttendanceAudit has not arrived in DB yet, but active Zoom API probe
    detects active meeting. Prevents TEACHER_NO_SHOW status, SLA strikes, and credit refunds.
    """
    now = timezone.now()
    zoom_booking.start_time_utc = now - timedelta(minutes=11)
    zoom_booking.end_time_utc = zoom_booking.start_time_utc + timedelta(minutes=25)
    zoom_booking.save()

    # Pre-populate student attendance to ensure booking moves to IN_PROGRESS
    AttendanceAudit.objects.create(
        booking=zoom_booking,
        participant_email=zoom_booking.student.email,
        join_time_utc=zoom_booking.start_time_utc
    )

    teacher = zoom_booking.teacher
    initial_strikes = teacher.sla_strikes

    # Mock ZoomClient.get_meeting_status to return active meeting
    with patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'started', 'participant_count': 2}):
        audit_attendance_and_noshows_task()

    zoom_booking.refresh_from_db()
    teacher.refresh_from_db()

    # Should be advanced to IN_PROGRESS, NOT TEACHER_NO_SHOW!
    assert zoom_booking.status == Booking.Status.IN_PROGRESS
    assert teacher.sla_strikes == initial_strikes
    assert AttendanceAudit.objects.filter(booking=zoom_booking, participant_email=teacher.user.email).exists()


@pytest.mark.django_db
def test_late_webhook_post_adjudication_quarantine_creates_dispute(zoom_booking):
    """
    Task 6.2 (Pillar 4 Post-Adjudication Quarantine):
    When a booking was already marked TEACHER_NO_SHOW at T+10m, but a late Zoom webhook
    arrives with proof of attendance, the booking is safely quarantined to DISPUTED
    and an audit DisputeCase is created for Sharon / Admin review in /admin/disputes.
    """
    client = APIClient()
    zoom_booking.status = Booking.Status.TEACHER_NO_SHOW
    zoom_booking.save()

    payload = {
        "event": "meeting.participant_joined",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id,
                "participant": {
                    "user_id": "late_tutor_1",
                    "email": zoom_booking.teacher.user.email,
                    "join_time": (timezone.now() - timedelta(minutes=15)).isoformat()
                }
            }
        }
    }
    raw_body = json.dumps(payload).encode('utf-8')
    res = client.post('/api/v1/integrations/zoom/webhook/', data=raw_body, content_type='application/json', **generate_zoom_headers(raw_body))
    assert res.status_code == 200

    zoom_booking.refresh_from_db()
    # Safely quarantined to DISPUTED
    assert zoom_booking.status == Booking.Status.DISPUTED

    # DisputeCase exists for Sharon / Admin arbitration
    dispute = DisputeCase.objects.filter(booking=zoom_booking).first()
    assert dispute is not None
    assert dispute.status == DisputeCase.Status.OPEN
    assert "Late Zoom" in dispute.student_statement


@pytest.mark.django_db
def test_concurrent_webhook_and_beat_interleaving(zoom_booking):
    """
    Task 6.2 (Pillar 2 Concurrency Mutual Exclusion & State Consistency):
    Verifies state safety when webhook arrives immediately before Celery Beat
    evaluates no-show candidates, ensuring no race conditions or false strikes.
    """
    teacher_email = zoom_booking.teacher.user.email
    payload = {
        "event": "meeting.participant_joined",
        "payload": {
            "object": {
                "id": zoom_booking.zoom_meeting_id,
                "participant": {
                    "user_id": "thread_tutor_1",
                    "email": teacher_email,
                    "join_time": timezone.now().isoformat()
                }
            }
        }
    }
    raw_body = json.dumps(payload).encode('utf-8')
    headers = generate_zoom_headers(raw_body)

    client = APIClient()
    res1 = client.post('/api/v1/integrations/zoom/webhook/', data=raw_body, content_type='application/json', **headers)
    assert res1.status_code == 200

    # Beat task executes immediately after
    res2 = audit_attendance_and_noshows_task()

    zoom_booking.refresh_from_db()
    # Booking must be IN_PROGRESS, not TEACHER_NO_SHOW
    assert zoom_booking.status == Booking.Status.IN_PROGRESS
    assert zoom_booking.teacher.sla_strikes == 0
    assert AttendanceAudit.objects.filter(booking=zoom_booking, participant_email=teacher_email).exists()



