"""Private Daily tokens for an admin-created, payment-free video trial."""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.schema import ErrorCodeSerializer
from apps.integrations.services.daily import DailyApiError, DailyClient, get_daily_domain, is_daily_configured

from .models import VideoTrial
from .video_views import VideoTokenSerializer


@extend_schema(
    responses={200: VideoTokenSerializer, 404: ErrorCodeSerializer, 409: ErrorCodeSerializer,
               502: ErrorCodeSerializer, 503: ErrorCodeSerializer},
    description='Get an ephemeral Daily token for a named, admin-created video-only trial. No booking or payment is created.',
)
class VideoTrialTokenView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'daily_video_token'

    def get(self, request, trial_id):
        # An unknown, disabled or non-party trial is indistinguishable to the caller.
        trial = (VideoTrial.objects.select_related('teacher', 'student')
                 .filter(pk=trial_id, enabled=True)
                 .filter(models.Q(teacher=request.user) | models.Q(student=request.user))
                 .first())
        if trial is None:
            return Response({'error': 'Video trial not found.', 'code': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        if (trial.closes_at <= trial.opens_at
                or trial.closes_at > trial.opens_at + timedelta(hours=2)
                or now < trial.opens_at or now >= trial.closes_at):
            return Response({'error': 'Video trial is not open.', 'code': 'outside_trial_window'},
                            status=status.HTTP_409_CONFLICT)
        if not is_daily_configured() or (settings.DEBUG is False and not settings.DAILY_API_KEY):
            return Response({'error': 'Video service is not configured.', 'code': 'video_unconfigured'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        room_name = f'trial-{trial.id}'
        nbf, exp = int(trial.opens_at.timestamp()), int(trial.closes_at.timestamp())
        is_owner = request.user.id == trial.teacher_id
        user_name = request.user.get_full_name().strip() or request.user.username
        try:
            daily = DailyClient()
            daily.ensure_room(room_name, nbf, exp)
            token = daily.create_meeting_token(
                room_name=room_name, user_id=str(request.user.id), user_name=user_name,
                is_owner=is_owner, nbf=nbf, exp=exp, enable_recording=False,
            )
        except DailyApiError:
            return Response({'error': 'Video provider is unavailable.', 'code': 'daily_unavailable'},
                            status=status.HTTP_502_BAD_GATEWAY)

        data = VideoTokenSerializer({
            'token': token, 'room_url': f'https://{get_daily_domain()}/{room_name}',
            'session_name': room_name, 'user_name': user_name, 'is_owner': is_owner, 'expires_at': exp,
        }).data
        response = Response(data)
        response['Cache-Control'] = 'no-store'
        return response
