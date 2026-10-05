"""
Single entry point for turning "I want this slot" into a held, payable booking (Task 9.2).

Reserve = validate + Redis lock (10 min) + PENDING_PAYMENT booking, atomically. The returned booking id is what checkout
pays for. Both `POST /bookings/reserve/` and `POST /bookings/` go through here so there is no path that creates a
booking without the lock/validation.
"""
from datetime import timedelta, timezone as dt_timezone
from typing import Optional, Tuple

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services.booking_block import booking_block_message
from apps.bookings.services.holds import hold_expires_at, live_hold_q
from apps.bookings.services.lock_service import acquire_slot_lock, new_slot_lock_token, release_slot_lock
from apps.bookings.services.slot_generator import LESSON_DURATION_MINUTES, generate_teacher_slots, horizon_scan_days
from apps.teachers.models import TeacherProfile

MAX_PENDING_PER_STUDENT = 3  # stops one account from hoarding slots by spamming reserve


class ReservationError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def reserve_slot(*, student, teacher_id, start_time_utc, material=None) -> Tuple[Booking, bool]:
    """Returns (booking, created). `created` is False when an identical live hold already existed (safe retry)."""
    if getattr(student, 'role', None) != 'student':
        raise ReservationError(403, "Only student accounts can book lessons.")
    blocked = booking_block_message(student)
    if blocked:
        raise ReservationError(409, blocked)

    teacher = (TeacherProfile.objects.select_related('user')
               .filter(id=teacher_id, is_active=True, is_verified=True).first())
    if teacher is None:
        raise ReservationError(404, "This tutor is not available for booking.")
    if teacher.user_id == student.id:
        raise ReservationError(409, "You cannot book your own lessons.")

    start = start_time_utc.astimezone(dt_timezone.utc)
    end = start + timedelta(minutes=LESSON_DURATION_MINUTES)
    now = timezone.now()

    # Safe retry / page refresh: return the student's own live hold instead of failing on their own lock.
    existing = (Booking.objects.filter(student=student, teacher=teacher, start_time_utc=start)
                .filter(live_hold_q(now)).first())
    if existing:
        return existing, False

    # The slot must be a real, currently-bookable slot of this tutor (availability, 25-min grid, future, not booked/held).
    slot = next((s for s in generate_teacher_slots(teacher=teacher, days_ahead=horizon_scan_days())
                 if s['start_time_utc'] and _same_instant(s['start_time_utc'], start)), None)
    if slot is None:
        raise ReservationError(409, "That time is not one of this tutor's open slots.")
    if not slot['is_bookable']:
        raise ReservationError(409, "This 25-minute slot was just taken. Please choose another.")

    # The Redis lock can lapse while another student's payment is still in flight: the database is the second opinion.
    if (Booking.objects.filter(teacher=teacher, start_time_utc=start).exclude(student=student)
            .filter(live_hold_q(now) | Q(status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS])).exists()):
        raise ReservationError(409, "This 25-minute slot was just taken. Please choose another.")

    mine = Booking.objects.filter(student=student).filter(
        live_hold_q(now) | Q(status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS]))
    if mine.filter(start_time_utc__lt=end, end_time_utc__gt=start).exists():
        raise ReservationError(409, "You already have a lesson at that time.")
    if mine.filter(live_hold_q(now)).count() >= MAX_PENDING_PER_STUDENT:
        raise ReservationError(409, "You have several unpaid reservations. Complete or wait for them to expire first.")

    # Use the generator's own timestamp string so the lock key matches the one it checks for "reserved" slots.
    lock_ts = slot['start_time_utc']
    lock_token = new_slot_lock_token()
    if not acquire_slot_lock(str(teacher.id), lock_ts, str(student.id), token=lock_token):
        raise ReservationError(409, "This 25-minute slot was just taken. Please choose another.")

    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                teacher=teacher, student=student, material=material,
                start_time_utc=start, end_time_utc=end, status=Booking.Status.PENDING_PAYMENT,
                slot_lock_token=lock_token)
    except Exception:
        release_slot_lock(str(teacher.id), lock_ts, str(student.id), token=lock_token)
        raise
    return booking, True


def _same_instant(iso: str, dt) -> bool:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso) == dt
    except ValueError:
        return False


def reservation_payload(booking: Booking) -> dict:
    expires = hold_expires_at(booking)
    remaining = max(int((expires - timezone.now()).total_seconds()), 0)
    return {
        "booking_id": str(booking.id),
        "status": booking.status,
        "teacher_id": str(booking.teacher_id),
        "start_time_utc": booking.start_time_utc.isoformat(),
        "end_time_utc": booking.end_time_utc.isoformat(),
        "lock_ttl_seconds": remaining,
        "lock_expires_at": expires.isoformat(),
        "message": "Slot held for 10 minutes. Please complete payment to confirm your booking.",
    }
