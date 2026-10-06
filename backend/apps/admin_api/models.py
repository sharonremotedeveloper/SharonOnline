import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class DisputeCase(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        RESOLVED = 'resolved', 'Resolved'

    class Resolution(models.TextChoices):
        FULL_REFUND_STUDENT = 'full_refund_student', 'Full Refund to Student'
        RELEASE_TUTOR = 'release_tutor', 'Release Escrow to Tutor'
        SPLIT_50_50 = 'split_50_50', '50/50 Split (Platform Absorbed)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField('bookings.Booking', on_delete=models.CASCADE, related_name='dispute')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_disputes')
    teacher = models.ForeignKey('teachers.TeacherProfile', on_delete=models.CASCADE, related_name='teacher_disputes')
    student_statement = models.TextField(help_text="Student complaint regarding the session")
    teacher_statement = models.TextField(blank=True, help_text="Teacher explanation / defense")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolution = models.CharField(max_length=30, choices=Resolution.choices, null=True, blank=True)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Dispute on Booking {self.booking_id} ({self.status})"


class PayoutBatch(models.Model):
    """
    A tutor payout run (ADR-0003, slices P1a-c). pending -> approved -> exported -> processed; `cancelled` only before export.
    Maker-checker: `created_by` may neither approve nor process it (apps/payments/services/payout_batches.py).
    `executed_by` / `executed_at` are the person and time that marked it processed.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        EXPORTED = 'exported', 'Exported'
        PROCESSED = 'processed', 'Processed'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch_reference = models.CharField(max_length=64, unique=True, db_index=True)
    total_payout_zar = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    recipients_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='payout_batches_created')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='payout_batches_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    exported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='payout_batches_exported')
    exported_at = models.DateTimeField(null=True, blank=True)
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.batch_reference} - {self.total_payout_zar} ZAR ({self.status})"


class PayoutBatchLine(models.Model):
    """
    One tutor's payout in a batch. `is_open` is true while the money is committed to a batch that has not paid or released
    it; the partial unique constraint makes it impossible for a tutor's balance to sit in two open batches at once.
    `skipped` lines are kept (never dropped silently) with the reason the tutor was not paid this run.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        EXPORTED = 'exported', 'Exported'
        PAID = 'paid', 'Paid'
        RETURNED = 'returned', 'Returned by the bank'
        SKIPPED = 'skipped', 'Skipped'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(PayoutBatch, on_delete=models.PROTECT, related_name='lines')
    teacher = models.ForeignKey('teachers.TeacherProfile', on_delete=models.PROTECT, related_name='payout_lines')
    amount_zar = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    is_open = models.BooleanField(default=True)
    skip_reason = models.CharField(max_length=64, blank=True)
    # What the line was built from: the bank account as it was when the batch was made. Compared with the live account at
    # approve and export; any change (or a re-save) blocks the payment until a new batch re-snapshots it.
    account_fingerprint = models.CharField(max_length=64, blank=True)
    account_last_four = models.CharField(max_length=4, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    return_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['teacher'], condition=models.Q(is_open=True), name='payout_one_open_line_per_teacher'),
            models.UniqueConstraint(fields=['batch', 'teacher'], name='payout_one_line_per_teacher_per_batch'),
            models.CheckConstraint(condition=models.Q(amount_zar__gte=0), name='payout_line_amount_not_negative'),
        ]

    def __str__(self):
        return f"{self.batch_id} {self.teacher_id} {self.amount_zar} ZAR ({self.status})"


class PayoutAttempt(models.Model):
    """Append-only record of what happened to a line when staff acted on it (paid, failed re-check, returned by the bank)."""
    class Status(models.TextChoices):
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'
        RETURNED = 'returned', 'Returned'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    line = models.ForeignKey(PayoutBatchLine, on_delete=models.PROTECT, related_name='attempts')
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+')
    status = models.CharField(max_length=20, choices=Status.choices)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('PayoutAttempt rows are append-only.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('PayoutAttempt rows are append-only.')


class PayoutExportAudit(models.Model):
    """One row per download of the bank CSV: who, which batch, how many rows, and the SHA-256 of exactly what was handed out."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(PayoutBatch, on_delete=models.PROTECT, related_name='export_audits')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    row_count = models.PositiveIntegerField()
    content_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
