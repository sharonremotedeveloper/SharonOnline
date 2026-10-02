from django.urls import path
from .views import (
    CheckoutInitializeView,
    PayFastWebhookView,
    PayPalWebhookView,
    CreditBalanceView,
    CreditPackListView,
    CreditPurchaseStatusView,
)

urlpatterns = [
    path('checkout/init/', CheckoutInitializeView.as_view(), name='payment-checkout-init'),
    path('webhooks/payfast/', PayFastWebhookView.as_view(), name='payment-webhook-payfast'),
    path('webhooks/paypal/', PayPalWebhookView.as_view(), name='payment-webhook-paypal'),
    path('credits/', CreditBalanceView.as_view(), name='payment-credits-balance'),
    path('credit-packs/', CreditPackListView.as_view(), name='payment-credit-packs'),
    path('credit-purchases/<uuid:purchase_id>/', CreditPurchaseStatusView.as_view(), name='payment-credit-purchase-status'),
]
