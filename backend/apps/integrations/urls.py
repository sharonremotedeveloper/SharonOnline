from django.urls import path
from .views import EskomStatusView, ZoomWebhookReceiverView, PresignedUploadURLView, R2PresignedUrlView

app_name = 'integrations'

urlpatterns = [
    path('zoom/webhook/', ZoomWebhookReceiverView.as_view(), name='zoom-webhook'),
    path('storage/presigned-url/', PresignedUploadURLView.as_view(), name='storage-presigned-url'),
    path('r2/presigned-url/', R2PresignedUrlView.as_view(), name='r2-presigned-url'),
    path('eskom/status/', EskomStatusView.as_view(), name='eskom-status'),
]


