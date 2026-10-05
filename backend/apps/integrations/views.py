import json
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
import logging
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.bookings.models import Booking
from apps.integrations.models import EskomAreaStatus
from apps.teachers.models import TeacherAsset, TeacherProfile
from apps.teachers.assets import audit_private_access
from apps.integrations.serializers import (
    EskomStatusSerializer,
    GoogleCalendarCallbackResponseSerializer,
    GoogleCalendarCallbackSerializer,
)
from apps.users.permissions import IsTeacher
from .services import attendance
from .zoom import zoom_client
from .google_calendar import oauth_authorization_url, exchange_oauth_code, disconnect_calendar, oauth_state_user, consume_oauth_state

logger = logging.getLogger(__name__)


@extend_schema(responses={200: EskomStatusSerializer})
class EskomStatusView(APIView):
    permission_classes = (permissions.IsAuthenticated, IsTeacher)

    def get(self, request):
        profile = getattr(request.user, 'teacher_profile', None)
        if profile is None or not profile.eskom_area_id:
            return Response({'code': 'eskom_area_not_configured'}, status=status.HTTP_409_CONFLICT)
        area = EskomAreaStatus.objects.filter(area_id=profile.eskom_area_id).first()
        if area is None:
            return Response({
                'code': 'eskom_status_unavailable', 'area_id': profile.eskom_area_id,
                'provider_status': 'unavailable',
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        now = timezone.now()
        outages = area.outages if isinstance(area.outages, list) else []
        future = []
        for item in outages:
            if not isinstance(item, dict):
                continue
            start = parse_datetime(str(item.get('start') or ''))
            end = parse_datetime(str(item.get('end') or ''))
            if start and end and end >= now:
                future.append((start, item))
        next_outage = min(future, key=lambda pair: pair[0])[1] if future else None
        provider_status = area.provider_status
        stale = area.fresh_until < now or provider_status != EskomAreaStatus.ProviderStatus.OK
        if stale and provider_status == EskomAreaStatus.ProviderStatus.OK:
            provider_status = EskomAreaStatus.ProviderStatus.STALE
        payload = {
            'area_id': area.area_id, 'area_name': area.area_name, 'stage': area.stage,
            'outages': outages,
            'next_outage_start': next_outage['start'] if next_outage else None,
            'next_outage_end': next_outage['end'] if next_outage else None,
            'has_inverter_backup': profile.has_inverter_backup,
            'has_lte_failover': profile.has_lte_failover,
            'stale': stale, 'provider_status': provider_status,
            'retrieved_at': area.provider_retrieved_at,
        }
        return Response(EskomStatusSerializer(payload).data)


@extend_schema(responses=OpenApiTypes.OBJECT)
class GoogleCalendarConnectView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request):
        try:
            return Response({'authorization_url': oauth_authorization_url(request.user)})
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@extend_schema(parameters=[GoogleCalendarCallbackSerializer], responses=GoogleCalendarCallbackResponseSerializer)
class GoogleCalendarCallbackView(APIView):
    # Google redirects may not preserve the API session. The single-use state
    # nonce is the authentication binding for this callback.
    permission_classes = [AllowAny]

    def get(self, request):
        serializer = GoogleCalendarCallbackSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        state = serializer.validated_data['state']
        if serializer.validated_data.get('error'):
            try:
                owner = oauth_state_user(state)
                consume_oauth_state(owner, state)
            except ValueError:
                logger.info('Ignored invalid or already-consumed declined Google OAuth state.')
            return Response({'error': 'Google Calendar authorization was declined.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            owner = oauth_state_user(state)
            if not getattr(owner, 'teacher_profile', None):
                raise ValueError('Google Calendar is available to teachers only.')
            exchange_oauth_code(owner, serializer.validated_data.get('code', ''), state)
        except (ValueError, RuntimeError) as exc:
            logger.info('Google Calendar callback failed: %s', type(exc).__name__)
            return Response({'error': 'Google Calendar connection could not be completed.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'connected': True}, status=status.HTTP_200_OK)


@extend_schema(exclude=True)
class GoogleCalendarDisconnectView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def post(self, request):
        disconnect_calendar(request.user)
        return Response({'connected': False}, status=status.HTTP_200_OK)


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
                        f"incoming/{user_id_str}",
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
            if key.startswith('incoming/') or key.startswith('private/'):
                if not is_admin:
                    allowed_private_prefixes = [
                        f"incoming/{user_id_str}",
                        f"private/vetting/certificates/{user_id_str}",
                        f"private/vetting/{user_id_str}",
                        f"private/{user_id_str}",
                    ]
                    if not any(key.startswith(p + '/') for p in allowed_private_prefixes):
                        return Response(
                            {"error": f"Permission denied to download private document '{key}'."},
                            status=status.HTTP_403_FORBIDDEN
                        )
                if key.startswith('private/'):
                    asset = TeacherAsset.objects.filter(object_key=key, replaced_at__isnull=True).select_related('teacher__user').first()
                    owner_id = key.split('/')[3] if key.startswith('private/vetting/') and len(key.split('/')) > 3 else ''
                    teacher = asset.teacher if asset else TeacherProfile.objects.filter(user_id=owner_id).first()
                    legacy_owner = teacher is None and not is_admin and owner_id == str(user.id)
                    if legacy_owner:
                        # Legacy presign callers may request a key before the commit row exists.
                        # A real committed private document always has an auditable TeacherAsset row.
                        teacher = getattr(user, 'teacher_profile', None)
                    if not legacy_owner and not is_admin and (teacher is None or teacher.user_id != user.id):
                        return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
                    if teacher is not None:
                        audit_private_access(user, teacher, key)
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
            private = key.startswith('incoming/') or key.startswith('private/')
            local_mode = settings.DEBUG or getattr(settings, 'ZOOM_SIMULATE_WITHOUT_CREDENTIALS', False)
            if private and not local_mode and not getattr(settings, 'CLOUDFLARE_R2_PRIVATE_BUCKET_NAME', ''):
                return Response({'error': 'Private asset storage is not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            if private and not local_mode:
                from apps.common.r2_client import get_r2_client
                if get_r2_client() is None:
                    return Response({'error': 'Private asset storage is unavailable.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            try:
                res = generate_presigned_upload_url(object_key=key, content_type=content_type, expires_in=expires_in,
                                                    content_length=size, private=private)
            except RuntimeError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            if not private:
                res['public_cdn_url'] = get_public_r2_url(key)
            return Response(res, status=status.HTTP_200_OK)
        elif action == 'download':
            private = key.startswith('incoming/') or key.startswith('private/')
            try:
                url = generate_presigned_download_url(object_key=key, expires_in=expires_in, private=private)
            except RuntimeError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response({
                "download_url": url,
                "key": key,
                "expires_in": expires_in
            }, status=status.HTTP_200_OK)


R2PresignedUrlView = PresignedUploadURLView

