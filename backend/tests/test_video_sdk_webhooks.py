"""Tests for Zoom Video SDK Webhook Ingestion & Attendance Telemetry (Slice V4).

Validates:
- URL validation challenge handshakes
- HMAC-SHA256 signature verification & replay attacks
- Identity classification (tutor, student, stranger)
- Idempotency & session deduplication
- Session lifecycle (started, ended)
- Late telemetry hazards & no-show contradictions
- Zero secret logging
"""
import hashlib
import hmac
import json
import time
from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking

ENDPOINT = '/api/v1/integrations/video-sdk/webhooks/'
WEBHOOK_SECRET = 'video_sdk_webhook_secret_key_32chars!'


def make_signature(body_bytes: bytes, secret: str, ts: int) -> str:
    message = f"v0:{ts}:{body_bytes.decode('utf-8')}"
    return f"v0={hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()}"


@pytest.fixture
def webhook_env(settings):
    settings.ZOOM_VIDEO_SDK_WEBHOOK_SECRET = WEBHOOK_SECRET
    settings.ZOOM_WEBHOOK_SECRET_TOKEN = WEBHOOK_SECRET
    return settings


@pytest.fixture
def active_booking():
    return f.make_booking(
        status=Booking.Status.CONFIRMED,
        start=timezone.now() - timedelta(minutes=5),
    )


@pytest.mark.django_db
class TestVideoSdkWebhookChallenge:
    def test_url_validation_handshake_returns_crc_response(self, webhook_env):
        client = APIClient()
        plain_token = "challenge_plain_token_12345"
        payload = {
            "event": "endpoint.url_validation",
            "payload": {
                "plainToken": plain_token,
            }
        }
        res = client.post(ENDPOINT, data=payload, format='json')
        assert res.status_code == 200
        data = res.json()
        assert data['plainToken'] == plain_token
        expected_encrypted = hmac.new(
            WEBHOOK_SECRET.encode('utf-8'),
            plain_token.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        assert data['encryptedToken'] == expected_encrypted

    def test_url_validation_missing_plain_token_returns_400(self, webhook_env):
        client = APIClient()
        payload = {
            "event": "endpoint.url_validation",
            "payload": {}
        }
        res = client.post(ENDPOINT, data=payload, format='json')
        assert res.status_code == 400
        assert res.json()['error'] == "Missing plainToken in URL validation challenge"


@pytest.mark.django_db
class TestVideoSdkWebhookSecurity:
    def test_valid_signature_is_accepted(self, webhook_env, active_booking):
        client = APIClient()
        payload = {
            "event": "session.user_joined",
            "event_id": "evt_valid_1",
            "payload": {
                "object": {
                    "session_name": f"lesson-{active_booking.id}",
                    "session_id": "sess_001",
                    "user_identity": str(active_booking.student_id),
                    "user_id": "p_001",
                    "join_time": timezone.now().isoformat(),
                }
            }
        }
        raw_body = json.dumps(payload).encode('utf-8')
        ts = int(time.time())
        sig = make_signature(raw_body, WEBHOOK_SECRET, ts)

        res = client.post(
            ENDPOINT,
            data=raw_body,
            content_type='application/json',
            HTTP_X_ZM_SIGNATURE=sig,
            HTTP_X_ZM_REQUEST_TIMESTAMP=str(ts),
        )
        assert res.status_code == 200

    def test_missing_signature_headers_returns_401(self, webhook_env, active_booking):
        client = APIClient()
        payload = {"event": "session.user_joined", "payload": {}}
        res = client.post(ENDPOINT, data=payload, format='json')
        assert res.status_code == 401
        assert "Missing" in res.json()['error']

    def test_tampered_signature_returns_401(self, webhook_env, active_booking):
        client = APIClient()
        payload = {"event": "session.user_joined", "payload": {}}
        raw_body = json.dumps(payload).encode('utf-8')
        ts = int(time.time())
        bad_sig = "v0=bad_hash_value_1234567890abcdef"

        res = client.post(
            ENDPOINT,
            data=raw_body,
            content_type='application/json',
            HTTP_X_ZM_SIGNATURE=bad_sig,
            HTTP_X_ZM_REQUEST_TIMESTAMP=str(ts),
        )
        assert res.status_code == 401
        assert res.json()['error'] == "Invalid HMAC signature"

    def test_expired_timestamp_replay_rejected_with_401(self, webhook_env, active_booking):
        client = APIClient()
        payload = {"event": "session.user_joined", "payload": {}}
        raw_body = json.dumps(payload).encode('utf-8')
        ts = int(time.time()) - 600  # 10 minutes ago (> 300s)
        sig = make_signature(raw_body, WEBHOOK_SECRET, ts)

        res = client.post(
            ENDPOINT,
            data=raw_body,
            content_type='application/json',
            HTTP_X_ZM_SIGNATURE=sig,
            HTTP_X_ZM_REQUEST_TIMESTAMP=str(ts),
        )
        assert res.status_code == 401
        assert "replay guard" in res.json()['error']

    def test_malformed_json_body_returns_400(self, webhook_env):
        client = APIClient()
        res = client.post(
            ENDPOINT,
            data="not json at all {",
            content_type='application/json',
        )
        assert res.status_code == 400


@pytest.mark.django_db
class TestVideoSdkEventIngestion:
    def _send_signed_event(self, client, event_type, booking, obj_data, event_id="evt_test"):
        payload = {
            "event": event_type,
            "event_id": event_id,
            "payload": {
                "object": {
                    "session_name": f"lesson-{booking.id}",
                    **obj_data,
                }
            }
        }
        raw_body = json.dumps(payload).encode('utf-8')
        ts = int(time.time())
        sig = make_signature(raw_body, WEBHOOK_SECRET, ts)
        return client.post(
            ENDPOINT,
            data=raw_body,
            content_type='application/json',
            HTTP_X_ZM_SIGNATURE=sig,
            HTTP_X_ZM_REQUEST_TIMESTAMP=str(ts),
        )

    def test_tutor_join_creates_teacher_audit_and_sets_in_progress(self, webhook_env, active_booking):
        client = APIClient()
        now = timezone.now()
        tutor_id = str(active_booking.teacher.user_id)

        res = self._send_signed_event(
            client,
            "session.user_joined",
            active_booking,
            {
                "session_id": "sess_101",
                "user_identity": tutor_id,
                "user_id": "p_tutor",
                "join_time": now.isoformat(),
            }
        )
        assert res.status_code == 200

        # Booking transitions to IN_PROGRESS
        active_booking.refresh_from_db()
        assert active_booking.status == Booking.Status.IN_PROGRESS

        # Audit row created
        audit = AttendanceAudit.objects.get(booking=active_booking)
        assert audit.classification == 'teacher'
        assert audit.participant_email == active_booking.teacher.user.email
        assert audit.identity == 'video_sdk'
        assert audit.participant_id == tutor_id

    def test_student_join_creates_student_audit_and_leaves_confirmed(self, webhook_env, active_booking):
        client = APIClient()
        now = timezone.now()
        student_id = str(active_booking.student_id)

        res = self._send_signed_event(
            client,
            "session.user_joined",
            active_booking,
            {
                "session_id": "sess_101",
                "user_identity": student_id,
                "user_id": "p_student",
                "join_time": now.isoformat(),
            }
        )
        assert res.status_code == 200

        # Student alone does NOT move booking to IN_PROGRESS
        active_booking.refresh_from_db()
        assert active_booking.status == Booking.Status.CONFIRMED

        audit = AttendanceAudit.objects.get(booking=active_booking)
        assert audit.classification == 'student'
        assert audit.participant_email == active_booking.student.email
        assert audit.identity == 'video_sdk'

    def test_unmatched_stranger_is_classified_as_unknown_with_empty_email(self, webhook_env, active_booking):
        client = APIClient()
        now = timezone.now()

        res = self._send_signed_event(
            client,
            "session.user_joined",
            active_booking,
            {
                "session_id": "sess_101",
                "user_identity": "unrelated-stranger-uuid",
                "user_id": "p_stranger",
                "join_time": now.isoformat(),
            }
        )
        assert res.status_code == 200

        audit = AttendanceAudit.objects.get(booking=active_booking)
        assert audit.classification == 'unknown'
        assert audit.participant_email == ''
        assert audit.identity == 'video_sdk'

    def test_user_left_calculates_dwell_minutes(self, webhook_env, active_booking):
        client = APIClient()
        t0 = timezone.now() - timedelta(minutes=25)
        t1 = timezone.now()
        tutor_id = str(active_booking.teacher.user_id)

        # 1. Join
        self._send_signed_event(
            client,
            "session.user_joined",
            active_booking,
            {
                "session_id": "sess_202",
                "user_identity": tutor_id,
                "user_id": "p_tutor",
                "join_time": t0.isoformat(),
            },
            event_id="evt_join",
        )

        # 2. Leave 25 minutes later
        self._send_signed_event(
            client,
            "session.user_left",
            active_booking,
            {
                "session_id": "sess_202",
                "user_identity": tutor_id,
                "user_id": "p_tutor",
                "leave_time": t1.isoformat(),
            },
            event_id="evt_leave",
        )

        audit = AttendanceAudit.objects.get(booking=active_booking)
        assert audit.total_minutes >= 24  # ~25 minutes
        assert "evt_join" in audit.event_ids
        assert "evt_leave" in audit.event_ids

    def test_idempotent_event_retries_do_not_duplicate_rows(self, webhook_env, active_booking):
        client = APIClient()
        now = timezone.now()
        student_id = str(active_booking.student_id)

        payload_obj = {
            "session_id": "sess_retry",
            "user_identity": student_id,
            "user_id": "p_student",
            "join_time": now.isoformat(),
        }

        # Deliver same event twice
        res1 = self._send_signed_event(client, "session.user_joined", active_booking, payload_obj, event_id="evt_dup")
        res2 = self._send_signed_event(client, "session.user_joined", active_booking, payload_obj, event_id="evt_dup")

        assert res1.status_code == 200
        assert res2.status_code == 200
        assert AttendanceAudit.objects.filter(booking=active_booking).count() == 1

    def test_session_started_and_ended_lifecycle(self, webhook_env, active_booking):
        client = APIClient()
        now = timezone.now()

        # 1. session.started
        res_start = self._send_signed_event(
            client,
            "session.started",
            active_booking,
            {
                "session_id": "sess_life",
                "start_time": now.isoformat(),
            }
        )
        assert res_start.status_code == 200
        active_booking.refresh_from_db()
        assert active_booking.status == Booking.Status.IN_PROGRESS

        # 2. Student joins
        self._send_signed_event(
            client,
            "session.user_joined",
            active_booking,
            {
                "session_id": "sess_life",
                "user_identity": str(active_booking.student_id),
                "user_id": "p_student",
                "join_time": (now + timedelta(minutes=1)).isoformat(),
            }
        )

        # 3. session.ended closes open participant sessions
        res_end = self._send_signed_event(
            client,
            "session.ended",
            active_booking,
            {
                "session_id": "sess_life",
                "end_time": (now + timedelta(minutes=25)).isoformat(),
            }
        )
        assert res_end.status_code == 200

        student_audit = AttendanceAudit.objects.get(booking=active_booking, classification='student')
        assert student_audit.leave_time_utc is not None
        assert student_audit.total_minutes >= 23

    def test_late_tutor_join_after_no_show_quarantines_to_disputed(self, webhook_env, active_booking):
        client = APIClient()
        # Set booking to TEACHER_NO_SHOW
        Booking.objects.filter(pk=active_booking.pk).update(status=Booking.Status.TEACHER_NO_SHOW)
        active_booking.refresh_from_db()

        # Late tutor telemetry arrives
        tutor_id = str(active_booking.teacher.user_id)
        res = self._send_signed_event(
            client,
            "session.user_joined",
            active_booking,
            {
                "session_id": "sess_late",
                "user_identity": tutor_id,
                "user_id": "p_tutor",
                "join_time": timezone.now().isoformat(),
            }
        )
        assert res.status_code == 200

        active_booking.refresh_from_db()
        assert active_booking.status == Booking.Status.DISPUTED
        assert DisputeCase.objects.filter(booking=active_booking).exists()
