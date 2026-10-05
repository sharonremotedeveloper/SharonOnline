from django.urls import path
from .views import (EskomStatusView, ZoomWebhookReceiverView, PresignedUploadURLView, R2PresignedUrlView,
                    GoogleCalendarConnectView, GoogleCalendarCallbackView, GoogleCalendarDisconnectView)

app_name = 'integrations'

urlpatterns = [
    path('zoom/webhook/', ZoomWebhookReceiverView.as_view(), name='zoom-webhook'),
    path('storage/presigned-url/', PresignedUploadURLView.as_view(), name='storage-presigned-url'),
    path('r2/presigned-url/', R2PresignedUrlView.as_view(), name='r2-presigned-url'),
    path('eskom/status/', EskomStatusView.as_view(), name='eskom-status'),
    path('google-calendar/connect/', GoogleCalendarConnectView.as_view(), name='google-calendar-connect'),
    path('google-calendar/callback/', GoogleCalendarCallbackView.as_view(), name='google-calendar-callback'),
    path('google-calendar/disconnect/', GoogleCalendarDisconnectView.as_view(), name='google-calendar-disconnect'),
]


