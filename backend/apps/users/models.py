import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        TEACHER = 'teacher', 'Teacher'
        ADMIN = 'admin', 'Administrator'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT, db_index=True)
    country = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2 code (e.g. ZA, JP, KR, DE)")
    timezone = models.CharField(max_length=64, default="UTC", help_text="IANA Timezone, e.g. Asia/Tokyo")
    phone_number = models.CharField(max_length=32, blank=True)
    email_verified = models.BooleanField(default=False, help_text="True once the user proved control of `email` (verification or password-reset link).")
    google_calendar_token = models.JSONField(null=True, blank=True, help_text="OAuth tokens for teacher calendar sync")
    booking_blocked_reason = models.CharField(
        max_length=255, blank=True,
        help_text="Non-empty = the student cannot book (e.g. a lesson was delivered but its payment failed). Staff clear it.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class StudentProfile(models.Model):
    """Student-owned learning preferences; blank means the student has not supplied the value."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_profile',
        primary_key=True,
    )
    target_level = models.CharField(max_length=64, blank=True)
    learning_goals = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Student profile: {self.user.username}"


class SupportInquiry(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In progress'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    class Category(models.TextChoices):
        GENERAL = 'general', 'General'
        PAYMENT_FAILURE = 'payment_failure', 'Payment failure'

    class DeliveryState(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RETRYABLE = 'retryable', 'Retryable'
        SENT = 'sent', 'Sent'

    class SenderType(models.TextChoices):
        STUDENT = 'student', 'Student'
        TEACHER = 'teacher', 'Teacher'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    sender_name = models.CharField(max_length=150)
    sender_email = models.EmailField()
    sender_type = models.CharField(max_length=20, choices=SenderType.choices, default=SenderType.OTHER)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    # System-created tickets (e.g. a pending payment that failed) point at the booking/payment they concern.
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL, db_index=True)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='support_inquiries')
    related_booking_id = models.UUIDField(null=True, blank=True)
    related_transaction_ref = models.CharField(max_length=40, blank=True)
    delivery_state = models.CharField(
        max_length=20, choices=DeliveryState.choices, default=DeliveryState.PENDING, db_index=True,
    )
    delivery_attempts = models.PositiveIntegerField(default=0)
    last_delivery_error = models.CharField(max_length=500, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.subject} ({self.sender_email})"
