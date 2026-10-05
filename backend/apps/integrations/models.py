import uuid

from django.conf import settings
from django.db import models


class EskomAreaStatus(models.Model):
    class ProviderStatus(models.TextChoices):
        OK = 'ok', 'OK'
        STALE = 'stale', 'Stale'
        QUOTA = 'quota', 'Quota exhausted'
        ERROR = 'error', 'Provider error'

    area_id = models.CharField(max_length=128, unique=True)
    area_name = models.CharField(max_length=255)
    stage = models.PositiveSmallIntegerField()
    outages = models.JSONField(default=list)
    provider_status = models.CharField(max_length=16, choices=ProviderStatus.choices, default=ProviderStatus.OK)
    provider_retrieved_at = models.DateTimeField()
    fresh_until = models.DateTimeField()
    last_error_code = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class EskomNotificationAttempt(models.Model):
    class State(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        RETRYABLE = 'retryable', 'Retryable'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=255, unique=True)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.PROTECT, related_name='eskom_notifications')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    area_status = models.ForeignKey(EskomAreaStatus, on_delete=models.PROTECT)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CalendarCredential(models.Model):
    """Encrypted Google Calendar refresh credential owned by one tutor."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='calendar_credential')
    refresh_token_enc = models.TextField()
    scopes = models.JSONField(default=list, blank=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    block_busy = models.BooleanField(default=True)
    last_error = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=['revoked_at', 'user'], name='integration_revoked_3fd39f_idx')]


class CalendarOAuthState(models.Model):
    """Database-backed, atomically consumable Google OAuth callback nonce."""

    state_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'expires_at'], name='gcal_state_user_exp_idx')]

