from django.db import models
from django.conf import settings
import uuid

class PaymentTransaction(models.Model):
    class Gateway(models.TextChoices):
        PAYFAST = 'payfast', 'PayFast (ZAR)'
        PAYPAL = 'paypal', 'PayPal (USD/EUR/JPY)'

    class Status(models.TextChoices):
        INITIALIZED = 'initialized', 'Initialized'
        SUCCESS = 'success', 'Successful'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='transactions')
    gateway = models.CharField(max_length=20, choices=Gateway.choices)
    gateway_reference = models.CharField(max_length=255, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIALIZED, db_index=True)
    escrow_cleared = models.BooleanField(default=False, db_index=True)
    raw_webhook_payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.gateway.upper()} {self.amount} {self.currency} - {self.status} ({self.gateway_reference})"


class CreditBundle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='credit_bundles')
    pack_name = models.CharField(max_length=64, default="5-Lesson Pack")
    total_credits = models.PositiveIntegerField(default=5)
    remaining_credits = models.PositiveIntegerField(default=5)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.remaining_credits}/{self.total_credits} credits"
