from django.urls import path
from .views import (EskomStatusView,
                    DailyWebhookReceiverView,
                    PresignedUploadURLView, R2PresignedUrlView,
                    GoogleCalendarConnectView, GoogleCalendarCallbackView, GoogleCalendarDisconnectView)

app_name = 'integrations'

urlpatterns = [
    path('daily/webhooks/', DailyWebhookReceiverView.as_view(), name='daily-webhooks'),
    path('storage/presigned-url/', PresignedUploadURLView.as_view(), name='storage-presigned-url'),
    path('r2/presigned-url/', R2PresignedUrlView.as_view(), name='r2-presigned-url'),
    path('eskom/status/', EskomStatusView.as_view(), name='eskom-status'),
    path('google-calendar/connect/', GoogleCalendarConnectView.as_view(), name='google-calendar-connect'),
    path('google-calendar/callback/', GoogleCalendarCallbackView.as_view(), name='google-calendar-callback'),
    path('google-calendar/disconnect/', GoogleCalendarDisconnectView.as_view(), name='google-calendar-disconnect'),
]


