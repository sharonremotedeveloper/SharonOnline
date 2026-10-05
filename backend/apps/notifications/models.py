"""Notifications (slice N1a; plan §3.2, docs/NOTIFICATIONS.md §2, docs/adr/ADR-0002-notification-delivery.md)."""
import uuid

from django.conf import settings
from django.db import models

from apps.common import clock


class Notification(models.Model):
    """One message to one user: an in-app item and/or an e-mail with its own delivery state.

    The e-mail is rendered ONCE at creation (`rendered_*`) and re-sent byte-identical under `idempotency_key` (Resend's
    `Idempotency-Key`), so a retry can never become a second, different e-mail. `payload` holds ids only.
    """

    class EmailState(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENDING = 'sending', 'Sending (claimed; the lease is NOTIFICATION_LEASE_SECONDS)'
        SENT = 'sent', 'Sent'
        RETRYABLE = 'retryable', 'Retryable'
        FAILED = 'failed', 'Failed (needs a person)'
        SKIPPED = 'skipped', 'Skipped (no e-mail for this kind / preference)'
        BOUNCED = 'bounced', 'Bounced'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True, help_text='Ids only, never free text (plan §3.2).')
    booking = models.ForeignKey('bookings.Booking', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='notifications')
    idempotency_key = models.CharField(max_length=200, unique=True)
    in_app = models.BooleanField(default=True, help_text='Shown in the in-app list (False = e-mail-only row).')
    created_at = models.DateTimeField(default=clock.now, editable=False)
    read_at = models.DateTimeField(null=True, blank=True)

    email_state = models.CharField(max_length=12, choices=EmailState.choices, default=EmailState.PENDING,
                                   db_index=True)
    email_attempts = models.PositiveSmallIntegerField(default=0)
    email_claimed_at = models.DateTimeField(null=True, blank=True)
    email_first_attempt_at = models.DateTimeField(null=True, blank=True)
    email_next_attempt_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True)
    rendered_subject = models.CharField(max_length=255, blank=True)
    rendered_html = models.TextField(blank=True)
    rendered_text = models.TextField(blank=True)
    email_last_error = models.CharField(max_length=64, blank=True, help_text='Short code only, never a provider body.')

    class Meta:
        indexes = [
            models.Index(fields=['user', 'read_at', '-created_at'], name='notif_user_read_created'),
            models.Index(fields=['email_state', 'email_next_attempt_at'], name='notif_email_due'),
        ]

    def __str__(self):
        return f'{self.kind} -> {self.user_id} ({self.email_state})'


class NotificationPreference(models.Model):
    """Per-kind opt-outs ({kind: bool}); a missing kind means 'on'. Mandatory kinds ignore the e-mail opt-out."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True,
                                related_name='notification_preference')
    email_by_kind = models.JSONField(default=dict, blank=True)
    in_app_by_kind = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Notification preferences of {self.user_id}'
