from django.urls import path
from .views import ZoomWebhookReceiverView

app_name = 'integrations'

urlpatterns = [
    path('zoom/webhook/', ZoomWebhookReceiverView.as_view(), name='zoom-webhook'),
]
