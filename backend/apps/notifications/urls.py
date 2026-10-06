from django.urls import path

from apps.notifications.views import (
    NotificationListView,
    NotificationPreferenceView,
    NotificationReadAllView,
    NotificationReadView,
    NotificationUnreadCountView,
    ResendWebhookView,
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('read-all/', NotificationReadAllView.as_view(), name='notification-read-all'),
    path('<uuid:pk>/read/', NotificationReadView.as_view(), name='notification-read'),
    path('preferences/', NotificationPreferenceView.as_view(), name='notification-preferences'),
    path('webhooks/resend/', ResendWebhookView.as_view(), name='notification-resend-webhook'),
]
