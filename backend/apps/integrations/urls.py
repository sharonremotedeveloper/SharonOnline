from django.urls import path
from .views import (EskomStatusView, ZoomWebhookReceiverView, VideoSdkWebhookReceiverView,
                    PresignedUploadURLView, R2PresignedUrlView,
                    GoogleCalendarConnectView, GoogleCalendarCallbackView, GoogleCalendarDisconnectView)

app_name = 'integrations'

urlpatterns = [
    path('zoom/webhook/', ZoomWebhookReceiverView.as_view(), name='zoom-webhook'),
    path('video-sdk/webhooks/', VideoSdkWebhookReceiverView.as_view(), name='video-sdk-webhooks'),
    path('video-sdk/webhook/', VideoSdkWebhookReceiverView.as_view(), name='video-sdk-webhook'),
    path('storage/presigned-url/', PresignedUploadURLView.as_view(), name='storage-presigned-url'),
    path('r2/presigned-url/', R2PresignedUrlView.as_view(), name='r2-presigned-url'),
    path('eskom/status/', EskomStatusView.as_view(), name='eskom-status'),
    path('google-calendar/connect/', GoogleCalendarConnectView.as_view(), name='google-calendar-connect'),
    path('google-calendar/callback/', GoogleCalendarCallbackView.as_view(), name='google-calendar-callback'),
    path('google-calendar/disconnect/', GoogleCalendarDisconnectView.as_view(), name='google-calendar-disconnect'),
]


