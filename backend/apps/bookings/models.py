from django.db import models
from django.conf import settings
import uuid

class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = 'pending_payment', 'Pending Payment'
        CONFIRMED = 'confirmed', 'Confirmed'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        DISPUTED = 'disputed', 'Disputed'
        INTERRUPTED_POWER = 'interrupted_power', 'Interrupted (Power Outage)'
        STUDENT_NO_SHOW = 'student_no_show', 'Student No Show'
        TEACHER_NO_SHOW = 'teacher_no_show', 'Teacher No Show'
        COMPLETED_PENDING_MEMO = 'completed_pending_memo', 'Completed (Pending Memo)'
        COMPLETED_MEMO_FORFEITED = 'completed_memo_forfeited', 'Completed (Memo Forfeited)'
        # Paid lessons that were cancelled (Task 9.6). Not CANCELLED: see state_machine.py.
        CANCELLED_BY_STUDENT = 'cancelled_by_student', 'Cancelled by Student (refunded)'
        STUDENT_LATE_CANCELLED = 'student_late_cancelled', 'Cancelled by Student (late, fee kept)'
        CANCELLED_BY_TEACHER = 'cancelled_by_teacher', 'Cancelled by Tutor (refunded)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey('teachers.TeacherProfile', on_delete=models.PROTECT, related_name='bookings')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='student_bookings')
    material = models.ForeignKey('materials.Material', on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True)
    # Unique ownership token for atomic Redis compare-and-release/renew operations.
    slot_lock_token = models.CharField(max_length=64, blank=True, editable=False)

    # All booking times are stored strictly in UTC
    start_time_utc = models.DateTimeField(db_index=True)
    end_time_utc = models.DateTimeField()

    # Video Conferencing details (provisioned via Zoom Server-to-Server API)
    zoom_meeting_id = models.CharField(max_length=64, blank=True)
    zoom_join_url = models.URLField(max_length=512, blank=True)
    # DEPRECATED (Slice Z1): the host link embeds an expiring ZAK. No longer written (0015 blanked old values); the tutor
    # fetches a fresh one from GET /bookings/<id>/host-link/. Kept one release for the API contract, then dropped.
    zoom_start_url = models.URLField(max_length=1024, blank=True)
    zoom_password = models.CharField(max_length=32, blank=True)
    # Zoom user the meeting was created under (HostPicker, Slice Z1). Null = no meeting / created before Z1 (= 'me').
    zoom_host_user_id = models.CharField(max_length=64, null=True, blank=True)

    # Google Calendar reference
    teacher_gcal_event_id = models.CharField(max_length=255, blank=True)

    # Background Automation & Reminder State Bitflags
    memo_reminder_sent = models.BooleanField(default=False)
    reminder_24h_sent = models.BooleanField(default=False)
    reminder_1h_sent = models.BooleanField(default=False)
    reminder_10m_sent = models.BooleanField(default=False)
    tutor_late_alert_sent = models.BooleanField(default=False)
    escrow_cleared_at = models.DateTimeField(null=True, blank=True)

    # Cancellation + rescheduling (Task 9.6)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    cancel_reason = models.CharField(max_length=255, blank=True)
    reschedule_count = models.PositiveSmallIntegerField(default=0)
    original_start_time_utc = models.DateTimeField(null=True, blank=True, help_text="Where the lesson started out, before its first reschedule")

    # Asymmetric Feedback & Rating
    student_rating = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1 to 5 star rating")
    student_review = models.TextField(blank=True, help_text="PRIVATE written review: staff only. Never shown to the tutor or other students.")
    student_review_tags = models.JSONField(default=list, blank=True, help_text="Rubric tags the student picked (services.reviews.REVIEW_TAGS)")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time_utc']
        constraints = [
            # Hard database-level lock preventing double-booking race conditions
            models.UniqueConstraint(
                fields=['teacher', 'start_time_utc'],
                condition=models.Q(status__in=[
                    'confirmed',
                    'in_progress',
                    'completed',
                    'completed_pending_memo',
                    'completed_memo_forfeited'
                ]),
                name='unique_teacher_active_timeslot'
            )
        ]

    def __str__(self):
        return f"Booking {self.id} | {self.teacher.user.username} with {self.student.username} at {self.start_time_utc.strftime('%Y-%m-%d %H:%M UTC')}"


class BookingReschedule(models.Model):
    """Append-only record of a lesson being moved (the Booking row keeps its id, payment and escrow)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='reschedules')
    old_start_time_utc = models.DateTimeField()
    new_start_time_utc = models.DateTimeField()
    actor = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class HostLinkIssue(models.Model):
    """
    Slice Z1 (QA #3): staff (not the tutor) was handed the Zoom HOST link of a lesson. Whoever opens the host link is the
    meeting's host, and the attendance rule credits the host as the TUTOR, so a staff-hosted lesson would otherwise show the
    absent tutor as present. The row is the audit trail (who, when) and an open hold: escrow is not released
    (`payments.services.settlement.attendance_verified_for_release`) until an admin reviews it (`reviewed_at`).
    Written only by `services.host_link.fresh_host_link`; reviewed only by `review_host_link_issues`.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='host_link_issues')
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['booking', 'reviewed_at'])]

    def __str__(self):
        return f"Host link for {self.booking_id} issued to staff {self.issued_by_id}"


class LessonMemo(models.Model):
    """
    Submitted by the teacher post-class: contains grammar notes, vocabulary bank entries, and homework.
    Published to student's dashboard and feeds the 'My Words' flashcard system.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='memo')
    teacher = models.ForeignKey('teachers.TeacherProfile', on_delete=models.CASCADE)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_memos')
    feedback_text = models.TextField(help_text="Grammar corrections, speaking feedback, overall commentary")
    vocabulary_words = models.JSONField(default=list, help_text="List of words: [{'word': 'resilience', 'definition': '...'}]")
    pronunciation_notes = models.TextField(blank=True)
    grammar_notes = models.TextField(blank=True, help_text="Grammar points to remember (shown to the student next to the vocabulary)")
    homework = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Memo for Booking {self.booking_id} by {self.teacher.user.username}"


class AttendanceAudit(models.Model):
    class Classification(models.TextChoices):
        TEACHER = 'teacher', 'Teacher'
        STUDENT = 'student', 'Student'
        UNKNOWN = 'unknown', 'Unknown'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='attendance_audits')
    participant_email = models.EmailField()
    zoom_user_id = models.CharField(max_length=64, blank=True, db_index=True)
    participant_id = models.CharField(max_length=128, blank=True, db_index=True)
    registrant_id = models.CharField(max_length=128, blank=True, db_index=True)
    host_id = models.CharField(max_length=128, blank=True, db_index=True)
    event_ids = models.JSONField(default=list, blank=True)
    classification = models.CharField(
        max_length=16, choices=Classification.choices, default=Classification.UNKNOWN, db_index=True)
    join_time_utc = models.DateTimeField(null=True, blank=True)
    leave_time_utc = models.DateTimeField(null=True, blank=True)
    total_minutes = models.PositiveIntegerField(default=0)
    raw_payload = models.JSONField(default=dict, blank=True)
    # How the participant was identified (integrations/services/attendance.py): host, account_email, email,
    # meeting_started, or unmatched. `participant_email` is an account e-mail ONLY for identified teacher/student rows;
    # unmatched participants are kept (evidence) with an empty e-mail so nothing downstream can count them.
    identity = models.CharField(max_length=24, blank=True)
    zoom_session_id = models.CharField(max_length=96, blank=True)   # one Zoom join session; makes webhook retries idempotent
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-join_time_utc']
        constraints = [
            models.UniqueConstraint(fields=['booking', 'zoom_session_id'], condition=~models.Q(zoom_session_id=''),
                                    name='uniq_attendance_session_per_booking'),
        ]

    def __str__(self):
        return f"Attendance {self.participant_email} on {self.booking_id} ({self.total_minutes}m)"


class BookingStatusChange(models.Model):
    """
    Append-only audit trail: one row per status change made through `services.state_machine.transition_booking`.
    Never edited or deleted by application code (disputes and payouts rely on being able to replay what happened).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='status_changes')
    from_status = models.CharField(max_length=30)
    to_status = models.CharField(max_length=30)
    actor = models.CharField(max_length=80, help_text="'user:<username>' or a system source such as 'system:purge_expired'.")
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['booking', 'created_at'])]

    def __str__(self):
        return f"{self.booking_id}: {self.from_status} -> {self.to_status} by {self.actor}"
