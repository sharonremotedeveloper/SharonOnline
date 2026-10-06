"""
Moving a paid lesson to another open slot of the same tutor (Task 9.6, decision D-6).

Rules (all settings): the student only; the lesson is CONFIRMED; its current start is more than RESCHEDULE_MIN_NOTICE_HOURS away;
at most RESCHEDULE_MAX_PER_BOOKING moves; the new slot is a real open slot of that tutor, at least the minimum notice away and at most
BOOKING_HORIZON_DAYS days out. Tutors cannot move a student's lesson: they cancel it (docs/CANCELLATION_AND_REFUNDS.md).

The same Booking row moves, so its payment, escrow and id stay put and the 24-hour release simply counts from the new end time.
The Zoom room is replaced (the old one deleted, a new one provisioned by the usual fulfilment task) and reminders re-arm.
The fulfilment row is reset inside the move transaction (services/fulfillment.py::reset_for_reprovision), so every step runs
again for the new time and any run still working on the old time loses its claim.
"""
from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingReschedule
from apps.bookings.services.fulfillment import reset_for_reprovision
from apps.bookings.services.holds import live_hold_q
from apps.bookings.services.lock_service import acquire_slot_lock, new_slot_lock_token, release_slot_lock
from apps.bookings.services.slot_generator import LESSON_DURATION_MINUTES, generate_teacher_slots, horizon_days, horizon_scan_days
from apps.integrations.tasks import cleanup_zoom_meeting, dispatch_booking_fulfillment
from django.db.models import Q

S = Booking.Status
MOVED_FIELDS = ['original_start_time_utc', 'start_time_utc', 'end_time_utc', 'reschedule_count', 'reminder_24h_sent',
                'reminder_1h_sent', 'reminder_10m_sent', 'tutor_late_alert_sent', 'zoom_meeting_id', 'zoom_join_url',
                'zoom_start_url', 'zoom_password', 'zoom_host_user_id', 'slot_lock_token',
                'updated_at']


class RescheduleError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def reschedule_booking(booking_id, student, new_start, now=None) -> Booking:
    now = now or timezone.now()
    new_start = new_start.astimezone(dt_timezone.utc)
    new_end = new_start + timedelta(minutes=LESSON_DURATION_MINUTES)
    notice = timedelta(hours=settings.RESCHEDULE_MIN_NOTICE_HOURS)
    lock_args = None

    with transaction.atomic():
        booking = Booking.objects.select_for_update(of=('self',)).select_related('teacher__user', 'student').get(pk=booking_id)
        if booking.student_id != student.id:
            raise RescheduleError(403, 'not_a_party', 'Only the student of a lesson can move it.')
        if booking.status != S.CONFIRMED:
            raise RescheduleError(409, 'not_reschedulable', f"A lesson that is '{booking.status}' cannot be moved.")
        if booking.reschedule_count >= settings.RESCHEDULE_MAX_PER_BOOKING:
            raise RescheduleError(409, 'reschedule_limit_reached', 'This lesson has already been rescheduled once.')
        if booking.start_time_utc - now <= notice:
            raise RescheduleError(409, 'reschedule_too_late',
                                  f'A lesson can only be moved more than {settings.RESCHEDULE_MIN_NOTICE_HOURS} hours before it starts.')

        if new_start == booking.start_time_utc or new_start - now < notice or new_start - now > timedelta(days=horizon_days()):
            raise RescheduleError(400, 'invalid_slot', 'Choose a different time at least '
                                  f'{settings.RESCHEDULE_MIN_NOTICE_HOURS} hours and at most {horizon_days()} days from now.')
        teacher = booking.teacher
        if not teacher.is_bookable:     # the NEW slot is new tutor time: same predicate as reserving (slice T1b)
            raise RescheduleError(409, 'slot_unavailable', 'This tutor is not available for new times right now.')

        slot = next((s for s in generate_teacher_slots(teacher=teacher, days_ahead=horizon_scan_days())
                     if s['start_time_utc'] and _instant(s['start_time_utc']) == new_start), None)
        if slot is None:
            raise RescheduleError(400, 'invalid_slot', "That time is not one of this tutor's open slots.")
        taken = RescheduleError(409, 'slot_unavailable', 'That 25-minute slot was just taken. Please choose another.')
        if not slot['is_bookable']:
            raise taken
        # The generator is a snapshot; the database is the second opinion (same checks as reserving a slot).
        if (Booking.objects.filter(teacher=teacher, start_time_utc=new_start).exclude(pk=booking.pk)
                .filter(live_hold_q(now) | Q(status__in=[S.CONFIRMED, S.IN_PROGRESS])).exists()):
            raise taken
        mine = (Booking.objects.filter(student=student).exclude(pk=booking.pk)
                .filter(live_hold_q(now) | Q(status__in=[S.CONFIRMED, S.IN_PROGRESS])))
        if mine.filter(start_time_utc__lt=new_end, end_time_utc__gt=new_start).exists():
            raise RescheduleError(409, 'slot_unavailable', 'You already have a lesson at that time.')

        # Same ownership-token rule as a reservation: only the holder of this exact token can release or extend the lock.
        token = new_slot_lock_token()
        lock_args = (str(teacher.id), slot['start_time_utc'], str(student.id))
        if not acquire_slot_lock(*lock_args, token=token):
            raise taken

        old_start, old_meeting = booking.start_time_utc, booking.zoom_meeting_id
        try:
            with transaction.atomic():
                booking.original_start_time_utc = booking.original_start_time_utc or old_start
                booking.start_time_utc, booking.end_time_utc = new_start, new_end
                booking.reschedule_count += 1
                booking.reminder_24h_sent = booking.reminder_1h_sent = booking.reminder_10m_sent = booking.tutor_late_alert_sent = False
                booking.zoom_meeting_id = booking.zoom_join_url = booking.zoom_start_url = booking.zoom_password = ''
                booking.zoom_host_user_id = None
                booking.slot_lock_token = token
                booking.save(update_fields=MOVED_FIELDS)
                BookingReschedule.objects.create(booking=booking, old_start_time_utc=old_start, new_start_time_utc=new_start,
                                                 actor=f'user:{student.username}')
                # The completed fulfilment row would otherwise be skipped: no new room, and a T+10 "no-show" (Slice F0).
                reset_for_reprovision(booking)
        except IntegrityError:
            release_slot_lock(*lock_args, token=token)
            raise taken
        booking_pk = str(booking.id)
        from apps.notifications.service import booking_key, notify
        notify(booking.student, 'booking_rescheduled', key=booking_key('booking-rescheduled', booking, 'student'),
               payload={'booking_id': booking_pk}, booking=booking)
        notify(teacher.user, 'booking_rescheduled', key=booking_key('booking-rescheduled', booking, 'teacher'),
               payload={'booking_id': booking_pk}, booking=booking)
        transaction.on_commit(lambda: _after_move(booking_pk, old_meeting))
    return booking


def _after_move(booking_id: str, old_meeting_id: str):
    """Outside the money/slot transaction: drop the old Zoom room, then let fulfilment build the new one, move the tutor's calendar
    event (same event id, see sync_booking_to_teacher_gcal) and tell everyone."""
    if old_meeting_id:
        cleanup_zoom_meeting.delay(old_meeting_id)
    dispatch_booking_fulfillment.delay(booking_id)


def _instant(iso: str):
    from datetime import datetime
    return datetime.fromisoformat(iso)
