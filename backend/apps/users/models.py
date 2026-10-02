import uuid
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
