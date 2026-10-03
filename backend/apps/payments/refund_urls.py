from django.urls import path

from .refund_views import ConvertRefundToWalletView, RefundListView

urlpatterns = [
    path('', RefundListView.as_view(), name='refund-list'),
    path('<uuid:refund_id>/convert-to-wallet/', ConvertRefundToWalletView.as_view(), name='refund-convert'),
]
