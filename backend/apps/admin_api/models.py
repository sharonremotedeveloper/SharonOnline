import uuid
from django.db import models
from django.conf import settings

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
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        EXPORTED = 'exported', 'Exported'
        PROCESSED = 'processed', 'Processed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch_reference = models.CharField(max_length=64, unique=True, db_index=True)
    total_payout_zar = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    recipients_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.batch_reference} - {self.total_payout_zar} ZAR ({self.status})"
