import json
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
import logging
from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.bookings.models import Booking
from .services import attendance
from .zoom import zoom_client

logger = logging.getLogger(__name__)


@extend_schema(exclude=True)  # machine-to-machine webhook, not part of the client API
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
        event_id = str(payload_data.get('event_id') or payload_data.get('id') or '')[:128]

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

        # 4. Extract the meeting object. Zoom's shape is not guaranteed, so anything odd is acknowledged and ignored.
        payload = payload_data.get('payload')
        meeting_obj = payload.get('object') if isinstance(payload, dict) else None
        if not isinstance(meeting_obj, dict) or not meeting_obj.get('id'):
            logger.info(f"[ZOOM WEBHOOK] Event {event} skipped: no usable meeting object.")
            return Response({"status": "skipped", "reason": "No meeting id"}, status=status.HTTP_200_OK)

        meeting_id = str(meeting_obj['id']).strip()
        participant = meeting_obj.get('participant')

        # 5. Process under transactional row lock (Concurrency Guard Pillar 2). Who the participant is and what the
        #    event means is decided in services/attendance.py (docs/ZOOM_ATTENDANCE.md).
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

            now = timezone.now()
            if event in ('meeting.participant_joined', 'meeting.participant_left'):
                if not isinstance(participant, dict) or not participant:
                    return Response({"status": "skipped", "reason": "No participant"}, status=status.HTTP_200_OK)
                handler = attendance.on_participant_joined if event == 'meeting.participant_joined' else attendance.on_participant_left
                handler(booking, meeting_obj, participant, now, event_id=event_id)
            elif event == 'meeting.started':
                attendance.on_meeting_started(booking, meeting_obj, now, event_id=event_id)
            elif event == 'meeting.ended':
                attendance.on_meeting_ended(booking, meeting_obj, now, event_id=event_id)

        return Response({
            "status": "success",
            "event": event,
            "meeting_id": meeting_id
        }, status=status.HTTP_200_OK)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
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

