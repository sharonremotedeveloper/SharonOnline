"""GET /api/v1/bookings/<id>/video-token/ (Sprint Slice V2): Zoom Video SDK token endpoint."""
from django.core.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.schema import ErrorCodeSerializer
from apps.integrations.services.video_sdk import (
    VideoSdkConfigError,
    VideoSdkTimingError,
    generate_video_sdk_token,
    resolve_role_for_booking,
)

from .models import Booking


class VideoTokenSerializer(serializers.Serializer):
    token = serializers.CharField(help_text='JWT session token for Zoom Video SDK')
    session_name = serializers.CharField(help_text='Session topic / room name')
    role_type = serializers.IntegerField(help_text='1 for Host (tutor), 0 for Participant (student)')
    user_identity = serializers.CharField(help_text='Unique user ID')
    user_name = serializers.CharField(help_text='Display name of participant')
    expires_at = serializers.IntegerField(help_text='Epoch expiration timestamp')


CANCELLED_STATUSES = {
    Booking.Status.CANCELLED,
    Booking.Status.CANCELLED_BY_STUDENT,
    Booking.Status.CANCELLED_BY_TEACHER,
    Booking.Status.STUDENT_LATE_CANCELLED,
}


CLASSROOM_STATUSES = {Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS}


@extend_schema(
    responses={
        200: VideoTokenSerializer,
        403: ErrorCodeSerializer,
        404: ErrorCodeSerializer,
        409: ErrorCodeSerializer,
        503: ErrorCodeSerializer,
    },
    description="Retrieve an ephemeral Zoom Video SDK JWT token to enter the live in-browser classroom."
)
class BookingVideoTokenView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'zoom_video_token'

    def get(self, request, booking_id):
        try:
            booking = (
                Booking.objects
                .select_related('teacher__user', 'student')
                .get(id=booking_id)
            )
        except (Booking.DoesNotExist, ValueError):
            return Response(
                {'error': 'Booking not found.', 'code': 'not_found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Authorize first: a non-party must not learn anything about the booking (status oracle).
        try:
            resolve_role_for_booking(booking, request.user)
        except PermissionDenied as exc:
            return Response({'error': str(exc), 'code': 'forbidden'}, status=status.HTTP_403_FORBIDDEN)

        if booking.status in CANCELLED_STATUSES:
            return Response(
                {'error': 'This lesson was cancelled and its classroom is closed.', 'code': 'booking_cancelled'},
                status=status.HTTP_409_CONFLICT,
            )
        # Only a paid, live lesson opens a classroom (pending_payment would be a free lesson).
        if booking.status not in CLASSROOM_STATUSES:
            return Response(
                {'error': 'This lesson is not open for a classroom session.', 'code': 'classroom_unavailable'},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            token_data = generate_video_sdk_token(
                booking=booking,
                user=request.user,
                enforce_window=True,
            )
        except VideoSdkTimingError as exc:
            return Response(
                {'error': str(exc), 'code': 'outside_lesson_window'},
                status=status.HTTP_409_CONFLICT,
            )
        except VideoSdkConfigError:
            return Response(
                {'error': 'Video classroom service is not configured.', 'code': 'video_unconfigured'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except PermissionDenied as exc:
            return Response(
                {'error': str(exc), 'code': 'forbidden'},
                status=status.HTTP_403_FORBIDDEN,
            )

        response = Response(VideoTokenSerializer(token_data).data)
        response['Cache-Control'] = 'no-store'
        return response
