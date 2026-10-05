"""GET /api/v1/bookings/<id>/host-link/ (Slice Z1): a fresh Zoom host start link for the lesson's tutor (or staff)."""
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.schema import ErrorCodeSerializer

from .services.host_link import HostLinkError, fresh_host_link


class HostLinkSerializer(serializers.Serializer):
    meeting_id = serializers.CharField()
    start_url = serializers.URLField(help_text='Fresh Zoom host start link (expiring ZAK). Open it at once; never store it.')


@extend_schema(responses={200: HostLinkSerializer, 403: ErrorCodeSerializer, 404: ErrorCodeSerializer,
                          409: ErrorCodeSerializer, 502: ErrorCodeSerializer})
class BookingHostLinkView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'zoom_host_link'

    def get(self, request, booking_id):
        try:
            data = fresh_host_link(booking_id, request.user)
        except HostLinkError as exc:
            return Response({'error': exc.message, 'code': exc.code}, status=exc.status_code)
        response = Response(HostLinkSerializer(data).data)
        response['Cache-Control'] = 'no-store'
        return response
