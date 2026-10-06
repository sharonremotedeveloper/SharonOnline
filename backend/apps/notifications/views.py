import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.notifications import registry
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.serializers import (
    NotificationPreferenceSerializer,
    NotificationSerializer,
    ReadAllResponseSerializer,
    ResendWebhookResponseSerializer,
    UnreadCountSerializer,
)
from apps.notifications.svix import WebhookVerificationError, verify_svix_signature

logger = logging.getLogger(__name__)


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationBaseView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (UserRateThrottle,)


@extend_schema(responses=NotificationSerializer(many=True))
class NotificationListView(generics.ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (UserRateThrottle,)
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user, in_app=True).order_by('-created_at', '-id')

    def get_serializer_context(self):
        return {'request': self.request}


@extend_schema(responses=UnreadCountSerializer)
class NotificationUnreadCountView(NotificationBaseView):
    def get(self, request):
        count = Notification.objects.filter(user=request.user, in_app=True, read_at__isnull=True).count()
        return Response(UnreadCountSerializer({'count': count}).data)


@extend_schema(request=None, responses=NotificationSerializer)
class NotificationReadView(NotificationBaseView):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user, in_app=True)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=('read_at',))
        return Response(NotificationSerializer(notification, context={'request': request}).data)


@extend_schema(request=None, responses=ReadAllResponseSerializer)
class NotificationReadAllView(NotificationBaseView):
    def post(self, request):
        updated = Notification.objects.filter(user=request.user, in_app=True, read_at__isnull=True).update(
            read_at=timezone.now())
        return Response(ReadAllResponseSerializer({'updated': updated}).data)


@extend_schema_view(
    get=extend_schema(responses=NotificationPreferenceSerializer),
    patch=extend_schema(request=NotificationPreferenceSerializer, responses=NotificationPreferenceSerializer),
)
class NotificationPreferenceView(NotificationBaseView):
    def get(self, request):
        preference, _created = NotificationPreference.objects.get_or_create(user=request.user)
        return Response(NotificationPreferenceSerializer(preference).data)

    def patch(self, request):
        preference, _created = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(NotificationPreferenceSerializer(serializer.instance).data)


@extend_schema(responses={200: ResendWebhookResponseSerializer})
class ResendWebhookView(APIView):
    """
    Public Svix webhook receiver for Resend transactional email events (Slice N3).
    Handles bounce and complaint events by recording the bounce on the Notification row
    and suppressing subsequent email deliveries in NotificationPreference.
    """
    permission_classes = (permissions.AllowAny,)
    throttle_classes = ()

    def post(self, request):
        secret = getattr(settings, 'RESEND_WEBHOOK_SECRET', '')
        if secret:
            try:
                verify_svix_signature(request.body, request.headers, secret)
            except WebhookVerificationError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return Response({'error': 'Invalid JSON body.'}, status=status.HTTP_400_BAD_REQUEST)

        event_type = payload.get('type')
        data = payload.get('data') or {}
        email_id = data.get('email_id')
        to_list = data.get('to') or []

        if event_type in ('email.bounced', 'email.complained'):
            notif = None
            if email_id:
                notif = Notification.objects.filter(provider_message_id=email_id).first()
            user = None
            if notif:
                notif.email_state = Notification.EmailState.BOUNCED
                notif.email_last_error = 'bounced' if event_type == 'email.bounced' else 'complained'
                notif.save(update_fields=['email_state', 'email_last_error'])
                user = notif.user
            elif to_list:
                user = get_user_model().objects.filter(email__in=to_list).first()

            if user:
                pref, _ = NotificationPreference.objects.get_or_create(user=user)
                pref.email_by_kind = {k.name: False for k in registry.all_kinds() if not k.mandatory}
                pref.save(update_fields=['email_by_kind', 'updated_at'])

            logger.warning('resend_webhook: bounce/complaint handled for email_id=%s', email_id or 'unknown')
            return Response({'received': True, 'action': 'suppressed'})

        return Response({'received': True, 'action': 'ignored'})

