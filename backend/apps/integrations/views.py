import json
import logging
import dateutil.parser
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.bookings.models import Booking, AttendanceAudit
from apps.admin_api.models import DisputeCase
from .zoom import zoom_client

logger = logging.getLogger(__name__)


class ZoomWebhookReceiverView(APIView):
    """
    Task 6.1 & 6.2: High-reliability Zoom Webhook Ingestion Receiver
    with HMAC-SHA256 signature verification, URL validation challenge handshakes,
    and Late Webhook Concurrency Guards.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'webhook'

    def post(self, request, *args, **kwargs):
        # 1. Parse JSON payload
        try:
            payload_data = json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as e:
            logger.error(f"[ZOOM WEBHOOK] Malformed JSON payload: {e}")
            return Response({"error": "Malformed JSON payload"}, status=status.HTTP_400_BAD_REQUEST)

        event = payload_data.get('event')

        # 2. Zoom Endpoint URL Validation Handshake (Challenge-Response CRC)
        if event == 'endpoint.url_validation':
            plain_token = payload_data.get('payload', {}).get('plainToken', '')
            if not plain_token:
                return Response({"error": "Missing plainToken in URL validation challenge"}, status=status.HTTP_400_BAD_REQUEST)
            crc_response = zoom_client.generate_url_validation_response(plain_token)
            logger.info("[ZOOM WEBHOOK] Handshake challenge responded successfully.")
            return Response(crc_response, status=status.HTTP_200_OK)

        # 3. HMAC-SHA256 Signature Verification & Replay Attack Defense
        # Inspect Django request.META for HTTP headers
        headers_dict = {
            'x-zm-signature': request.META.get('HTTP_X_ZM_SIGNATURE', request.headers.get('x-zm-signature', '')),
            'x-zm-request-timestamp': request.META.get('HTTP_X_ZM_REQUEST_TIMESTAMP', request.headers.get('x-zm-request-timestamp', ''))
        }

        is_valid, reason = zoom_client.verify_webhook_signature(headers_dict, request.body)
        if not is_valid:
            logger.warning(f"[ZOOM WEBHOOK] Unauthorized request rejected: {reason}")
            return Response({"error": reason}, status=status.HTTP_401_UNAUTHORIZED)

        # 4. Extract meeting object & participant data
        payload = payload_data.get('payload', {})
        meeting_obj = payload.get('object', {})
        raw_meeting_id = meeting_obj.get('id')
        if not raw_meeting_id:
            logger.info(f"[ZOOM WEBHOOK] Event {event} skipped: no meeting ID provided.")
            return Response({"status": "skipped", "reason": "No meeting id"}, status=status.HTTP_200_OK)

        meeting_id = str(raw_meeting_id).strip()

        # 5. Process under transactional row lock (Concurrency Guard Pillar 2)
        with transaction.atomic():
            booking = (
                Booking.objects.select_for_update()
                .filter(zoom_meeting_id=meeting_id)
                .select_related('teacher__user', 'student')
                .first()
            )

            if not booking:
                logger.warning(f"[ZOOM WEBHOOK] Received event {event} for unrecognized meeting_id: {meeting_id}")
                return Response({"status": "ignored", "reason": "Booking not found"}, status=status.HTTP_200_OK)

            participant = meeting_obj.get('participant', {})
            p_email = (participant.get('email') or '').strip().lower()
            p_user_id = str(participant.get('user_id') or participant.get('id') or '').strip()
            join_time_raw = participant.get('join_time')
            leave_time_raw = participant.get('leave_time')

            # Identify participant email mapping
            teacher_email = booking.teacher.user.email.strip().lower()
            student_email = booking.student.email.strip().lower()
            host_id = str(meeting_obj.get('host_id') or '').strip()

            if p_email == teacher_email:
                mapped_email = booking.teacher.user.email
            elif p_email == student_email:
                mapped_email = booking.student.email
            elif p_user_id and host_id and p_user_id == host_id:
                mapped_email = booking.teacher.user.email
            else:
                # Default guest / external client mapping
                mapped_email = booking.student.email

            # Handle participant_joined
            if event == 'meeting.participant_joined':
                try:
                    join_dt = dateutil.parser.isoparse(join_time_raw) if join_time_raw else timezone.now()
                except Exception:
                    join_dt = timezone.now()

                # Look up existing record to handle out-of-order delivery
                audit_qs = AttendanceAudit.objects.filter(
                    booking=booking,
                    participant_email=mapped_email
                )
                if p_user_id:
                    audit_record = audit_qs.filter(Q(zoom_user_id=p_user_id) | Q(zoom_user_id='')).first()
                else:
                    audit_record = audit_qs.first()

                if not audit_record:
                    audit_record = AttendanceAudit.objects.create(
                        booking=booking,
                        participant_email=mapped_email,
                        zoom_user_id=p_user_id,
                        join_time_utc=join_dt,
                        raw_payload=participant
                    )
                else:
                    if not audit_record.join_time_utc:
                        audit_record.join_time_utc = join_dt
                    if p_user_id and not audit_record.zoom_user_id:
                        audit_record.zoom_user_id = p_user_id

                    # If participant_left was ingested before participant_joined
                    if audit_record.leave_time_utc and audit_record.join_time_utc:
                        duration_sec = (audit_record.leave_time_utc - audit_record.join_time_utc).total_seconds()
                        audit_record.total_minutes = max(0, int(duration_sec // 60))
                    audit_record.save()

                # State Machine Progression & Late Webhook Concurrency Guard
                if booking.status == Booking.Status.CONFIRMED:
                    booking.status = Booking.Status.IN_PROGRESS
                    booking.save(update_fields=['status', 'updated_at'])
                    logger.info(f"[ZOOM WEBHOOK] Booking {booking.id} transitioned to IN_PROGRESS.")

                elif booking.status in [Booking.Status.TEACHER_NO_SHOW, Booking.Status.STUDENT_NO_SHOW]:
                    # Late Webhook Hazard: participant joined after adjudication!
                    logger.warning(
                        f"[LATE WEBHOOK HAZARD] Booking {booking.id} is in {booking.status}, "
                        f"but received late participant_joined event for {mapped_email}! Quarantining to DISPUTED."
                    )
                    booking.status = Booking.Status.DISPUTED
                    booking.save(update_fields=['status', 'updated_at'])

                    # Auto-create audit DisputeCase in arbitration tribunal
                    DisputeCase.objects.get_or_create(
                        booking=booking,
                        defaults={
                            "student": booking.student,
                            "teacher": booking.teacher,
                            "student_statement": f"Automated Alert: Late Zoom attendance telemetry received after {booking.status} adjudication.",
                            "teacher_statement": f"Telemetry proof: Participant {mapped_email} joined at {join_dt.isoformat()}.",
                            "status": DisputeCase.Status.OPEN,
                            "admin_notes": "Late webhook arrived post-adjudication. Quarantined for admin manual arbitration."
                        }
                    )

            # Handle participant_left
            elif event == 'meeting.participant_left':
                try:
                    leave_dt = dateutil.parser.isoparse(leave_time_raw) if leave_time_raw else timezone.now()
                except Exception:
                    leave_dt = timezone.now()

                audit_qs = AttendanceAudit.objects.filter(
                    booking=booking,
                    participant_email=mapped_email
                )
                if p_user_id:
                    audit_record = audit_qs.filter(Q(zoom_user_id=p_user_id) | Q(zoom_user_id='')).first()
                else:
                    audit_record = audit_qs.first()

                if not audit_record:
                    # Out of order: participant_left arrived before participant_joined
                    audit_record = AttendanceAudit.objects.create(
                        booking=booking,
                        participant_email=mapped_email,
                        zoom_user_id=p_user_id,
                        leave_time_utc=leave_dt,
                        raw_payload=participant
                    )
                else:
                    audit_record.leave_time_utc = leave_dt
                    if p_user_id and not audit_record.zoom_user_id:
                        audit_record.zoom_user_id = p_user_id

                    if audit_record.join_time_utc and audit_record.leave_time_utc:
                        duration_sec = (audit_record.leave_time_utc - audit_record.join_time_utc).total_seconds()
                        audit_record.total_minutes = max(0, int(duration_sec // 60))
                    audit_record.save()

                logger.info(
                    f"[ZOOM WEBHOOK] Participant {mapped_email} left booking {booking.id}. "
                    f"Total duration: {audit_record.total_minutes}m."
                )

                # Late Webhook Hazard guard on leave event as well
                if booking.status in [Booking.Status.TEACHER_NO_SHOW, Booking.Status.STUDENT_NO_SHOW]:
                    booking.status = Booking.Status.DISPUTED
                    booking.save(update_fields=['status', 'updated_at'])
                    DisputeCase.objects.get_or_create(
                        booking=booking,
                        defaults={
                            "student": booking.student,
                            "teacher": booking.teacher,
                            "student_statement": f"Automated Alert: Late Zoom telemetry received after {booking.status} adjudication.",
                            "teacher_statement": f"Telemetry proof: Participant {mapped_email} logged {audit_record.total_minutes}m.",
                            "status": DisputeCase.Status.OPEN,
                            "admin_notes": "Late webhook arrived post-adjudication. Quarantined for admin manual arbitration."
                        }
                    )

            # Handle meeting.ended
            elif event == 'meeting.ended':
                now_utc = timezone.now()
                open_audits = AttendanceAudit.objects.filter(booking=booking, leave_time_utc__isnull=True)
                for aud in open_audits:
                    aud.leave_time_utc = now_utc
                    if aud.join_time_utc:
                        duration_sec = (aud.leave_time_utc - aud.join_time_utc).total_seconds()
                        aud.total_minutes = max(0, int(duration_sec // 60))
                    aud.save()
                logger.info(f"[ZOOM WEBHOOK] Meeting ended for booking {booking.id}. Finalized {open_audits.count()} open records.")

        return Response({
            "status": "success",
            "event": event,
            "meeting_id": meeting_id
        }, status=status.HTTP_200_OK)


class PresignedUploadURLView(APIView):
    """
    POST /api/v1/integrations/storage/presigned-url/
    POST /api/v1/integrations/r2/presigned-url/
    Generates presigned upload or download URLs for Cloudflare R2 object storage with zero egress fees.
    Direct-to-storage client upload architecture eliminates backend Gunicorn/Celery worker blocking.
    Enforces strict role-based access control (RBAC), Tier 1 vs Tier 2 separation, and path traversal protection.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'upload'

    def post(self, request):
        from apps.common.upload_policy import policy_for_key, clamp_expires
        action = request.data.get('action', 'upload')  # 'upload' or 'download'
        key = str(request.data.get('key') or '').strip()
        content_type = request.data.get('content_type')
        expires_in = clamp_expires(request.data.get('expires_in', 900))

        if not key:
            return Response(
                {"error": "Object 'key' is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Path traversal guard
        if '..' in key or key.startswith('/') or '\\' in key or '//' in key or '%' in key or any(ord(c) < 32 for c in key):
            return Response(
                {"error": "Invalid object key path."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        is_admin = bool(user.is_staff or getattr(user, 'role', '') == 'admin' or user.is_superuser)
        user_id_str = str(user.id)

        # 1. Access Control for UPLOAD action
        if action == 'upload':
            if not is_admin:
                allowed_prefixes = []
                user_role = getattr(user, 'role', '')
                if user_role == 'teacher' or getattr(user, 'teacher_profile', None):
                    allowed_prefixes.extend([
                        f"teachers/avatars/{user_id_str}",
                        f"teachers/audio/{user_id_str}",
                        f"private/vetting/certificates/{user_id_str}",
                        f"private/vetting/{user_id_str}",
                    ])
                if user_role in ['student', 'teacher']:
                    allowed_prefixes.append(f"students/avatars/{user_id_str}")

                if not any(key.startswith(p + '/') for p in allowed_prefixes):
                    return Response(
                        {"error": f"Permission denied to upload to key '{key}'."},
                        status=status.HTTP_403_FORBIDDEN
                    )

        # 2. Access Control for DOWNLOAD action (Tier 2 Private Regulated Compliance Vault)
        elif action == 'download':
            if key.startswith('private/'):
                if not is_admin:
                    allowed_private_prefixes = [
                        f"private/vetting/certificates/{user_id_str}",
                        f"private/vetting/{user_id_str}",
                        f"private/{user_id_str}",
                    ]
                    if not any(key.startswith(p + '/') for p in allowed_private_prefixes):
                        return Response(
                            {"error": f"Permission denied to download private document '{key}'."},
                            status=status.HTTP_403_FORBIDDEN
                        )
        else:
            return Response(
                {"error": f"Invalid action '{action}'. Supported actions: 'upload', 'download'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from apps.common.r2_client import (
            generate_presigned_upload_url,
            generate_presigned_download_url,
            get_public_r2_url
        )

        if action == 'upload':
            policy = policy_for_key(key)
            if policy is None:
                return Response({"error": "No upload policy exists for this key prefix."}, status=status.HTTP_400_BAD_REQUEST)
            allowed_types, max_bytes = policy
            if content_type not in allowed_types:
                return Response({"error": f"content_type must be one of {sorted(allowed_types)}."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                size = int(request.data.get('size'))
            except (ValueError, TypeError):
                return Response({"error": "'size' (bytes) is required."}, status=status.HTTP_400_BAD_REQUEST)
            if size <= 0 or size > max_bytes:
                return Response({"error": f"size must be between 1 and {max_bytes} bytes."}, status=status.HTTP_400_BAD_REQUEST)
            res = generate_presigned_upload_url(object_key=key, content_type=content_type, expires_in=expires_in, content_length=size)
            res['public_cdn_url'] = get_public_r2_url(key)
            return Response(res, status=status.HTTP_200_OK)
        elif action == 'download':
            url = generate_presigned_download_url(object_key=key, expires_in=expires_in)
            return Response({
                "download_url": url,
                "key": key,
                "expires_in": expires_in
            }, status=status.HTTP_200_OK)


R2PresignedUrlView = PresignedUploadURLView

