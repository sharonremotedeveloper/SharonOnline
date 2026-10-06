from django.urls import path
from .views import (
    CheckoutInitializeView,
    PayFastWebhookView,
    PayPalWebhookView,
    CreditBalanceView,
    PayPalCaptureView,
    CreditPackListView,
    LessonPriceListView,
    CreditPurchaseStatusView,
    PayoutCodeView,
    TutorStatementView,
    PayoutSettingsView,
    ReceiptListView,
    ReceiptPdfView,
    TutorWalletView,
)

urlpatterns = [
    path('checkout/init/', CheckoutInitializeView.as_view(), name='payment-checkout-init'),
    path('webhooks/payfast/', PayFastWebhookView.as_view(), name='payment-webhook-payfast'),
    path('paypal/capture/', PayPalCaptureView.as_view(), name='payment-paypal-capture'),
    path('webhooks/paypal/', PayPalWebhookView.as_view(), name='payment-webhook-paypal'),
    path('credits/', CreditBalanceView.as_view(), name='payment-credits-balance'),
    path('credit-packs/', CreditPackListView.as_view(), name='payment-credit-packs'),
    path('lesson-prices/', LessonPriceListView.as_view(), name='payment-lesson-prices'),
    path('credit-purchases/<uuid:purchase_id>/', CreditPurchaseStatusView.as_view(), name='payment-credit-purchase-status'),
    path('wallet/tutor/', TutorWalletView.as_view(), name='payment-tutor-wallet'),
    path('payout-settings/', PayoutSettingsView.as_view(), name='payment-payout-settings'),
    path('wallet/tutor/statement/', TutorStatementView.as_view(), name='payment-tutor-statement'),
    path('payout-settings/code/', PayoutCodeView.as_view(), name='payment-payout-code'),
    path('receipts/', ReceiptListView.as_view(), name='payment-receipts'),
    path('receipts/<uuid:receipt_id>/pdf/', ReceiptPdfView.as_view(), name='payment-receipt-pdf'),
]
