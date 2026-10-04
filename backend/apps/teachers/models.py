from django.db import models
from django.db.models import Case, Q, Value, When
from django.conf import settings
import uuid

# Plan §3.1, the only truth table. is_verified: approved|suspended. is_active: everything but rejected|suspended.
STATUS_VALUES = ('applied', 'submitted', 'in_review', 'approved', 'changes_requested', 'rejected', 'suspended')
VERIFIED_STATUSES = ('approved', 'suspended')
ACTIVE_STATUSES = ('applied', 'submitted', 'in_review', 'changes_requested', 'approved')
GENERATED_FLAGS = frozenset({'is_verified', 'is_active'})


def _refuse_generated(names, where):
    hit = GENERATED_FLAGS.intersection(names)
    if hit:
        raise ValueError(f"{sorted(hit)} are generated from TeacherProfile.status and cannot be written ({where}); "
                         "use apps.teachers.vetting.transition_teacher.")


class TeacherProfileQuerySet(models.QuerySet):
    """Django silently drops writes to GeneratedFields here; refuse them loudly instead."""

    def update(self, **kwargs):
        _refuse_generated(kwargs, 'QuerySet.update')
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        _refuse_generated(fields, 'QuerySet.bulk_update')
        return super().bulk_update(objs, fields, *args, **kwargs)


class TeacherProfile(models.Model):
    class Accent(models.TextChoices):
        SOUTH_AFRICAN = 'ZA', 'South African'
        BRITISH = 'UK', 'British'
        AMERICAN = 'US', 'American'
        OTHER = 'OTHER', 'International'

    class Status(models.TextChoices):
        """Tutor lifecycle (plan §3.1, docs/TUTOR_STATUS_MACHINE.md). Changed only by teachers/vetting.py."""
        APPLIED = 'applied', 'Applied'
        SUBMITTED = 'submitted', 'Submitted for review'
        IN_REVIEW = 'in_review', 'In review'
        APPROVED = 'approved', 'Approved'
        CHANGES_REQUESTED = 'changes_requested', 'Changes requested'
        REJECTED = 'rejected', 'Rejected'
        SUSPENDED = 'suspended', 'Suspended'

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
    # The only stored lifecycle column; written only by teachers/vetting.py (transition_teacher / create_teacher_profile).
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLIED, db_index=True)
    # Set when the tutor finished onboarding training (T6); live tutors were grandfathered by migration 0007.
    training_completed_at = models.DateTimeField(null=True, blank=True)
    # Derived from `status` by the database (plan §3.1 truth table): every existing filter keeps working and nothing can
    # set them. Constructor kwargs, save(update_fields=...) and queryset update() on them raise (see the tripwires below).
    is_verified = models.GeneratedField(
        expression=Case(When(status__in=VERIFIED_STATUSES, then=Value(True)), default=Value(False)),
        output_field=models.BooleanField(), db_persist=True, db_index=True)
    is_active = models.GeneratedField(
        expression=Case(When(status__in=ACTIVE_STATUSES, then=Value(True)), default=Value(False)),
        output_field=models.BooleanField(), db_persist=True, db_index=True)
    # Strikes inside the rolling STRIKE_WINDOW_DAYS window, kept in step by teachers/strikes.py (do not edit by hand)
    sla_strikes = models.PositiveSmallIntegerField(default=0)
    eskom_area_id = models.CharField(max_length=128, blank=True, default='')
    has_inverter_backup = models.BooleanField(default=False)
    has_lte_failover = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TeacherProfileQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=STATUS_VALUES), name='teacherprofile_status_valid'),
        ]

    def __init__(self, *args, **kwargs):
        # from_db() passes field values positionally, so only callers can hit this; Django would silently drop them.
        hit = GENERATED_FLAGS.intersection(kwargs)
        if hit:
            raise TypeError(f"{sorted(hit)} are generated from status; pass status=... (plan §3.1).")
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is not None:
            _refuse_generated(kwargs['update_fields'], 'save(update_fields=...)')   # Django would make it a silent no-op
        super().save(*args, **kwargs)

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


class TeacherStatusChangeQuerySet(models.QuerySet):
    """Append-only: bulk edits and bulk deletes are refused (a tutor's deletion still cascades through the collector)."""

    def update(self, **kwargs):
        raise ValueError('TeacherStatusChange rows are append-only; they cannot be updated.')

    def delete(self):
        raise ValueError('TeacherStatusChange rows are append-only; they cannot be deleted.')


class TeacherStatusChange(models.Model):
    """
    One row per tutor status change made through teachers/vetting.py (plus a baseline row, from_status '', when a profile is
    created or was migrated by 0007). Never edited or deleted by application code: vetting decisions and suspensions must be
    replayable.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='status_changes')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.CharField(max_length=80, help_text="'user:<username>' or a system source such as 'system:strikes'.")
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reason = models.CharField(max_length=500, blank=True)
    rubric = models.JSONField(null=True, blank=True)
    reviewed_assets = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = TeacherStatusChangeQuerySet.as_manager()

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['teacher', 'created_at'], name='teacher_statuschange_t_idx')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('TeacherStatusChange rows are append-only; they cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('TeacherStatusChange rows are append-only; they cannot be deleted.')

    def __str__(self):
        return f"{self.teacher_id}: {self.from_status or '-'} -> {self.to_status} by {self.actor}"


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
