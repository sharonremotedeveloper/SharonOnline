from django.db import models
from django.conf import settings
import uuid

class TeacherProfile(models.Model):
    class Accent(models.TextChoices):
        SOUTH_AFRICAN = 'ZA', 'South African'
        BRITISH = 'UK', 'British'
        AMERICAN = 'US', 'American'
        OTHER = 'OTHER', 'International'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teacher_profile')
    bio = models.TextField(blank=True)
    headline = models.CharField(max_length=255, blank=True, help_text="e.g. Certified TEFL Tutor · 5+ Yrs Experience")
    accent = models.CharField(max_length=10, choices=Accent.choices, default=Accent.SOUTH_AFRICAN, db_index=True)
    intro_video_url = models.URLField(blank=True, help_text="Cloudflare Stream HLS or preview MP4 URL")
    intro_video_thumbnail = models.URLField(blank=True)
    avatar_image = models.ImageField(upload_to='teachers/avatars/', blank=True, null=True, help_text="Teacher avatar image stored on Cloudflare R2")
    avatar_url = models.URLField(blank=True)
    intro_audio_file = models.FileField(upload_to='teachers/audio/', blank=True, null=True, help_text="15s accent audio audition sample stored on R2")
    intro_audio_url = models.URLField(blank=True, help_text="Cloudflare R2 public audio URL")
    tefl_certificate_file = models.FileField(upload_to='private/vetting/certificates/', blank=True, null=True, help_text="Private TEFL certificate stored securely on R2")
    tefl_certificate_url = models.URLField(blank=True, help_text="Direct or fallback certificate URL")
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)
    rating_count = models.PositiveIntegerField(default=0)
    price_per_25min_usd = models.DecimalField(max_digits=6, decimal_places=2, default=9.00)
    specialties = models.JSONField(default=list, help_text="List of tags: ['FreeTalk', 'Business English', 'Daily News', 'TOEIC']")
    is_verified = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    # Strikes counted inside the rolling STRIKE_WINDOW_DAYS window; kept in step by services/strikes.py (never edit by hand)
    # Strikes inside the rolling STRIKE_WINDOW_DAYS window, kept in step by services/strikes.py (do not edit by hand)
    sla_strikes = models.PositiveSmallIntegerField(default=0)
    eskom_area_id = models.CharField(max_length=64, blank=True, default="jhb-block-3")
    has_inverter_backup = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def resolved_avatar_url(self) -> str:
        if self.avatar_image:
            try:
                return self.avatar_image.url
            except Exception:
                pass
        return self.avatar_url or ""

    @property
    def resolved_intro_audio_url(self) -> str:
        if self.intro_audio_file:
            try:
                return self.intro_audio_file.url
            except Exception:
                pass
        return self.intro_audio_url or ""

    @property
    def resolved_tefl_certificate_url(self) -> str:
        if self.tefl_certificate_file:
            try:
                from apps.common.r2_client import generate_presigned_download_url
                return generate_presigned_download_url(self.tefl_certificate_file.name)
            except Exception:
                try:
                    return self.tefl_certificate_file.url
                except Exception:
                    pass
        return self.tefl_certificate_url or ""

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_accent_display()})"

class TeacherStrike(models.Model):
    """
    One row per strike. Only strikes inside STRIKE_WINDOW_DAYS count, so a tutor who had a bad month is not penalised
    for life; `TeacherProfile.sla_strikes` mirrors that windowed count (services/strikes.py::add_strike).
    """
    class Kind(models.TextChoices):
        NO_SHOW = 'no_show', 'Missed a lesson'
        LATE_CANCEL = 'late_cancel', 'Cancelled less than 24h before the lesson'
        SERIAL_CANCEL = 'serial_cancel', 'Repeated early cancellations'
        MEMO_SLA = 'memo_sla', 'Memo not submitted within 24h'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey('TeacherProfile', on_delete=models.CASCADE, related_name='strikes')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='teacher_strikes')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # A booking can earn a tutor at most one strike of each kind, so retries cannot double-penalise.
            models.UniqueConstraint(fields=['booking', 'kind'], condition=models.Q(booking__isnull=False),
                                    name='uniq_strike_kind_per_booking'),
        ]


class TeacherAvailability(models.Model):
    """
    Weekly recurring availability blocks declared in the teacher's local timezone (SAST / UTC+2).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='availabilities')
    day_of_week = models.PositiveSmallIntegerField(
        help_text="0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday"
    )
    start_time = models.TimeField(help_text="Start time in teacher local clock, e.g. 09:00:00")
    end_time = models.TimeField(help_text="End time in teacher local clock, e.g. 17:00:00")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Teacher Availabilities"
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        day_str = days[self.day_of_week] if 0 <= self.day_of_week <= 6 else str(self.day_of_week)
        return f"{self.teacher.user.username} - {day_str} {self.start_time.strftime('%H:%M')} to {self.end_time.strftime('%H:%M')}"
