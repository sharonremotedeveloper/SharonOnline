"""Attendance evidence: who was present in a lesson's room, and for how long.

Everything downstream (no-show verdicts, the 20-minute completion rule, escrow release, disputes) reads the
`AttendanceAudit` rows written by the Daily webhook receiver (`integrations/views.py::DailyWebhookReceiverView`) and the
presence probe (`bookings/services/attendance_probe.py`). A row is keyed by the Daily join session, so webhook retries are
idempotent. Callers hold the booking row lock where it matters.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import AttendanceAudit

TEACHER, STUDENT, UNKNOWN = 'teacher', 'student', 'unknown'

DISCONNECT_GRACE = timedelta(minutes=5)


def classified_rows(booking, classification):
    """Use explicit identity; the blank-classification branch supports pre-migration rows only."""
    email = booking.teacher.user.email if classification == TEACHER else booking.student.email
    return AttendanceAudit.objects.filter(booking=booking).filter(
        Q(classification=classification) |
        Q(classification='', participant_email=email) |
        Q(classification=UNKNOWN, identity='', participant_email=email)
    )


def present_with_disconnect_grace(booking, classification, at):
    rows = classified_rows(booking, classification)
    if rows.filter(join_time_utc__isnull=True, total_minutes__gt=0).exists():
        return True
    return rows.filter(
        join_time_utc__lte=at,
    ).filter(Q(leave_time_utc__isnull=True) | Q(leave_time_utc__gte=at - DISCONNECT_GRACE)).exists()


def credited_attendance_minutes(booking, classification, *, through=None):
    """Sum identified presence while crediting reconnect gaps of at most five minutes."""
    through = through or timezone.now()
    rows = classified_rows(booking, classification)
    legacy_rows = rows.filter(Q(join_time_utc__isnull=True) | Q(leave_time_utc__isnull=True, total_minutes__gt=0))
    legacy_minutes = min(
        sum(legacy_rows.values_list('total_minutes', flat=True)),
        int((booking.end_time_utc - booking.start_time_utc).total_seconds() // 60),
    )
    intervals = []
    interval_rows = rows.exclude(join_time_utc__isnull=True).exclude(leave_time_utc__isnull=True, total_minutes__gt=0)
    for row in interval_rows.order_by('join_time_utc'):
        start = max(row.join_time_utc, booking.start_time_utc)
        end = min(row.leave_time_utc or through, booking.end_time_utc, through)
        if end > start:
            intervals.append((start, end))
    if not intervals:
        return legacy_minutes
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1] + DISCONNECT_GRACE:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    lesson_minutes = int((booking.end_time_utc - booking.start_time_utc).total_seconds() // 60)
    return min(lesson_minutes, legacy_minutes + int(sum((end - start).total_seconds() for start, end in merged) // 60))
