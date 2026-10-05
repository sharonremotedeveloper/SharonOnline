from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.serializers import (
    NotificationPreferenceSerializer,
    NotificationSerializer,
    ReadAllResponseSerializer,
    UnreadCountSerializer,
)


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
