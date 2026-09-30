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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey('teachers.TeacherProfile', on_delete=models.PROTECT, related_name='bookings')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='student_bookings')
    material = models.ForeignKey('materials.Material', on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True)

    # All booking times are stored strictly in UTC
    start_time_utc = models.DateTimeField(db_index=True)
    end_time_utc = models.DateTimeField()

    # Video Conferencing details (provisioned via Zoom Server-to-Server API)
    zoom_meeting_id = models.CharField(max_length=64, blank=True)
    zoom_join_url = models.URLField(max_length=512, blank=True)
    zoom_start_url = models.URLField(max_length=1024, blank=True)
    zoom_password = models.CharField(max_length=32, blank=True)

    # Google Calendar reference
    teacher_gcal_event_id = models.CharField(max_length=255, blank=True)

    # Background Automation & Reminder State Bitflags
    memo_reminder_sent = models.BooleanField(default=False)
    reminder_24h_sent = models.BooleanField(default=False)
    reminder_1h_sent = models.BooleanField(default=False)
    reminder_10m_sent = models.BooleanField(default=False)
    tutor_late_alert_sent = models.BooleanField(default=False)
    escrow_cleared_at = models.DateTimeField(null=True, blank=True)

    # Asymmetric Feedback & Rating
    student_rating = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1 to 5 star rating")
    student_review = models.TextField(blank=True, help_text="Written review visible to admin and teacher")

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
    homework = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Memo for Booking {self.booking_id} by {self.teacher.user.username}"


class AttendanceAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='attendance_audits')
    participant_email = models.EmailField()
    zoom_user_id = models.CharField(max_length=64, blank=True, db_index=True)
    join_time_utc = models.DateTimeField(null=True, blank=True)
    leave_time_utc = models.DateTimeField(null=True, blank=True)
    total_minutes = models.PositiveIntegerField(default=0)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-join_time_utc']

    def __str__(self):
        return f"Attendance {self.participant_email} on {self.booking_id} ({self.total_minutes}m)"
