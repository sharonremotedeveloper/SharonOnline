from contextlib import ExitStack, contextmanager

from django.db import models
from django.db.models import Case, Q, Value, When
from django.conf import settings
import uuid

# Plan §3.1, the only truth table. is_verified: approved|suspended. is_active: everything but rejected|suspended.
STATUS_VALUES = ('applied', 'submitted', 'in_review', 'approved', 'changes_requested', 'rejected', 'suspended')
VERIFIED_STATUSES = ('approved', 'suspended')
ACTIVE_STATUSES = ('applied', 'submitted', 'in_review', 'changes_requested', 'approved')
GENERATED_FLAGS = frozenset({'is_verified', 'is_active'})
# Written only with an explicit update_fields by their owners (vetting.py / strikes.py); a full-row save skips them.
SERVICE_OWNED = ('status', 'sla_strikes')
_INTERNAL = '_internal_generated_write'


@contextmanager
def _internal_write(instance):
    """Let Django's own machinery set the generated flags on `instance` (re-entrant)."""
    state = instance.__dict__
    state[_INTERNAL] = state.get(_INTERNAL, 0) + 1
    try:
        yield
    finally:
        state[_INTERNAL] -= 1
        if not state[_INTERNAL]:
            del state[_INTERNAL]


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

    def bookable(self):
        """
        The single bookable predicate (plan §3.1, slice T1b): approved (is_verified and is_active) and training_ok, i.e. the
        training gate (TUTOR_TRAINING_GATE_ENABLED) is off or the tutor finished training. Every path that creates or
        confirms a NEW lesson uses it; operations on existing lessons never do (docs/TUTOR_STATUS_MACHINE.md §8).
        """
        qs = self.filter(is_verified=True, is_active=True)
        if settings.TUTOR_TRAINING_GATE_ENABLED:
            qs = qs.filter(training_completed_at__isnull=False)
        return qs

    def operational(self, now=None):
        """
        Tutors whose integrations must keep running (Eskom sync, calendar reconcile): approved tutors, plus any tutor (e.g.
        suspended) who still has a confirmed / in-progress lesson that has not ended. Applicants never have one.
        """
        from apps.bookings.models import Booking
        from apps.common import clock
        live = Booking.objects.filter(teacher=models.OuterRef('pk'), end_time_utc__gte=now or clock.now(),
                                      status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS])
        return self.filter(Q(status=TeacherProfile.Status.APPROVED) | Q(models.Exists(live)))

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        with ExitStack() as stack:          # INSERT ... RETURNING sets the generated flags on each object
            for obj in objs:
                stack.enter_context(_internal_write(obj))
            created = super().bulk_create(objs, *args, **kwargs)
        for obj in created:
            obj._remember_owned(SERVICE_OWNED)
        return created


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
    # DEPRECATED (T1c): lesson prices come from the platform catalog (payments.LessonPrice, Task 10.1). No API exposes this
    # column any more; the public `price_per_25min_usd` field reports the catalog USD price. Drop after one release.
    price_per_25min_usd = models.DecimalField(max_digits=6, decimal_places=2, default=9.00)
    specialties = models.JSONField(default=list, blank=True, help_text="List of tags: ['FreeTalk', 'Business English', 'Daily News', 'TOEIC']")
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

    # ---- tripwires (docs/TUTOR_STATUS_MACHINE.md §4). Django's own loading/saving may set the generated flags on an
    # instance (from_db, refresh_from_db, INSERT ... RETURNING, bulk_create); everything else raises.
    def __init__(self, *args, **kwargs):
        # from_db() passes field values positionally, so only callers can hit this; Django would silently drop them.
        hit = GENERATED_FLAGS.intersection(kwargs)
        if hit:
            raise TypeError(f"{sorted(hit)} are generated from status; pass status=... (plan §3.1).")
        with _internal_write(self):
            super().__init__(*args, **kwargs)

    def __setattr__(self, name, value):
        if name in GENERATED_FLAGS and not self.__dict__.get(_INTERNAL):
            raise AttributeError(f"TeacherProfile.{name} is generated from status; use apps.teachers.vetting.transition_teacher.")
        super().__setattr__(name, value)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._remember_owned(SERVICE_OWNED)
        return instance

    def refresh_from_db(self, using=None, fields=None, from_queryset=None):
        with _internal_write(self):
            super().refresh_from_db(using=using, fields=fields, from_queryset=from_queryset)
        self._remember_owned(SERVICE_OWNED if fields is None else [n for n in SERVICE_OWNED if n in fields])

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is not None:
            _refuse_generated(kwargs['update_fields'], 'save(update_fields=...)')   # Django would make it a silent no-op
        elif not self._state.adding and not kwargs.get('force_insert'):
            # A full-row save never writes the service-owned columns: a stale copy (e.g. a DRF PATCH that loaded the
            # profile before a strike suspended the tutor) must not write `approved` back. Changing them here is an error.
            kwargs['update_fields'] = self._full_row_fields()
        written = kwargs.get('update_fields')
        with _internal_write(self):
            super().save(*args, **kwargs)
        self._remember_owned(SERVICE_OWNED if written is None else [n for n in SERVICE_OWNED if n in written])

    def _remember_owned(self, names):
        loaded = self.__dict__.setdefault('_loaded_owned', {})
        loaded.update({n: self.__dict__[n] for n in names if n in self.__dict__})

    def _full_row_fields(self):
        loaded = self.__dict__.get('_loaded_owned', {})
        changed = sorted(n for n, v in loaded.items() if self.__dict__.get(n, v) != v)
        if changed:
            raise ValueError(f"{changed} changed on the instance: status only via apps.teachers.vetting.transition_teacher, "
                             "sla_strikes only via apps.teachers.strikes.add_strike.")
        deferred = self.get_deferred_fields()
        return [f.name for f in self._meta.concrete_fields
                if not (f.primary_key or f.generated or f.name in SERVICE_OWNED or f.attname in deferred)]

    @property
    def is_bookable(self) -> bool:
        """Instance form of TeacherProfileQuerySet.bookable() (same rule; keep them in step)."""
        if self.status != TeacherProfile.Status.APPROVED:
            return False
        return not settings.TUTOR_TRAINING_GATE_ENABLED or self.training_completed_at is not None

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


class TeacherAsset(models.Model):
    """A server-committed, content-verified tutor asset."""

    class Kind(models.TextChoices):
        AVATAR = 'avatar', 'Avatar'
        ACCENT_AUDIO = 'accent_audio', 'Accent audio'
        TEFL_CERTIFICATE = 'tefl_certificate', 'TEFL certificate'
        INTRO_VIDEO = 'intro_video', 'Intro video'
        IDENTITY_DOCUMENT = 'identity_document', 'Identity document'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='assets')
    kind = models.CharField(max_length=32, choices=Kind.choices)
    object_key = models.CharField(max_length=512)
    quarantine_key = models.CharField(max_length=512, blank=True)
    etag = models.CharField(max_length=128)
    content_type = models.CharField(max_length=128)
    size_bytes = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    replaced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['teacher', 'kind', 'etag'], name='uniq_teacher_asset_etag')]
        indexes = [models.Index(fields=['teacher', 'kind', 'replaced_at'], name='teachers_te_teacher_d9a03c_idx')]

    def __str__(self):
        return f'{self.teacher_id}:{self.kind}:{self.etag}'


class PrivateAssetAccessAudit(models.Model):
    """Append-only access trail for private vetting documents."""

    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='private_asset_accesses')
    object_key = models.CharField(max_length=512)
    action = models.CharField(max_length=32, default='download')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('PrivateAssetAccessAudit rows are append-only.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('PrivateAssetAccessAudit rows are append-only.')

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


class TeacherTimeOff(models.Model):
    """
    A one-off absence (holiday, illness) as an absolute UTC interval (T2). The slot generator hides every slot that overlaps
    it. It never cancels a lesson: confirmed lessons inside it are returned to the tutor as conflicts to act on.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='time_off')
    start_utc = models.DateTimeField()
    end_utc = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_utc']
        constraints = [
            models.CheckConstraint(condition=Q(end_utc__gt=models.F('start_utc')), name='teachertimeoff_end_after_start'),
        ]
        indexes = [models.Index(fields=['teacher', 'end_utc'], name='teacher_timeoff_t_end_idx')]


class TeacherDateOverride(models.Model):
    """
    A specific-date exception to the weekly matrix, in the tutor's LOCAL clock (INV TEA-03, T2).
    `open`   adds hours on that date (start_time/end_time required).
    `closed` removes hours from that date: the given window, or the whole day when both times are empty.
    """
    class Kind(models.TextChoices):
        OPEN = 'open', 'Extra hours'
        CLOSED = 'closed', 'Hours removed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='date_overrides')
    date = models.DateField(help_text="Date in the teacher's local timezone")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'start_time']
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=['open', 'closed']), name='teacherdateoverride_kind_valid'),
            models.CheckConstraint(
                condition=(Q(start_time__isnull=True, end_time__isnull=True)
                           | Q(start_time__isnull=False, end_time__isnull=False, start_time__lt=models.F('end_time'))),
                name='teacherdateoverride_hours_pair_ordered'),
            models.CheckConstraint(condition=Q(kind='closed') | Q(start_time__isnull=False),
                                   name='teacherdateoverride_open_needs_hours'),
        ]
        indexes = [models.Index(fields=['teacher', 'date'], name='teacher_dateoverride_t_d_idx')]


class TrainingModule(models.Model):
    """One onboarding training module (slice T6). Content is written by Sharon; only published modules are shown, and only
    published + required ones count towards `TeacherProfile.training_completed_at` (set by teachers/training.py)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True, help_text='Markdown shown to the tutor.')
    position = models.PositiveIntegerField(default=1, db_index=True)
    estimated_minutes = models.PositiveIntegerField(default=10)
    is_required = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', 'slug']

    def __str__(self):
        return self.slug


class TrainingProgress(models.Model):
    """A tutor finished a module (one row per tutor and module; written only by teachers/training.py)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='training_progress')
    module = models.ForeignKey(TrainingModule, on_delete=models.CASCADE, related_name='progress')
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['teacher', 'module'], name='uniq_training_progress')]


class TeacherApplication(models.Model):
    """What an applicant reports while completing the funnel (slice T5a). Uploads live in TeacherAsset, the profile text on
    TeacherProfile; this row holds the rest. The speed test is measured by the browser and recorded as given: it is advisory
    evidence for the reviewer, not proof. The South African ID number is deliberately NOT stored (the document is an upload)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.OneToOneField(TeacherProfile, on_delete=models.CASCADE, related_name='application')
    speed_test_download_mbps = models.DecimalField(max_digits=7, decimal_places=1, null=True, blank=True)
    speed_test_upload_mbps = models.DecimalField(max_digits=7, decimal_places=1, null=True, blank=True)
    speed_test_at = models.DateTimeField(null=True, blank=True)
    power_backup_confirmed_at = models.DateTimeField(null=True, blank=True)
    declaration_accepted_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
